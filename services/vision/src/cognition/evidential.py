# -*- coding: utf-8 -*-
"""Evidential 모델의 공통 추론 인터페이스 — 구조(MLP/HandFormer)와 앙상블을 한 곳에서.

학습·평가·웹캠 확인·서비스가 **모두 이 클래스로** 추론한다. 경로마다 따로 계산하면
정규화나 증거 활성 함수가 어긋나 조용히 틀린 판정이 나온다(train-serve skew).

앙상블은 **증거를 평균**한다.
  e = mean_m e_m,  alpha = e + 1
  멤버들이 서로 다른 클래스에 증거를 내면 평균 증거가 흩어져 max b 가 작아지고,
  모두 증거를 못 내면 u 가 그대로 높게 남는다. 즉 "의견 불일치"도 거부 쪽으로 작용한다.

번들 형식 (torch.save 한 dict)
  arch         "mlp" | "handformer"
  members      state_dict 리스트 (앙상블 멤버)
  config       구조를 되살리는 데 필요한 값 (size, width, drop, norm ...)
  classes      클래스 이름 (학습 순서)
  mu, sd       joint23 표준화 값 (학습 데이터 기준)
  activation   증거 활성 함수
  feature_mode "joint23"
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import torch

from cognition.edl import EvidentialNet, evidence_fn
from cognition.handformer import HandFormer, joint23_torch, to_tensor


class EvidentialPredictor:
    def __init__(self, arch: str, members: Sequence[torch.nn.Module], classes: list[str],
                 mu: np.ndarray, sd: np.ndarray, activation: str, device: str = "cpu",
                 config: dict | None = None):
        self.arch = arch
        self.members = [m.to(device).eval() for m in members]
        self.classes = list(classes)
        self.mu = to_tensor(mu, device)
        self.sd = to_tensor(sd, device)
        self.activation = activation
        self.device = device
        self.config = dict(config or {})

    # ------------------------------------------------------------ 추론
    @torch.no_grad()
    def evidence(self, canonical: torch.Tensor) -> torch.Tensor:
        """canonical (N,21,3) 텐서 -> 멤버 평균 증거 (N,K)."""
        j = (joint23_torch(canonical) - self.mu) / self.sd
        ev = []
        for m in self.members:
            logits = m(j) if self.arch == "mlp" else m(canonical, j)
            ev.append(evidence_fn(logits.float(), self.activation))
        return torch.stack(ev).mean(0)

    @torch.no_grad()
    def __call__(self, canonical: np.ndarray, batch: int = 4096) -> dict:
        """canonical (N,21,3) numpy -> {pred, p, u, b_max, b} numpy."""
        c = np.asarray(canonical, dtype=np.float32).reshape(-1, 21, 3)
        outs = []
        for i in range(0, len(c), batch):
            outs.append(self.evidence(to_tensor(c[i:i + batch], self.device)))
        e = torch.cat(outs) if outs else torch.zeros(0, len(self.classes))
        K = e.shape[-1]
        S = (e + 1.0).sum(-1, keepdim=True)
        p = (e + 1.0) / S
        b = e / S
        u = (K / S).squeeze(-1)
        return {"pred": p.argmax(1).cpu().numpy(), "p": p.cpu().numpy(),
                "u": u.cpu().numpy(), "b": b.cpu().numpy(),
                "b_max": b.max(1).values.cpu().numpy()}

    # ------------------------------------------------------------ 저장/복원
    def to_bundle(self, **extra) -> dict:
        return {"arch": self.arch, "members": [m.state_dict() for m in self.members],
                "config": self.config, "classes": self.classes,
                "mu": self.mu.cpu().numpy(), "sd": self.sd.cpu().numpy(),
                "activation": self.activation, "feature_mode": "joint23", **extra}

    @classmethod
    def from_bundle(cls, raw: dict, device: str = "cpu") -> "EvidentialPredictor":
        classes = list(raw["classes"])
        mu = np.asarray(raw["mu"], dtype=np.float32)
        sd = np.asarray(raw["sd"], dtype=np.float32)
        act = str(raw.get("activation", "softplus"))
        cfg = dict(raw.get("config") or {})
        members = []
        for sdict in raw["members"]:
            if raw["arch"] == "mlp":
                m = EvidentialNet(len(mu), len(classes), int(cfg.get("width", 256)),
                                  float(cfg.get("drop", 0.2)), str(cfg.get("norm", "layer")), act)
            elif raw["arch"] == "handformer":
                m = HandFormer(len(classes), str(cfg.get("size", "small")),
                               float(cfg.get("drop", 0.1)), act)
            else:
                raise ValueError(f"알 수 없는 구조: {raw['arch']}")
            m.load_state_dict(sdict)
            members.append(m)
        return cls(raw["arch"], members, classes, mu, sd, act, device, cfg)


def load_predictor(path: str | Path, device: str = "cpu") -> EvidentialPredictor:
    raw = torch.load(path, weights_only=False, map_location="cpu")
    return EvidentialPredictor.from_bundle(raw, device)
