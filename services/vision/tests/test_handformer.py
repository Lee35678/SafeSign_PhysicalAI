# -*- coding: utf-8 -*-
"""HandFormer 경로 — GPU 판 특징이 원본과 같은가, 증강이 손을 망가뜨리지 않는가."""
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cognition.evidential import EvidentialPredictor, load_predictor  # noqa: E402
from cognition.handformer import (  # noqa: E402
    FINGER_CHAINS, HandFormer, augment, joint23_torch,
)
from cognition.normalize import joint_features, normalize_landmarks  # noqa: E402

_passed = []


def _hands(n=16, seed=0):
    """정규화까지 거친 그럴듯한 손 n개."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n):
        pts = rng.normal(0, 0.05, (21, 3))
        pts[9] += [0, 0.5, 0]
        for f, ch in enumerate(FINGER_CHAINS):
            for k, j in enumerate(ch):
                pts[j] += [(f - 2) * 0.12, 0.2 + 0.15 * k * rng.uniform(0.2, 1.0), 0]
        out.append(normalize_landmarks(pts, handedness="Right"))
    return np.asarray(out, dtype=np.float32)


def test_joint23_torch_matches_numpy():
    """학습(GPU)과 서비스(numpy)가 같은 특징을 봐야 한다 — train-serve skew 방지."""
    C = _hands()
    ref = np.stack([joint_features(c) for c in C])
    got = joint23_torch(torch.tensor(C)).numpy()
    assert np.allclose(ref, got, atol=1e-5), np.abs(ref - got).max()


def test_augment_keeps_shape_and_changes_hand():
    C = torch.tensor(_hands())
    A = augment(C)
    assert A.shape == C.shape and torch.isfinite(A).all()
    assert not torch.allclose(A, C)


def test_bone_scaling_keeps_bone_directions():
    """뼈 길이만 바뀌고 방향은 그대로여야 한다 (회전·잡음을 끄면)."""
    C = torch.tensor(_hands())
    A = augment(C, bone=0.1, rot_deg=0, jitter=0)
    for ch in FINGER_CHAINS:
        for a, b in zip(ch[:-1], ch[1:]):
            d0 = C[:, b] - C[:, a]
            d1 = A[:, b] - A[:, a]
            cos = (d0 * d1).sum(-1) / (d0.norm(dim=-1) * d1.norm(dim=-1))
            assert (cos > 0.9999).all(), cos.min()


def test_no_augment_is_identity():
    C = torch.tensor(_hands())
    assert torch.allclose(augment(C, bone=0, rot_deg=0, jitter=0), C)


def test_handformer_forward():
    for size in ("small", "base"):
        m = HandFormer(7, size=size).eval()
        C = torch.tensor(_hands(4))
        out = m(C, torch.randn(4, 23))
        assert out.shape == (4, 7)


def test_predictor_roundtrip_and_ensemble():
    """저장 -> 복원이 같은 출력을 내고, 앙상블 증거가 멤버 평균이어야 한다."""
    torch.manual_seed(0)
    members = [HandFormer(7, "small").eval() for _ in range(2)]
    mu, sd = np.zeros(23, np.float32), np.ones(23, np.float32)
    pred = EvidentialPredictor("handformer", members, list("abcdefg"), mu, sd, "exp")
    C = _hands(8)
    a = pred(C)
    assert np.allclose(a["b"].sum(1) + a["u"], 1.0, atol=1e-5)   # sum(b) + u = 1
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "m.pt"
        torch.save(pred.to_bundle(), path)
        b = load_predictor(path)(C)
    assert np.allclose(a["u"], b["u"], atol=1e-6)
    ct = torch.tensor(C)
    e_each = [EvidentialPredictor("handformer", [m], list("abcdefg"), mu, sd, "exp").evidence(ct)
              for m in members]
    assert torch.allclose(pred.evidence(ct), torch.stack(e_each).mean(0), atol=1e-5)


for _n, _f in sorted(globals().copy().items()):
    if _n.startswith("test_") and callable(_f):
        _f()
        _passed.append(_n)
        print(f"  ok  {_n}")
print(f"{len(_passed)}개 통과")
