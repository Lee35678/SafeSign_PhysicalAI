# -*- coding: utf-8 -*-
"""모델 고르기 전 과정을 한 번에 — 설정 → 구조 → 최종. **공개 데이터만** 쓴다.

    python training/select_model.py --profile local     # 노트북 (RTX 3050 Ti 4GB 기준 ~75분)
    python training/select_model.py --profile colab     # Colab (T4 이상, 더 무거운 비교)
    python training/select_model.py --stage arch        # 한 단계만

왜 설정부터 다시 고르는가
  이전 기본값(증거 exp · λmax 3 · LayerNorm · 치명가중치 1)은 **KPI 데이터(JH·me01)를 보고**
  고른 값이었다. 코드는 공개 데이터만 읽어도 설정이 오염돼 있으면 소용없다. 그래서 공개 val 로
  처음부터 다시 고른다.

단계
  1 settings  MLP 로 손실·머리 설정을 고른다 (싸서 많이 돌릴 수 있다)
              증거 활성 {softplus, exp, relu} × λmax {1, 3} × 정규화 {layer, batch} × 치명가중치 {1, 10}
  2 arch      고른 설정으로 구조를 비교한다
              local: MLP · MLP(증강 끔) · HandFormer-small · HandFormer-base
              colab: 위 + HandFormer-large, 그리고 HandFormer-small 에서 활성·λ 를 다시 확인
  3 final     고른 구조로 멤버 5개를 학습 → 공개 test 1회 → models/handformer_edl.pt

선택 규칙 (결과를 보기 **전에** 정했다 — 모든 단계에서 같다)
  ① val 정답률이 최고치에서 1%p 이내인 후보만 남긴다        (분류를 망가뜨리지 않기)
  ② 그중 한 클래스 빼기(LOCO) 검증 OOD AUC 가 가장 높은 것을 고른다  ("7종 밖"을 가장 잘 아는 것)
  공개 test 는 3단계에서 최종 모델에 대해 한 번만 본다. 자체 촬영은 끝까지 보지 않는다.

이어서 돌리기
  단계 결과를 reports/ 에 바로바로 쓴다. 다시 실행하면 **끝난 조합·구조는 건너뛴다.**
  Colab 세션이 끊겨도 같은 명령을 다시 실행하면 된다 (Drive 에 풀어 두었다면).
  처음부터 다시 하려면 --fresh.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT / "src"))
sys.path.insert(0, str(SERVICE_ROOT / "training"))

import torch  # noqa: E402

from train_handformer import (  # noqa: E402
    REPORTS, finalize, load_data, run_config, strip, write_record,
)

VAL_ACC_MARGIN = 1.0

PROFILES = {
    "local": {"grid_members": 1, "arch_members": 3, "final_members": 5, "patience": 15,
              "archs": ["mlp", "mlp_noaug", "hf_small", "hf_base"], "hf_recheck": False},
    "colab": {"grid_members": 2, "arch_members": 3, "final_members": 5, "patience": 20,
              "archs": ["mlp", "mlp_noaug", "hf_small", "hf_base", "hf_large"], "hf_recheck": True},
}
ARCHS = {
    "mlp": ("mlp", "small", True),
    "mlp_noaug": ("mlp", "small", False),
    "hf_small": ("handformer", "small", True),
    "hf_base": ("handformer", "base", True),
    "hf_large": ("handformer", "large", True),
}
GRID = {"activation": ["softplus", "exp", "relu"], "lam_max": [1.0, 3.0],
        "norm": ["layer", "batch"], "critical_weight": [1.0, 10.0]}


def pick(results: dict[str, dict]) -> str:
    """선택 규칙 ①② — 결과 dict(이름 -> val 요약) 에서 하나를 고른다."""
    best_acc = max(r["val_acc"] for r in results.values())
    cand = {k: r for k, r in results.items() if r["val_acc"] >= best_acc - VAL_ACC_MARGIN}
    return max(cand, key=lambda k: cand[k].get("loco_auc", float("-inf")))


def show(results: dict[str, dict], chosen: str, title: str) -> None:
    best_acc = max(r["val_acc"] for r in results.values())
    print(f"\n  {title}")
    print(f"  {'':<34}{'val 정답률':>11}{'LOCO AUC':>10}{'미지 차단':>10}{'정상 오거부':>11}"
          f"{'최고/멈춤 epoch':>16}")
    for k, r in sorted(results.items(), key=lambda kv: -kv[1].get("loco_auc", 0)):
        mark = "  ← 선택" if k == chosen else ("" if r["val_acc"] >= best_acc - VAL_ACC_MARGIN
                                               else "  (정답률 조건 탈락)")
        print(f"  {k:<34}{r['val_acc']:>10.2f}%{r.get('loco_auc', float('nan')):>10.3f}"
              f"{r.get('loco_block', float('nan')):>9.1f}%{r['val_reject']:>10.1f}%"
              f"{r['best_epoch_mean']:>9.0f}/{r['stopped_epoch_mean']:<6.0f}{mark}")


def load_json(p: Path) -> dict:
    return json.load(open(p, encoding="utf-8")) if p.exists() else {}


def save_json(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    json.dump(obj, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)


# ============================================================ 단계
def stage_settings(data, device, prof, fresh) -> dict:
    path = REPORTS / "select_settings.json"
    state = {} if fresh else load_json(path)
    results = state.get("results", {})
    combos = list(itertools.product(*GRID.values()))
    print(f"\n[1/3] 설정 고르기 — MLP · {len(combos)}조합 · 멤버 {prof['grid_members']}개 + LOCO 7회"
          f" (끝난 것 {len(results)}개 건너뜀)")
    for combo in combos:
        cfg = dict(zip(GRID, combo))
        key = f"{cfg['activation']}·λ{cfg['lam_max']:g}·{cfg['norm']}·치명{cfg['critical_weight']:g}"
        if key in results:
            continue
        t0 = time.time()
        *_, summ = run_config(data, "mlp", device, prof["grid_members"], True, verbose=False,
                              aug=True, patience=prof["patience"], **cfg)
        summ["config"] = cfg
        results[key] = summ
        save_json(path, {"results": results})
        print(f"    {key:<32} val 정답률 {summ['val_acc']:.2f}%  LOCO AUC {summ['loco_auc']:.3f}"
              f"  ({time.time() - t0:.0f}초)", flush=True)
    chosen = pick(results)
    show(results, chosen, "설정 결과 (LOCO AUC 순)")
    state = {"results": results, "chosen": chosen, "config": results[chosen]["config"]}
    save_json(path, state)
    return state["config"]


def stage_hf_recheck(data, device, prof, base_cfg, fresh) -> dict:
    """Colab 전용 — MLP 에서 고른 활성·λ 가 HandFormer 에도 맞는지 small 로 다시 확인한다."""
    path = REPORTS / "select_settings_hf.json"
    state = {} if fresh else load_json(path)
    results = state.get("results", {})
    combos = list(itertools.product(["softplus", "exp"], [1.0, 3.0]))
    print(f"\n[1+/3] HandFormer-small 에서 활성·λ 재확인 — {len(combos)}조합")
    for act, lam in combos:
        key = f"{act}·λ{lam:g}"
        if key in results:
            continue
        t0 = time.time()
        cfg = dict(base_cfg, activation=act, lam_max=lam)
        *_, summ = run_config(data, "handformer", device, prof["grid_members"], True,
                              verbose=False, size="small", aug=True, patience=prof["patience"],
                              **{k: v for k, v in cfg.items() if k != "norm"})
        summ["config"] = cfg
        results[key] = summ
        save_json(path, {"results": results})
        print(f"    {key:<10} val 정답률 {summ['val_acc']:.2f}%  LOCO AUC {summ['loco_auc']:.3f}"
              f"  ({time.time() - t0:.0f}초)", flush=True)
    chosen = pick(results)
    show(results, chosen, "HandFormer-small 재확인 결과")
    save_json(path, {"results": results, "chosen": chosen, "config": results[chosen]["config"]})
    return results[chosen]["config"]


def stage_arch(data, device, prof, cfg_mlp, cfg_hf, fresh) -> str:
    print(f"\n[2/3] 구조 비교 — {', '.join(prof['archs'])} · 멤버 {prof['arch_members']}개 + LOCO 7회")
    results = {}
    for name in prof["archs"]:
        arch, size, aug = ARCHS[name]
        cfg = dict(cfg_mlp if arch == "mlp" else {k: v for k, v in cfg_hf.items() if k != "norm"})
        kw = dict(cfg, size=size, aug=aug, patience=prof["patience"])
        hp = REPORTS / f"history_{name}.json"
        old = {} if fresh else load_json(hp)
        if old.get("config_key") == json.dumps(kw, sort_keys=True) and \
                len(old.get("members", [])) == prof["arch_members"]:
            results[name] = old["summary_val"]
            print(f"    {name:<10} 건너뜀 (기록 있음)")
            continue
        t0 = time.time()
        print(f"    {name:<10} 학습 중 ...", flush=True)
        nets, infos, loco, _ln, summ = run_config(data, arch, device, prof["arch_members"], True,
                                                  verbose=True, **kw)
        write_record({"name": name, "arch": arch, "size": size, "config": kw,
                      "config_key": json.dumps(kw, sort_keys=True),
                      "members": [strip(i) for i in infos], "loco": [strip(i) for i in loco],
                      "summary_val": summ})
        results[name] = summ
        print(f"    {name:<10} val 정답률 {summ['val_acc']:.2f}%  LOCO AUC {summ['loco_auc']:.3f}"
              f"  파라미터 {infos[0]['params']:,}  ({time.time() - t0:.0f}초)", flush=True)
    chosen = pick(results)
    show(results, chosen, "구조 결과 (LOCO AUC 순)")
    save_json(REPORTS / "select_arch.json", {"results": results, "chosen": chosen})
    return chosen


def stage_final(data, device, prof, name, cfg_mlp, cfg_hf) -> dict:
    arch, size, aug = ARCHS[name]
    cfg = dict(cfg_mlp if arch == "mlp" else {k: v for k, v in cfg_hf.items() if k != "norm"})
    kw = dict(cfg, size=size, aug=aug, patience=prof["patience"])
    print(f"\n[3/3] 최종 모델 — {name} · 멤버 {prof['final_members']}개 + LOCO 7회 · 설정 {cfg}")
    # 이 단계는 중간 저장이 없다 — 살아 있는지 보이도록 run 마다 진행을 찍는다
    nets, infos, loco, loco_nets, summ = run_config(data, arch, device, prof["final_members"], True,
                                                    verbose=True, **kw)
    test = finalize(data, arch, size, cfg["activation"], cfg.get("norm", "layer"), aug,
                    nets, infos, loco, loco_nets, summ, device)
    write_record({"name": "final", "arch": arch, "size": size, "config": kw,
                  "members": [strip(i) for i in infos], "loco": [strip(i) for i in loco],
                  "summary_val": summ, "test_public": test})
    return test


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", choices=sorted(PROFILES), default="local")
    ap.add_argument("--stage", choices=["all", "settings", "arch", "final"], default="all")
    ap.add_argument("--fresh", action="store_true", help="이전 기록을 무시하고 처음부터")
    args = ap.parse_args()
    prof = PROFILES[args.profile]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        free, tot = torch.cuda.mem_get_info()
        cap = torch.cuda.get_device_capability()
        print(f"장치: {torch.cuda.get_device_name(0)} (sm{cap[0]}{cap[1]}) · VRAM 여유 "
              f"{free / 2**30:.1f}/{tot / 2**30:.1f} GB · torch {torch.__version__}")
    else:
        print("⚠️ GPU 없음 — CPU 로 돈다(매우 느리다). Colab 이면 런타임 유형을 GPU 로 바꿀 것")
    data = load_data()
    print(f"공개 데이터 — train {data['tr'].sum()} · val {data['va'].sum()} · test {data['te'].sum()}"
          f"  (자체 촬영은 읽지 않는다) · 프로필 {args.profile}")
    t0 = time.time()

    if args.stage in ("all", "settings"):
        cfg_mlp = stage_settings(data, device, prof, args.fresh)
    else:
        cfg_mlp = load_json(REPORTS / "select_settings.json").get("config")
        if not cfg_mlp:
            print("설정 단계 결과가 없습니다 — 먼저 --stage settings")
            return 1
    cfg_hf = dict(cfg_mlp)
    if prof["hf_recheck"] and args.stage in ("all", "settings"):
        cfg_hf = stage_hf_recheck(data, device, prof, cfg_mlp, args.fresh)
    elif prof["hf_recheck"]:
        cfg_hf = load_json(REPORTS / "select_settings_hf.json").get("config", cfg_mlp)
    if args.stage == "settings":
        return 0

    if args.stage in ("all", "arch"):
        name = stage_arch(data, device, prof, cfg_mlp, cfg_hf, args.fresh)
    else:
        name = load_json(REPORTS / "select_arch.json").get("chosen")
        if not name:
            print("구조 단계 결과가 없습니다 — 먼저 --stage arch")
            return 1
    if args.stage == "arch":
        return 0

    test = stage_final(data, device, prof, name, cfg_mlp, cfg_hf)
    save_json(REPORTS / "selection.json", {
        "profile": args.profile, "settings_mlp": cfg_mlp, "settings_hf": cfg_hf,
        "arch": name, "test_public": test, "torch": torch.__version__,
        "device": torch.cuda.get_device_name(0) if device == "cuda" else "cpu",
        "minutes": (time.time() - t0) / 60})
    print(f"\n끝 — 총 {(time.time() - t0) / 60:.0f}분. 그래프: python scripts/plot_training.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
