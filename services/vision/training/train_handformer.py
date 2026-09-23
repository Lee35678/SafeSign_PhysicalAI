# -*- coding: utf-8 -*-
"""GPU 학습 — HandFormer(또는 MLP) + Evidential 머리 + 딥 앙상블. **공개 데이터만** 쓴다.

    python training/train_handformer.py --arch mlp               # 설정 비교용 (val 만 본다)
    python training/train_handformer.py --size small --final     # 최종 모델 (공개 test 1회 + 저장)
    python scripts/plot_training.py                              # epoch 별 그래프

자체 촬영(JH·me01)과 웹캠 로그는 **여기서 전혀 읽지 않는다.**
  그 데이터는 마지막 KPI 측정용이다. 가중치 학습은 물론이고 epoch·설계를 고르는 데 써도
  "처음 보는 데이터"가 아니게 된다. 최종 모델이 정해진 뒤 scripts/evaluate_edl.py 로 한 번만 본다.

데이터 분할 — 공개 데이터 27,735건, 클래스별·세션 단위 (stratified_session_split)
  train  거대 세션 전부 + 작은 세션 일부   가중치 학습
  val    작은 세션들                       early stopping · 설정 비교
  test   작은 세션들 (val 과 같은 성격)     --final 일 때 한 번만

"7종 밖"을 공개 데이터로 재는 법 — 한 클래스 빼기 (leave-one-class-out, LOCO)
  7종 중 하나를 빼고 6종으로 학습한 뒤, 뺀 클래스를 "처음 보는 손모양"으로 넣어 u 가 올라가는지
  본다. 7번 반복해 평균한다.
    검증 = 아는 6종의 val  vs  뺀 클래스의 train+val 샘플
    시험 = 아는 6종의 test vs  뺀 클래스의 test 샘플        (--final 일 때만)

early stopping (2026-09-23)
  감시 지표   val EDL 손실 (아는 클래스, 클래스 균형 가중). **λ 는 λmax 로 고정**해서 계산한다 —
              학습 중에는 KL 가중치가 0 -> λmax 로 오르므로 그대로 쓰면 epoch 마다 잣대가 달라진다.
              val 정답률(590건)은 epoch 마다 들쭉날쭉해서 감시 지표로 쓰지 않는다.
  최소 epoch  KL 가중치가 최대에 도달할 때까지(--anneal). 목표가 바뀌는 중에 멈추지 않는다.
  개선        최고 기록보다 --min-delta(0.1%) 이상 낮아질 때만
  멈춤        --patience(15) epoch 동안 개선이 없으면
  학습률      정체 --lr-patience(5) epoch 마다 절반 (최소 1e-5). 멈추기 전에 더 내려갈 기회를 준다
  끝          **최고점 가중치로 되돌린다**
  LOCO 7회도 같은 규칙(아는 6종의 val 손실)으로 멈춘다. OOD 점수로 멈추게 하면 그 점수가 낙관적이 된다.

하드웨어 기준 (개발 노트북: RTX 3050 Ti Laptop, VRAM 4GB 중 여유 ~3.2GB)
  · 혼합정밀 — Ampere 이상 bf16, Colab T4 는 fp16+GradScaler (amp_dtype). **손실만 fp32**.
  · small 0.57M(VRAM ~0.9GB) · base 1.87M · large 5.42M(Colab 권장). GPU 가 없으면 CPU.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "src"))

import torch  # noqa: E402

from cognition.edl import EvidentialNet, edl_mse_loss  # noqa: E402
from cognition.evidential import EvidentialPredictor  # noqa: E402
from cognition.handformer import (  # noqa: E402
    SIZES, HandFormer, augment, count_params, joint23_torch, to_tensor,
)

LM_CACHE = SERVICE_ROOT / "training" / ".landmark_cache.npz"
FINAL_OUT = SERVICE_ROOT / "models" / "handformer_edl.pt"
REPORTS = SERVICE_ROOT / "reports"
CRITICAL = "정지"


# ============================================================ 데이터
def stratified_session_split(y: np.ndarray, sess: np.ndarray, fracs=(0.70, 0.15, 0.15),
                             seed: int = 0, giant_frac: float = 0.05) -> np.ndarray:
    """클래스마다 세션을 train/val/test 에 배정한다 (반환: 0/1/2 배열).

    왜 무작위 세션 분할을 쓰지 않는가 — 세션 크기가 극단적으로 불균등하다(중앙값 1건,
    최대 2,700건: 한 출처가 통째로 한 세션). 무작위로 나눴더니 train 에 좌회전 유도가
    208건뿐이고 val 의 97%가 두 클래스였다(2026-09-23 실측).

    방법
      ① 클래스 건수의 giant_frac(5%)을 넘는 **거대 세션은 무조건 train**. 쪼갤 수 없고,
         val/test 에 가면 그 분할이 세션 하나짜리가 되어 버린다.
      ② 나머지 작은 세션을 큰 것부터 **목표 건수 대비 가장 모자란 분할**에 넣는다.
    그래서 val 과 test 가 둘 다 "작은 세션 여럿"이라 **성격이 같다**. 세션은 절대 둘로
    나뉘지 않으므로 누수는 없다(05 §3-2).
    """
    rng = np.random.default_rng(seed)
    part = np.zeros(len(y), dtype=np.int8)
    for c in np.unique(y):
        m = y == c
        s_u, s_n = np.unique(sess[m], return_counts=True)
        target = np.asarray(fracs) * m.sum()
        have = np.zeros(3)
        giant = s_n > giant_frac * m.sum()
        have[0] = s_n[giant].sum()                            # ① 거대 세션 -> train
        small = np.flatnonzero(~giant)
        order = small[np.lexsort((rng.random(len(small)), -s_n[small]))]
        for k in order:                                       # ② 큰 것부터, 같으면 무작위
            dest = int(np.argmax(target - have))
            have[dest] += s_n[k]
            if dest:
                part[m & (sess == s_u[k])] = dest
    return part


def load_data(split_seed: int = 0) -> dict:
    """랜드마크 캐시 -> 클래스별·세션 단위 train/val/test."""
    if not LM_CACHE.exists():
        raise SystemExit(f"랜드마크 캐시가 없습니다: {LM_CACHE}\n"
                         "  먼저: python training/build_landmark_cache.py")
    z = np.load(LM_CACHE, allow_pickle=False)
    C, labels, sess = z["canonical"].astype(np.float32), z["labels"], z["sessions"]
    classes = sorted(set(labels.tolist()))
    idx = {c: i for i, c in enumerate(classes)}
    y = np.array([idx[c] for c in labels], dtype=np.int64)
    part = stratified_session_split(y, sess, seed=split_seed)
    return {"C": C, "y": y, "tr": part == 0, "va": part == 1, "te": part == 2,
            "classes": classes, "n_sessions": len(np.unique(sess)), "sessions": sess}


def _auc(neg: np.ndarray, pos: np.ndarray) -> float:
    """pos 가 neg 보다 u 가 높을수록 1. (u 로 '처음 보는 것' 또는 '틀린 것'을 가려내는 능력)"""
    try:
        from sklearn.metrics import roc_auc_score
        return float(roc_auc_score(np.r_[np.zeros(len(neg)), np.ones(len(pos))], np.r_[neg, pos]))
    except Exception:
        return float("nan")


def known_report(pred: EvidentialPredictor, C: np.ndarray, y_local: np.ndarray) -> dict:
    """아는 클래스에 대한 정답률 · 오답탐지 AUC · 정상 오거부율(u > max b)."""
    out = pred(C)
    wrong = out["pred"] != y_local
    return {"acc": float((~wrong).mean() * 100), "auc_err": _auc(out["u"][~wrong], out["u"][wrong]),
            "reject": float((out["u"] > out["b_max"]).mean() * 100),
            "u_median": float(np.median(out["u"])), "_u": out["u"]}


def amp_dtype(device: str):
    """혼합정밀 자료형. Ampere(8.x) 이상은 bf16, 그 아래(Colab T4 = 7.5)는 fp16 + GradScaler.

    torch 의 is_bf16_supported() 는 **에뮬레이션도 True 로 친다** — T4 에서 bf16 을 쓰면 오히려
    느려진다. 그래서 compute capability 로 직접 판단한다.
    """
    if not device.startswith("cuda"):
        return None
    major, _ = torch.cuda.get_device_capability()
    return torch.bfloat16 if major >= 8 else torch.float16


def build_member(arch: str, K: int, size: str, activation: str, width: int = 256,
                 norm: str = "layer"):
    if arch == "handformer":
        return HandFormer(K, size=size, activation=activation)
    return EvidentialNet(23, K, width, 0.2, norm, activation)


# ============================================================ 학습
def train_member(data: dict, arch: str, seed: int, device: str, *, size: str = "small",
                 max_epochs: int = 300, patience: int = 15, min_delta: float = 1e-3,
                 lr_patience: int = 5, batch: int = 1024, lr: float | None = None,
                 lam_max: float = 3.0, anneal: int = 30, activation: str = "exp",
                 aug: bool = True, width: int = 256, norm: str = "layer",
                 critical_weight: float = 1.0, exclude: int | None = None,
                 verbose: bool = True):
    """멤버 하나를 early stopping 으로 학습한다. exclude 를 주면 그 클래스를 빼고(LOCO).

    epoch 마다 train 과 **val 지표만** 기록한다. 끝나면 최고점 가중치로 되돌린다.
    돌려주는 것: (모델, 기록) — 기록에 history · best_epoch · stopped_epoch · mu · sd.
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    keep = [i for i in range(len(data["classes"])) if i != exclude]
    remap = np.full(len(data["classes"]), -1)
    remap[keep] = np.arange(len(keep))
    names = [data["classes"][i] for i in keep]
    K = len(keep)
    in_keep = np.isin(data["y"], keep)

    trm = data["tr"] & in_keep
    Ctr = to_tensor(data["C"][trm], device)
    ytr = torch.as_tensor(remap[data["y"][trm]], device=device)
    vam = data["va"] & in_keep
    Cva_np, yva_np = data["C"][vam], remap[data["y"][vam]]
    Cva, yva = to_tensor(Cva_np, device), torch.as_tensor(yva_np, device=device)
    # LOCO 검증용 '처음 보는 손모양' — 뺀 클래스의 train+val 샘플 (test 는 건드리지 않는다)
    Cunk = (data["C"][(data["tr"] | data["va"]) & (data["y"] == exclude)]
            if exclude is not None else None)

    # joint23 표준화 값은 **흔들기 전** 학습 데이터로 정한다 — 추론 때 입력은 흔들리지 않는다
    j_tr = joint23_torch(Ctr)
    mu, sd = j_tr.mean(0), j_tr.std(0) + 1e-8
    mu_np, sd_np = mu.cpu().numpy(), sd.cpu().numpy()

    cnt = torch.bincount(ytr, minlength=K).float()
    cls_w = cnt.sum() / (K * cnt.clamp_min(1))
    if CRITICAL in names:
        cls_w[names.index(CRITICAL)] *= critical_weight
    sw_all, sw_va = cls_w[ytr], cls_w[yva]
    Y_all, Y_va = torch.eye(K, device=device)[ytr], torch.eye(K, device=device)[yva]

    net = build_member(arch, K, size, activation, width, norm).to(device)
    lr = lr or (1e-3 if arch == "handformer" else 2e-3)
    wd = 0.05 if arch == "handformer" else 1e-4
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    plateau = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, factor=0.5, patience=lr_patience,
                                                         min_lr=1e-5)
    spe = max(1, (len(Ctr) + batch - 1) // batch)
    warm = 5 * spe
    adt = amp_dtype(device)
    scaler = torch.amp.GradScaler("cuda", enabled=adt is torch.float16)

    def forward(c):
        j = (joint23_torch(c) - mu) / sd
        return net(j) if arch == "mlp" else net(c, j)

    history = []
    best_loss, best_ep, best_state, stale = float("inf"), 0, None, 0
    min_epochs = anneal
    step = 0
    t0 = time.time()
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    ep = 0
    for ep in range(1, max_epochs + 1):
        lam = min(lam_max, ep / anneal * lam_max)
        net.train()
        perm = torch.randperm(len(Ctr), device=device)
        loss_sum, seen, correct = 0.0, 0, 0
        for i in range(0, len(Ctr), batch):
            b = perm[i:i + batch]
            if len(b) < 2:
                continue
            if step < warm:                                  # 처음 5 epoch 는 학습률을 천천히
                for g in opt.param_groups:
                    g["lr"] = lr * (step + 1) / warm
            step += 1
            c = augment(Ctr[b]) if aug else Ctr[b]
            with torch.autocast("cuda", dtype=adt or torch.float32, enabled=adt is not None):
                logits = forward(c)
            # EDL 손실은 fp32 로 — lgamma/digamma 가 bf16/fp16 에서 부정확하다
            loss = edl_mse_loss(logits.float(), Y_all[b], lam, sw_all[b], activation)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            scaler.step(opt)
            scaler.update()
            loss_sum += float(loss.detach()) * len(b)
            seen += len(b)
            correct += int((logits.detach().argmax(1) == ytr[b]).sum())

        # ---- epoch 기록 (val 만 본다)
        net.eval()
        with torch.no_grad():
            val_loss = float(edl_mse_loss(forward(Cva).float(), Y_va, lam_max, sw_va, activation))
        pred = EvidentialPredictor(arch, [net], names, mu_np, sd_np, activation, device)
        k = known_report(pred, Cva_np, yva_np)
        rec = {"epoch": ep, "lam": lam, "lr": opt.param_groups[0]["lr"],
               "train_loss": loss_sum / max(1, seen), "train_acc": correct / max(1, seen) * 100,
               "val_loss": val_loss, "val_acc": k["acc"], "val_auc_err": k["auc_err"],
               "val_reject": k["reject"], "val_u_median": k["u_median"]}
        if Cunk is not None:
            o = pred(Cunk)
            rec.update(ood_auc=_auc(k["_u"], o["u"]),
                       ood_block=float((o["u"] > o["b_max"]).mean() * 100),
                       ood_u_median=float(np.median(o["u"])))
        history.append(rec)

        # ---- early stopping (KL 가중치가 최대에 오른 뒤부터 판단)
        if ep >= min_epochs:
            if val_loss < best_loss * (1 - min_delta):
                best_loss, best_ep, stale = val_loss, ep, 0
                best_state = copy.deepcopy({kk: t.detach().cpu() for kk, t in net.state_dict().items()})
            else:
                stale += 1
            if ep > warm // spe:
                plateau.step(val_loss)
        if verbose and (ep % 10 == 0 or ep == 1):
            print(f"        epoch {ep:>3}  λ {lam:.2f}  lr {rec['lr']:.1e}  val 손실 {val_loss:.4f}  "
                  f"val 정답률 {rec['val_acc']:5.2f}%"
                  + (f"  OOD AUC {rec['ood_auc']:.3f}" if Cunk is not None else "")
                  + f"  ({time.time() - t0:.0f}초)", flush=True)
        if ep >= min_epochs and stale >= patience:
            break

    if best_state is None:                                    # 최소 epoch 전에 끝난 경우
        best_ep = ep
        best_state = {kk: t.detach().cpu() for kk, t in net.state_dict().items()}
    net.load_state_dict(best_state)                           # 최고점 가중치로 되돌린다
    net.eval()
    info = {"seconds": time.time() - t0, "params": count_params(net), "history": history,
            "best_epoch": best_ep, "stopped_epoch": ep, "best_val_loss": best_loss,
            "classes": names, "mu": mu_np, "sd": sd_np,
            "exclude": None if exclude is None else data["classes"][exclude]}
    if device.startswith("cuda"):
        info["peak_vram_mb"] = torch.cuda.max_memory_allocated() / 2**20
    if verbose:
        print(f"        -> 멈춤 epoch {ep} · 최고점 epoch {best_ep} (val 손실 {best_loss:.4f}) · "
              f"{info['seconds']:.0f}초", flush=True)
    return net, info


def at_best(info: dict, key: str) -> float:
    return float(info["history"][info["best_epoch"] - 1].get(key, float("nan")))


def summarize(members: list[dict], loco: list[dict]) -> dict:
    """설정 비교용 요약 — **val 만**, 각 run 의 최고점 epoch 기준."""
    s = {k: float(np.mean([at_best(m, k) for m in members]))
         for k in ("val_loss", "val_acc", "val_auc_err", "val_reject")}
    s["best_epoch_mean"] = float(np.mean([m["best_epoch"] for m in members]))
    s["stopped_epoch_mean"] = float(np.mean([m["stopped_epoch"] for m in members]))
    s["seconds_total"] = float(sum(m["seconds"] for m in members + loco))
    if loco:
        s["loco_auc"] = float(np.mean([at_best(i, "ood_auc") for i in loco]))
        s["loco_block"] = float(np.mean([at_best(i, "ood_block") for i in loco]))
        s["loco_per_class"] = {i["exclude"]: at_best(i, "ood_auc") for i in loco}
    return s


def run_config(data: dict, arch: str, device: str, n_members: int, do_loco: bool,
               verbose: bool = True, **kw):
    """한 설정을 통째로 — LOCO 7회 + 7종 멤버 n 개. (멤버 모델, 멤버 기록, LOCO 기록·모델, 요약)."""
    loco, loco_nets = [], []
    if do_loco:
        if verbose:
            print("\n  [한 클래스 빼기] 7종 중 하나씩 빼고 학습 — '처음 보는 손모양' 검증용")
        for c, name in enumerate(data["classes"]):
            net, info = train_member(data, arch, 0, device, exclude=c, verbose=False, **kw)
            loco.append(info)
            loco_nets.append(net.cpu())
            if verbose:
                print(f"    - {name:<8} 제외: 최고점 epoch {info['best_epoch']:>3}/{info['stopped_epoch']:>3}"
                      f"  val 정답률 {at_best(info, 'val_acc'):.2f}%  OOD AUC {at_best(info, 'ood_auc'):.3f}"
                      f"  ({info['seconds']:.0f}초)", flush=True)
    nets, infos = [], []
    for s in range(n_members):
        if verbose:
            print(f"\n  [멤버 {s + 1}/{n_members}] seed {s}")
        net, info = train_member(data, arch, s, device, verbose=verbose, **kw)
        nets.append(net.cpu())
        infos.append(info)
    return nets, infos, loco, loco_nets, summarize(infos, loco)


def loco_test(data: dict, arch: str, activation: str, loco: list[dict], loco_nets: list,
              device: str) -> dict:
    """LOCO 모델들을 **test** 에서 한 번 잰다 (--final 일 때만)."""
    per = {}
    for info, net in zip(loco, loco_nets):
        c = data["classes"].index(info["exclude"])
        keep = [i for i in range(len(data["classes"])) if i != c]
        pred = EvidentialPredictor(arch, [net], info["classes"], info["mu"], info["sd"],
                                   activation, device)
        kn = pred(data["C"][data["te"] & np.isin(data["y"], keep)])
        un = pred(data["C"][data["te"] & (data["y"] == c)])
        per[info["exclude"]] = {"auc": _auc(kn["u"], un["u"]),
                                "block": float((un["u"] > un["b_max"]).mean() * 100),
                                "n_unknown": int(len(un["u"]))}
    return {"mean_auc": float(np.mean([v["auc"] for v in per.values()])),
            "mean_block": float(np.mean([v["block"] for v in per.values()])), "per_class": per}


def strip(i: dict) -> dict:
    return {k: i[k] for k in ("params", "seconds", "exclude", "best_epoch", "stopped_epoch",
                              "best_val_loss", "history")} | {"peak_vram_mb": i.get("peak_vram_mb")}


def write_record(record: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    hp = REPORTS / f"history_{record['name']}.json"
    json.dump(record, open(hp, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    print(f"기록  {hp}")
    return hp


def finalize(data: dict, arch: str, size: str, activation: str, norm: str, aug: bool,
             nets: list, infos: list[dict], loco: list[dict], loco_nets: list, summ: dict,
             device: str) -> dict:
    """최종 모델 — 공개 test 를 **한 번** 재고 models/handformer_edl.pt 로 저장한다."""
    cfg = {"size": size, "drop": 0.1 if arch == "handformer" else 0.2, "width": 256,
           "norm": norm, "aug": aug, "best_epochs": [i["best_epoch"] for i in infos]}
    ens = EvidentialPredictor(arch, nets, data["classes"], infos[0]["mu"], infos[0]["sd"],
                              activation, device, cfg)
    # ---- 여기서 처음으로 공개 test 를 본다 (한 번만). 자체 촬영은 여전히 보지 않는다.
    kt = known_report(ens, data["C"][data["te"]], data["y"][data["te"]])
    test = {k: v for k, v in kt.items() if not k.startswith("_")}
    if loco:
        test["loco"] = loco_test(data, arch, activation, loco, loco_nets, device)
    print(f"\n  [공개 test] 정답률 {test['acc']:.2f}%  오답탐지 AUC {test['auc_err']:.3f}  "
          f"정상 오거부 {test['reject']:.1f}%"
          + (f"  LOCO OOD AUC {test['loco']['mean_auc']:.3f}  미지 차단 {test['loco']['mean_block']:.1f}%"
             if loco else ""))
    FINAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    cpu = EvidentialPredictor(arch, [n.cpu() for n in nets], data["classes"], infos[0]["mu"],
                              infos[0]["sd"], activation, "cpu", cfg)
    torch.save(cpu.to_bundle(n_train=int(data["tr"].sum()), summary_val=summ, test_public=test,
                             torch_version=torch.__version__), FINAL_OUT)
    print(f"\n저장  {FINAL_OUT}  ({FINAL_OUT.stat().st_size / 1e6:.2f} MB)")
    print("KPI 측정은 이 모델로 한 번만:  python scripts/evaluate_edl.py")
    return test


# ============================================================ 실행
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", choices=["handformer", "mlp"], default="handformer")
    ap.add_argument("--size", choices=sorted(SIZES), default="small")
    ap.add_argument("--members", type=int, default=3, help="딥 앙상블 멤버 수")
    ap.add_argument("--max-epochs", type=int, default=300, help="early stopping 의 안전 상한")
    ap.add_argument("--patience", type=int, default=15)
    ap.add_argument("--min-delta", type=float, default=1e-3, help="상대 개선 기준 (0.1%%)")
    ap.add_argument("--lr-patience", type=int, default=5)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--activation", choices=["relu", "softplus", "exp"], default="exp",
                    help="증거 활성 함수 — training/tune_evidential.py 가 공개 val 로 고른 값을 쓸 것")
    ap.add_argument("--lam-max", type=float, default=3.0)
    ap.add_argument("--anneal", type=int, default=30)
    ap.add_argument("--norm", choices=["layer", "batch", "none"], default="layer", help="MLP 만")
    ap.add_argument("--critical-weight", type=float, default=1.0)
    ap.add_argument("--no-aug", action="store_true", help="GPU 증강을 끈다 (비교용)")
    ap.add_argument("--no-loco", action="store_true", help="한 클래스 빼기를 건너뛴다")
    ap.add_argument("--final", action="store_true",
                    help="최종 모델: 공개 test 를 한 번 재고 models/handformer_edl.pt 로 저장")
    ap.add_argument("--name", default=None, help="기록 파일 이름 (reports/history_<name>.json)")
    ap.add_argument("--device", default="auto")
    args = ap.parse_args()

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    if device == "cuda":
        free, tot = torch.cuda.mem_get_info()
        print(f"장치: {torch.cuda.get_device_name(0)} · VRAM 여유 {free / 2**30:.2f}/{tot / 2**30:.2f} GB")
    else:
        print("장치: CPU (GPU 가 없거나 CUDA 빌드 torch 가 아니다)")

    data = load_data()
    print(f"공개 데이터 — 세션 {data['n_sessions']} · train {data['tr'].sum()} · "
          f"val {data['va'].sum()} · test {data['te'].sum()}  (자체 촬영은 읽지 않는다)")
    name = args.name or (f"{args.arch}" + (f"_{args.size}" if args.arch == "handformer" else "")
                         + ("_noaug" if args.no_aug else ""))
    print(f"설정 [{name}] 증거 {args.activation} · λmax {args.lam_max} · 증강 "
          f"{'끔' if args.no_aug else '켬'} · 멤버 {args.members}개 · early stopping "
          f"(patience {args.patience}, 상한 {args.max_epochs})")
    kw = dict(size=args.size, max_epochs=args.max_epochs, patience=args.patience,
              min_delta=args.min_delta, lr_patience=args.lr_patience, batch=args.batch,
              lr=args.lr, lam_max=args.lam_max, anneal=args.anneal, activation=args.activation,
              aug=not args.no_aug, norm=args.norm, critical_weight=args.critical_weight)

    nets, infos, loco, loco_nets, summ = run_config(data, args.arch, device, args.members,
                                                    not args.no_loco, **kw)
    print(f"\n  [val 요약] 정답률 {summ['val_acc']:.2f}%  오답탐지 AUC {summ['val_auc_err']:.3f}  "
          f"정상 오거부 {summ['val_reject']:.1f}%"
          + (f"  LOCO OOD AUC {summ['loco_auc']:.3f}  미지 차단 {summ['loco_block']:.1f}%" if loco else "")
          + f"\n             최고점 epoch 평균 {summ['best_epoch_mean']:.0f} · 멈춤 평균 "
          f"{summ['stopped_epoch_mean']:.0f} · 총 {summ['seconds_total']:.0f}초")

    record = {"name": name, "arch": args.arch, "size": args.size, "config": kw,
              "members": [strip(i) for i in infos], "loco": [strip(i) for i in loco],
              "summary_val": summ}

    if args.final:
        record["test_public"] = finalize(data, args.arch, args.size, args.activation, args.norm,
                                         not args.no_aug, nets, infos, loco, loco_nets, summ, device)

    write_record(record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
