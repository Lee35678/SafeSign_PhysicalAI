# -*- coding: utf-8 -*-
"""실제 촬영 데이터 — 촬영자 단위로 나눠 읽고 채점한다.

왜 촬영자로 나누는가
  자체 촬영(정상 7종 + 애매한 자세)은 거부 설계를 고르는 유일한 실제 데이터다. 이걸로 고르고
  이걸로 채점하면 11 §8-6 과 같은 함정이 된다. 그래서
      검증(val)  = 한 촬영자   — 활성 함수·구조·epoch 를 고르는 데만 쓴다
      시험(test) = 다른 촬영자 — 마지막에 한 번만 본다
  웹캠 로그는 라벨·촬영자가 없어 시험 전용이다.
"""
from __future__ import annotations

import collections
import glob
import json
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from cognition.normalize import landmarks_to_array, normalize_landmarks

SERVICE_ROOT = Path(__file__).resolve().parent.parent.parent
SELF = SERVICE_ROOT.parent / "data" / "datasets" / "self_recorded"
LOGS = SERVICE_ROOT / "logs"
SIGN7 = ["정지", "서행", "좌회전_유도", "우회전_유도", "확인_완료", "후진", "주의"]
AMBIGUOUS = "애매한자세"


def canon(landmarks, handedness) -> np.ndarray:
    return normalize_landmarks(landmarks_to_array(landmarks), handedness=handedness)


def load_logs() -> np.ndarray:
    out = []
    for p in sorted(glob.glob(str(LOGS / "*.jsonl"))):
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except Exception:
                continue
            lm = d.get("landmarks") or d.get("world_landmarks")
            if d.get("record") == "header" or not lm:
                continue
            out.append(canon(lm, d.get("handedness", "Right")))
    return np.asarray(out, dtype=np.float32).reshape(-1, 21, 3)


class RealData:
    """자체 촬영(선택한 촬영자만) + 선택적으로 웹캠 로그. 한 번 읽고 여러 모델을 채점한다."""

    def __init__(self, subjects: Optional[Iterable[str]] = None, with_logs: bool = True):
        subjects = set(subjects) if subjects else None
        self.clean, self.amb = [], []
        for p in sorted(glob.glob(str(SELF / "*" / "*.json"))):
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            c = d["class_name"]
            sub = d.get("subject_id", "?")
            if (c not in SIGN7 and c != AMBIGUOUS) or (subjects and sub not in subjects):
                continue
            rec = {"c": canon(d["landmarks"], d.get("handedness", "Right")), "sub": sub,
                   "take": (d.get("source") or {}).get("take"),
                   "true": None if c == AMBIGUOUS else c}
            (self.clean if rec["true"] else self.amb).append(rec)
        self.subjects = sorted({r["sub"] for r in self.clean + self.amb})
        self.CC = np.stack([r["c"] for r in self.clean]).astype(np.float32)
        self.AC = (np.stack([r["c"] for r in self.amb]).astype(np.float32)
                   if self.amb else np.zeros((0, 21, 3), np.float32))
        self.LC = load_logs() if with_logs else np.zeros((0, 21, 3), np.float32)
        self.clean_tk = collections.defaultdict(list)
        for i, r in enumerate(self.clean):
            self.clean_tk[(r["sub"], r["true"], r["take"])].append(i)
        self.amb_tk = collections.defaultdict(list)
        for i, r in enumerate(self.amb):
            self.amb_tk[(r["sub"], r["take"])].append(i)

    def describe(self) -> str:
        return (f"촬영자 {','.join(self.subjects)} · 정상 {len(self.clean_tk)}테이크({len(self.CC)}프레임)"
                f" · 애매 {len(self.amb_tk)}테이크({len(self.AC)}프레임)"
                + (f" · 웹캠 {len(self.LC)}프레임" if len(self.LC) else ""))

    def _kpi(self, pred_names, rejected):
        ok = bad = rej = crit = 0
        for key, ids in self.clean_tk.items():
            v = [pred_names[i] for i in ids if not rejected[i]]
            if not v:
                rej += 1
                continue
            w = collections.Counter(v).most_common(1)[0][0]
            if w == key[1]:
                ok += 1
            else:
                bad += 1
                crit += key[1] == "정지"
        n = max(1, len(self.clean_tk))
        return ok / n * 100, bad / n * 100, rej / n * 100, crit

    def quick(self, predictor) -> dict:
        """epoch 마다 부를 가벼운 채점 (웹캠 로그 제외). 임계값 없는 규칙 u > max b."""
        oc, oa = predictor(self.CC), predictor(self.AC)
        names = np.array(predictor.classes)[oc["pred"]]
        res = {"clean_acc": float((names == np.array([r["true"] for r in self.clean])).mean() * 100),
               "u_clean": float(np.median(oc["u"])),
               "u_amb": float(np.median(oa["u"])) if len(oa["u"]) else float("nan")}
        rc, ra = oc["u"] > oc["b_max"], oa["u"] > oa["b_max"]
        res["clean_reject"] = float(rc.mean() * 100)
        res["amb_block"] = (sum(all(ra[i] for i in ids) for ids in self.amb_tk.values())
                            / max(1, len(self.amb_tk)) * 100)
        try:
            from sklearn.metrics import roc_auc_score
            res["auc_ood"] = float(roc_auc_score(
                np.r_[np.zeros(len(oc["u"])), np.ones(len(oa["u"]))], np.r_[oc["u"], oa["u"]]))
        except Exception:
            res["auc_ood"] = float("nan")
        return res

    def score(self, predictor) -> dict:
        """최종 채점 — KPI 행 여러 개(임계값 없는 규칙 + 참고용 스윕) + 웹캠."""
        oc, oa, ol = predictor(self.CC), predictor(self.AC), predictor(self.LC)
        names = np.array(predictor.classes)[oc["pred"]]
        res = self.quick(predictor)
        rows = []
        for label, rc, ra, rl in [
            ("u > max b  (임계값 없음)", oc["u"] > oc["b_max"], oa["u"] > oa["b_max"],
             ol["u"] > ol["b_max"]),
            *[(f"u > {t:.1f}  (참고)", oc["u"] > t, oa["u"] > t, ol["u"] > t)
              for t in (0.2, 0.3, 0.4, 0.5)],
        ]:
            a, bd, rj, cr = self._kpi(names, rc)
            ab = (sum(all(ra[i] for i in ids) for ids in self.amb_tk.values())
                  / max(1, len(self.amb_tk)) * 100)
            lv = float(rl.mean() * 100) if len(rl) else float("nan")
            rows.append((label, a, bd, rj, cr, ab, lv))
        res["rows"] = rows
        res["u_median"] = (res["u_clean"], res["u_amb"],
                           float(np.median(ol["u"])) if len(ol["u"]) else float("nan"))
        return res
