# -*- coding: utf-8 -*-
"""HandFormer — 관절 21개를 토큰으로 보는 Transformer + Evidential 머리.

왜 Transformer 인가
  joint23 은 사람이 고른 관계량 23개다(굽힘·폄·거리). 잘 작동하지만(+11.1%p) 사람이 떠올린
  관계만 담는다. 관절 21개를 각각 토큰으로 두면 **어떤 관절 쌍이 중요한지를 어텐션이 직접
  배운다.** 검증된 joint23 은 버리지 않고 옆 가지로 함께 넣는다 — 학습된 관계가 사람이 고른
  관계를 대체하는 게 아니라 보태도록.

왜 GPU 에서 증강하는가
  공개 데이터(ASL 사진)와 실제 사용자 사이에는 손 비율·정렬 오차·관절 떨림 차이가 있다.
  매 배치 새로 흔들어 주면 모델이 그 차이에 덜 민감해진다. 흔든 뒤 joint23 도 **GPU 에서
  다시 계산**해야 두 가지(토큰 / joint23)가 같은 손을 본다.

입력 좌표계
  normalize.normalize_landmarks 의 canonical 좌표(좌우손 통일·원점·크기·회전 정렬 완료).
  학습·추론이 반드시 같은 정규화를 거쳐야 한다.
"""
from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn as nn

from cognition.edl import ACTIVATIONS

N_JOINTS = 21
# normalize._FINGER_JOINTS 와 같다 (MCP/CMC -> PIP -> DIP -> TIP)
FINGER_CHAINS = ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12),
                 (13, 14, 15, 16), (17, 18, 19, 20))
TIPS = (4, 8, 12, 16, 20)
# 손 뼈대 트리의 부모 관절 (손목은 자기 자신)
PARENT = (0, 0, 1, 2, 3, 0, 5, 6, 7, 0, 9, 10, 11, 0, 13, 14, 15, 0, 17, 18, 19)
# 관절이 속한 손가락 (0~4, 손목=5)
FINGER_OF = (5, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4)

SIZES = {
    # 이름: (d_model, 층 수, 헤드 수, FFN 폭)            파라미터   권장 환경
    "small": (128, 4, 4, 256),     # 약 0.57M   노트북(4GB)
    "base": (192, 6, 6, 384),      # 약 1.87M   노트북 가능, Colab 권장
    "large": (256, 8, 8, 768),     # 약 5.42M   Colab (T4 16GB 이상)
}

_EPS = 1e-9


