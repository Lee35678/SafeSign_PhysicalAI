# -*- coding: utf-8 -*-
"""epoch 에 따라 무엇이 어떻게 변하는가 — 학습 기록(reports/history_*.json)으로 그린다.

    python scripts/plot_training.py                    # reports/history_*.json 전부 (final 제외)
    python scripts/plot_training.py mlp hf_small       # 이름으로 골라서

만드는 그림 (전부 **공개 데이터 val** — 자체 촬영은 KPI 측정용이라 쓰지 않는다)
  reports/training_curves.png   7종 모델, 시드마다 선 하나
      ① 학습 손실  ② val 손실(early stopping 감시 지표)  ③ val 정답률
      ④ val 오답탐지 AUC  ⑤ val 정상 오거부(u > max b)  ⑥ 학습률
      ● = 최고점(되돌린 가중치) · × = 멈춘 곳
  reports/loco_curves.png       한 클래스 빼기 — 뺀 클래스마다 패널 하나 + 평균 막대

패널마다 y축 하나 — 단위가 다른 지표를 한 축에 겹치지 않는다.
**test 는 그리지 않는다** — test 곡선을 보고 무언가를 고르면 test 를 선택에 쓰는 셈이다.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parent.parent
REPORTS = SERVICE_ROOT / "reports"

# dataviz 기준 팔레트 (밝은 면) — 범주 1~5번, 고정 순서. 선 그래프라 인접 쌍 기준으로 검증했다.
# 청록·노랑·분홍은 면 대비 3:1 미만 → 선마다 직접 라벨 + 표를 함께 낸다.
SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASE = "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
ORDER = ["mlp", "mlp_noaug", "hf_small", "hf_base", "hf_large"]
LABEL = {"mlp": "MLP", "mlp_noaug": "MLP (증강 끔)", "hf_small": "HandFormer-small",
         "hf_base": "HandFormer-base", "hf_large": "HandFormer-large"}
# 운영 게이트(코사인)의 한 클래스 빼기 AUC — feature/vision 에서 잰 값(이전 무작위 세션 분할)
BASELINE_OOD = 0.932


def _setup():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
        if any(f.name == name for f in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = name
            break
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10})
    return plt


def _style(ax, title):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", color=INK, fontsize=10.5, pad=7)
    ax.grid(True, axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASE)
    ax.tick_params(colors=MUTED, labelsize=8.5)


def _series(h, key):
    ep = np.array([r["epoch"] for r in h["history"]])
    v = np.array([r.get(key, np.nan) for r in h["history"]], dtype=float)
    return ep, v


def _end_labels(ax, ends):
    """선 끝 직접 라벨 — 글자는 잉크색, 색은 옆의 짧은 선이 맡는다. 겹치면 벌린다."""
    ends.sort()
    ylo, yhi = ax.get_ylim()
    gap, last = (yhi - ylo) * 0.075, -np.inf
    xmax = max(e[3] for e in ends)
    for y, name, col, _x in ends:
        yy = max(y, last + gap)
        last = yy
        ax.annotate(name, (xmax * 1.02, yy), color=INK, fontsize=8, va="center",
                    annotation_clip=False)
        ax.plot([xmax * 0.995, xmax * 1.015], [yy, yy], color=col, lw=2, clip_on=False,
                solid_capstyle="round")
    ax.set_xlim(0, xmax * 1.28)


def plot_members(plt, recs):
    panels = [("train_loss", "① 학습 손실 (EDL)", False),
              ("val_loss", "② val 손실 — early stopping 감시 지표 (λ = λmax 고정)", False),
              ("val_acc", "③ val 정답률 (%)", False),
              ("val_auc_err", "④ val 오답탐지 AUC — u 가 '틀릴 것'을 아는가", False),
              ("val_reject", "⑤ val 정상 자세 오거부 (%, u > max b)", False),
              ("lr", "⑥ 학습률 (정체되면 절반)", True)]
    fig, axes = plt.subplots(3, 2, figsize=(13.5, 11.5), sharex=True, facecolor=SURFACE)
    for ax, (key, title, logy) in zip(axes.flat, panels):
        _style(ax, title)
        if logy:
            from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter
            ax.set_yscale("log")
            # 로그 축 기본 눈금은 수식 글꼴을 써서 한글 글꼴에서 음수 기호가 깨진다 — 직접 쓴다
            ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"{v:.0e}"))
            ax.yaxis.set_minor_formatter(NullFormatter())
        ends = []
        for i, r in enumerate(recs):
            col = SERIES[i % len(SERIES)]
            longest = None
            for m in r["members"]:
                ep, v = _series(m, key)
                ax.plot(ep, v, color=col, lw=1.6, alpha=0.85, solid_capstyle="round",
                        label=LABEL.get(r["name"], r["name"]) if m is r["members"][0] else None)
                be = m["best_epoch"]
                if key in ("val_loss", "val_acc", "val_auc_err"):
                    ax.plot([be], [v[be - 1]], "o", ms=7, color=col, mec=SURFACE, mew=1.8, zorder=5)
                    ax.plot([ep[-1]], [v[-1]], "x", ms=6, color=col, mew=1.8, zorder=5)
                if longest is None or len(ep) > len(longest[0]):
                    longest = (ep, v)
            ends.append((float(longest[1][-1]), LABEL.get(r["name"], r["name"]), col,
                         float(longest[0][-1])))
        if not logy:
            _end_labels(ax, ends)
        else:
            ax.set_xlim(0, max(e[3] for e in ends) * 1.28)
    for ax in axes[-1]:
        ax.set_xlabel("epoch", color=INK2)
    anneal = recs[0]["config"].get("anneal", 30)
    for ax in axes.flat:
        ax.axvline(anneal, color=BASE, lw=1)
    axes[0, 1].annotate("여기서부터 멈춤 판단 (KL 가중치 최대)", (anneal, 1),
                        xycoords=("data", "axes fraction"), xytext=(4, -12),
                        textcoords="offset points", color=MUTED, fontsize=8)
    handles, labels = axes[0, 1].get_legend_handles_labels()
    # 범례는 제목 아래 줄에 — 구성이 많으면 제목과 겹친다
    fig.legend(handles, labels, loc="upper left", ncol=len(labels), frameon=False,
               labelcolor=INK, bbox_to_anchor=(0.008, 0.972), fontsize=9)
    fig.suptitle("epoch 에 따른 변화 (공개 데이터 val) — 선: 시드 하나 · ●: 최고점(되돌린 가중치) · ×: 멈춘 곳",
                 x=0.012, ha="left", y=0.995, color=INK, fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = REPORTS / "training_curves.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def plot_loco(plt, recs):
    recs = [r for r in recs if r.get("loco")]
    if not recs:
        return None
    classes = [l["exclude"] for l in recs[0]["loco"]]
    fig, axes = plt.subplots(2, 4, figsize=(15, 7.8), facecolor=SURFACE)
    for ax, cname in zip(axes.flat, classes):
        _style(ax, f"'{cname.replace('_', ' ')}' 을 뺐을 때 OOD AUC")
        ends = []
        for i, r in enumerate(recs):
            col = SERIES[i % len(SERIES)]
            run = next(l for l in r["loco"] if l["exclude"] == cname)
            ep, v = _series(run, "ood_auc")
            ax.plot(ep, v, color=col, lw=1.8, solid_capstyle="round",
                    label=LABEL.get(r["name"], r["name"]))
            be = run["best_epoch"]
            ax.plot([be], [v[be - 1]], "o", ms=7, color=col, mec=SURFACE, mew=1.8, zorder=5)
            ends.append((float(v[-1]), LABEL.get(r["name"], r["name"]), col, float(ep[-1])))
        ax.set_xlim(0, max(e[3] for e in ends) * 1.05)
    # 여덟 번째 칸 — 최고점 기준 평균, 가로 막대 (값 라벨은 잉크색)
    ax = axes.flat[len(classes)]
    _style(ax, "평균 (각 run 최고점 epoch 기준)")
    ax.grid(True, axis="x", color=GRID, linewidth=0.8)
    ax.grid(False, axis="y")
    means = [float(np.mean([l["history"][l["best_epoch"] - 1]["ood_auc"] for l in r["loco"]]))
             for r in recs]
    ys = np.arange(len(recs))[::-1]
    for i, (r, m) in enumerate(zip(recs, means)):
        # 가는 막대 (굵기 ≤ 24px) — 칸을 다 채우지 않고 나머지는 여백으로 둔다
        ax.barh(ys[i], m - 0.5, left=0.5, height=0.32, color=SERIES[i % len(SERIES)])
        ax.annotate(f"{m:.3f}", (m, ys[i]), xytext=(4, 0), textcoords="offset points",
                    va="center", color=INK, fontsize=8.5)
    ax.set_yticks(ys, [LABEL.get(r["name"], r["name"]) for r in recs], fontsize=8.5, color=INK)
    ax.axvline(BASELINE_OOD, color=INK2, lw=1, ls=(0, (4, 3)))
    ax.set_ylim(-0.8, len(recs) - 0.2)
    ax.annotate(f"운영 게이트 {BASELINE_OOD:.3f}", (BASELINE_OOD, 0), xycoords=("data", "axes fraction"),
                xytext=(-3, 3), textcoords="offset points", ha="right", va="bottom",
                color=INK2, fontsize=8)
    lo = min(means + [BASELINE_OOD]) - 0.03
    ax.set_xlim(max(0.5, lo), 1.0)
    for a in axes.flat[len(classes) + 1:]:
        a.axis("off")
    for a in axes[-1][:3]:
        a.set_xlabel("epoch", color=INK2)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper left", ncol=len(labels), frameon=False,
               labelcolor=INK, bbox_to_anchor=(0.008, 0.955), fontsize=9)
    fig.suptitle("한 클래스 빼기 — 6종으로 학습하고 뺀 1종을 '처음 보는 손모양'으로 넣었을 때 (공개 val) · ●: 최고점",
                 x=0.01, ha="left", y=0.995, color=INK, fontsize=11.5)
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    out = REPORTS / "loco_curves.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    return out


def main(names: list[str]) -> int:
    plt = _setup()
    paths = ([REPORTS / f"history_{n}.json" for n in names] if names else
             [Path(p) for p in sorted(glob.glob(str(REPORTS / "history_*.json")))
              if not Path(p).stem.endswith(("final", "_smoke"))])
    recs = [json.load(open(p, encoding="utf-8")) for p in paths if Path(p).exists()]
    if not recs:
        print("기록이 없습니다. 먼저: python training/select_model.py")
        return 1
    recs.sort(key=lambda r: ORDER.index(r["name"]) if r["name"] in ORDER else 99)
    REPORTS.mkdir(exist_ok=True)
    for out in (plot_members(plt, recs), plot_loco(plt, recs)):
        if out:
            print(f"저장  {out}")

    # 표 보기 — 색 없이도 읽히도록 같은 숫자를 글로도 남긴다
    print()
    print(f"  {'구성':<20}{'최고점/멈춤 epoch':>18}{'val 정답률':>11}{'오답탐지':>9}"
          f"{'정상 오거부':>11}{'LOCO AUC':>10}{'미지 차단':>10}")
    for r in recs:
        s = r["summary_val"]
        print(f"  {LABEL.get(r['name'], r['name']):<20}"
              f"{s['best_epoch_mean']:>11.0f}/{s['stopped_epoch_mean']:<6.0f}"
              f"{s['val_acc']:>10.2f}%{s['val_auc_err']:>9.3f}{s['val_reject']:>10.1f}%"
              f"{s.get('loco_auc', float('nan')):>10.3f}{s.get('loco_block', float('nan')):>9.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
