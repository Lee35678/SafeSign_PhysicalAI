# -*- coding: utf-8 -*-
"""EDL 의 수학이 맞는지 — 디리클레 항등식과 거부 규칙."""
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cognition.edl import (  # noqa: E402
    REJECT_RULE_RELATIVE, REJECT_RULE_THRESHOLD, EvidentialNet, dirichlet,
    edl_mse_loss, kl_dirichlet_uniform, reject_mask,
)

_passed = []


def check(name, fn):
    fn()
    _passed.append(name)
    print(f"  ok  {name}")


def test_belief_and_uncertainty_sum_to_one():
    """sum(b) + u = 1 — EDL 의 핵심 항등식. **p 가 아니라 b 에 대해** 성립한다."""
    _a, _S, p, u, b = dirichlet(torch.randn(32, 7))
    total = b.sum(-1) + u.squeeze(-1)
    assert torch.allclose(total, torch.ones(32), atol=1e-5), total


def test_probability_alone_sums_to_one():
    """기대 확률 p 는 그 자체로 합이 1 — 그래서 '모르겠다'를 담을 자리가 없다."""
    _a, _S, p, _u, _b = dirichlet(torch.randn(16, 7))
    assert torch.allclose(p.sum(-1), torch.ones(16), atol=1e-5)


def test_zero_evidence_gives_maximum_uncertainty():
    """증거가 0이면 u = 1 — '아무것도 모르겠다'."""
    # softplus(x) -> 0 이려면 x 가 아주 작아야 한다
    _a, _S, p, u, b = dirichlet(torch.full((1, 7), -50.0))
    assert u.item() > 0.999, u.item()
    assert b.max().item() < 1e-3
    assert torch.allclose(p, torch.full((1, 7), 1 / 7), atol=1e-4)


def test_strong_evidence_lowers_uncertainty():
    logits = torch.zeros(1, 7)
    logits[0, 2] = 20.0
    _a, _S, p, u, b = dirichlet(logits)
    assert u.item() < 0.5
    assert int(p.argmax()) == 2
    assert int(b.argmax()) == 2


def test_kl_is_zero_for_uniform_dirichlet():
    """Dir(1) 과의 KL 은 alpha=1 일 때 0 이어야 한다."""
    kl = kl_dirichlet_uniform(torch.ones(4, 7))
    assert torch.allclose(kl, torch.zeros(4), atol=1e-5), kl


def test_kl_is_positive_when_evidence_exists():
    a = torch.ones(1, 7)
    a[0, 0] = 9.0
    assert kl_dirichlet_uniform(a).item() > 0


def test_loss_decreases_when_prediction_improves():
    y = torch.eye(7)[torch.tensor([3])]
    wrong = torch.zeros(1, 7)
    wrong[0, 0] = 5.0
    right = torch.zeros(1, 7)
    right[0, 3] = 5.0
    assert edl_mse_loss(right, y, 0.0) < edl_mse_loss(wrong, y, 0.0)


def test_reject_rules():
    # 믿음 질량 b 와 불확실성 u (각 행의 합이 1)
    p = torch.tensor([[0.8, 0.05, 0.05], [0.2, 0.1, 0.1]])
    u = torch.tensor([[0.1], [0.6]])
    rel = reject_mask(p, u, REJECT_RULE_RELATIVE)
    assert bool(rel[0]) is False and bool(rel[1]) is True
    thr = reject_mask(p, u, REJECT_RULE_THRESHOLD, tau_u=0.5)
    assert bool(thr[0]) is False and bool(thr[1]) is True


def test_net_forward_shape_and_norm_variants():
    for norm in ("layer", "batch", "none"):
        net = EvidentialNet(23, 7, width=32, norm=norm)
        net.eval()
        out = net(torch.randn(4, 23))
        assert out.shape == (4, 7)


for _n, _f in sorted(globals().copy().items()):
    if _n.startswith("test_") and callable(_f):
        check(_n, _f)
print(f"{len(_passed)}개 통과")