# ============================================================ joint23 (GPU)
def _cos(u: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
    num = (u * v).sum(-1)
    den = u.norm(dim=-1) * v.norm(dim=-1)
    return torch.where(den < _EPS, torch.zeros_like(num), num / den.clamp_min(_EPS))


def joint23_torch(canonical: torch.Tensor) -> torch.Tensor:
    """(B, 21, 3) -> (B, 23). normalize.joint_features 를 배치·GPU 로 옮긴 것.

    tests/test_handformer.py 가 두 구현이 같은 값을 내는지 확인한다.
    """
    c = canonical
    fj = torch.tensor(FINGER_CHAINS, device=c.device)
    wrist = c[:, 0:1]
    mcp, dip, tip = c[:, fj[:, 0]], c[:, fj[:, 2]], c[:, fj[:, 3]]
    bend = _cos(dip - mcp, tip - dip)
    ext = _cos(mcp - wrist, tip - mcp)
    tip_wrist = (tip - wrist).norm(dim=-1)
    gaps = (tip[:, :-1] - tip[:, 1:]).norm(dim=-1)
    thumb = (tip[:, 0:1] - tip[:, 1:]).norm(dim=-1)
    return torch.cat([bend, ext, tip_wrist, gaps, thumb], dim=1)


# ============================================================ 증강 (GPU)
def _random_rotation(n: int, max_deg: float, device) -> torch.Tensor:
    """축마다 ±max_deg 이내의 작은 회전 행렬 (n, 3, 3)."""
    a = (torch.rand(n, 3, device=device) * 2 - 1) * math.radians(max_deg)
    cx, cy, cz = a[:, 0].cos(), a[:, 1].cos(), a[:, 2].cos()
    sx, sy, sz = a[:, 0].sin(), a[:, 1].sin(), a[:, 2].sin()
    o, z = torch.ones_like(cx), torch.zeros_like(cx)
    rx = torch.stack([o, z, z, z, cx, -sx, z, sx, cx], 1).view(n, 3, 3)
    ry = torch.stack([cy, z, sy, z, o, z, -sy, z, cy], 1).view(n, 3, 3)
    rz = torch.stack([cz, -sz, z, sz, cz, z, z, z, o], 1).view(n, 3, 3)
    return rz @ ry @ rx


def augment(canonical: torch.Tensor, bone: float = 0.10, rot_deg: float = 10.0,
            jitter: float = 0.008) -> torch.Tensor:
    """canonical 손을 흔든다. 모든 연산이 배치 단위라 GPU 에서 거의 공짜다.

    bone     손가락마다 마디 길이를 ×U(1-bone, 1+bone) — 사람마다 다른 손 비율
    rot_deg  작은 회전 — 랜드마크 떨림 때문에 생기는 정렬 오차
    jitter   관절 좌표에 가우시안 잡음 — MediaPipe 추정 떨림
    """
    c = canonical.clone()
    n = c.shape[0]
    if bone > 0:
        s = 1 + (torch.rand(n, 5, device=c.device) * 2 - 1) * bone
        for f, chain in enumerate(FINGER_CHAINS):
            # 마디 방향은 그대로 두고 길이만 바꿔 손가락을 다시 세운다
            prev_old = c[:, chain[0]].clone()
            prev_new = c[:, chain[0]]
            for j in chain[1:]:
                old = c[:, j].clone()
                c[:, j] = prev_new + (old - prev_old) * s[:, f:f + 1]
                prev_old, prev_new = old, c[:, j]
    if rot_deg > 0:
        c = c @ _random_rotation(n, rot_deg, c.device).transpose(1, 2)
    if jitter > 0:
        c = c + torch.randn_like(c) * jitter
    return c


# ============================================================ 모델
class HandFormer(nn.Module):
    """토큰 = 관절 21개 (좌표 + 부모에서 뻗은 뼈 벡터) + 분류용 CLS 토큰 1개.

    CLS 출력과 joint23 가지를 합쳐 증거 logit 을 낸다. 마지막에 softmax 가 없다 —
    증거로 바꾸는 것은 edl.dirichlet() 이 한다.
    """

    arch = "handformer"

    def __init__(self, n_classes: int, size: str = "small", drop: float = 0.1,
                 activation: str = "exp", joint_dim: int = 23):
        super().__init__()
        if activation not in ACTIVATIONS:
            raise ValueError(f"알 수 없는 증거 활성 함수: {activation}")
        d, layers, heads, ff = SIZES[size]
        self.size, self.activation, self.n_classes = size, activation, n_classes
        self.register_buffer("parent", torch.tensor(PARENT), persistent=False)
        self.register_buffer("finger_of", torch.tensor(FINGER_OF), persistent=False)

        self.inp = nn.Linear(6, d)
        self.joint_emb = nn.Parameter(torch.randn(N_JOINTS, d) * 0.02)
        self.finger_emb = nn.Embedding(6, d)
        self.cls = nn.Parameter(torch.randn(1, 1, d) * 0.02)
        layer = nn.TransformerEncoderLayer(d, heads, ff, drop, activation="gelu",
                                           batch_first=True, norm_first=True)
        self.encoder = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.out_norm = nn.LayerNorm(d)
        self.joint_branch = nn.Sequential(nn.Linear(joint_dim, d), nn.GELU(), nn.LayerNorm(d))
        self.head = nn.Sequential(nn.LayerNorm(2 * d), nn.Linear(2 * d, d), nn.GELU(),
                                  nn.Dropout(drop), nn.Linear(d, n_classes))

    def forward(self, canonical: torch.Tensor, joint23: torch.Tensor) -> torch.Tensor:
        """canonical (B,21,3), joint23 (B,23, 표준화된 값) -> logit (B,K)."""
        bone_vec = canonical - canonical[:, self.parent]
        tok = self.inp(torch.cat([canonical, bone_vec], -1))
        tok = tok + self.joint_emb + self.finger_emb(self.finger_of)
        tok = torch.cat([self.cls.expand(tok.shape[0], -1, -1), tok], 1)
        h = self.out_norm(self.encoder(tok)[:, 0])
        return self.head(torch.cat([h, self.joint_branch(joint23)], -1))


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def to_tensor(a: np.ndarray, device) -> torch.Tensor:
    return torch.as_tensor(np.ascontiguousarray(a), dtype=torch.float32, device=device)
