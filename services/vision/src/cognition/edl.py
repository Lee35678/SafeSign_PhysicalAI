# -*- coding: utf-8 -*-
"""Evidential Deep Learning — 신경망이 "모르겠다"를 직접 말하게 한다.

왜 이게 필요한가
  softmax 는 K개 클래스 안에서 합이 1이 되도록 정규화한다. 그래서 학습한 적 없는 입력이
  들어와도 "그나마 가장 비슷한" 클래스가 높은 확률을 받는다 — **7종 밖이라는 선택지가
  문법에 없다.** 실측으로 학습에 없던 손모양의 83%가 확신도 검사를 그냥 통과했다.
  그래서 지금까지는 분류기 바깥에 거리 기반 게이트를 덧대고 그 수치를 사람이 맞췄다.

EDL 이 바꾸는 것
  신경망이 확률 대신 **증거(evidence)** 를 낸다. 증거는 디리클레 분포의 파라미터가 되고,
  거기서 확률과 **불확실성이 함께** 나온다.

      e_k = softplus(logit_k) >= 0     클래스 k 의 증거
      a_k = e_k + 1                    디리클레 파라미터
      S   = sum(a_k) = sum(e_k) + K    증거 총량
      p_k = a_k / S                    **기대 확률** (이것만으로 합이 1)
      b_k = e_k / S                    **믿음 질량**
      u   = K / S                      불확실성 질량

      sum(b_k) + u = 1                 <- 핵심. b 와 u 가 같은 저울 위에 있다

  헷갈리기 쉬운 곳: 항등식이 성립하는 것은 p 가 아니라 **b** 다.
  p 는 그 자체로 합이 1이라 "모르겠다"를 담을 자리가 없다(= softmax 와 같은 한계).
  거부 판단에 b 와 u 를 쓰는 이유가 이것이다.

  처음 보는 손이면 어느 클래스에도 증거를 못 내므로 S -> K, 즉 u -> 1 이 된다.
  "아무것도 아님"이 모델 출력 안에 자리를 갖는다.

참고: Sensoy, Kaplan, Kandemir (2018) "Evidential Deep Learning to Quantify
      Classification Uncertainty", NeurIPS.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

__all__ = [
    "ACTIVATIONS", "EvidentialNet", "dirichlet", "edl_mse_loss", "evidence_fn",
    "kl_dirichlet_uniform",
    "REJECT_RULE_RELATIVE", "REJECT_RULE_THRESHOLD", "reject_mask",
]

REJECT_RULE_RELATIVE = "relative"    # u > max_k p_k  (임계값 없음)
REJECT_RULE_THRESHOLD = "threshold"  # u > tau_u

# 증거 활성 함수 — logit 을 0 이상의 증거로 바꾸는 방법
#   relu      Sensoy et al.(2018) 원논문 기본값. 음수 구간 기울기 0 -> 한 번 죽은 증거가
#             되살아나지 않는다(dead evidence)
#   softplus  relu 를 매끄럽게 만든 것. 0 근처에서도 기울기가 남는다
#   exp       증거를 지수로 키운다. 아는 입력은 증거가 폭발적으로 커지고 모르는 입력은
#             0 쪽으로 빠르게 줄어 u 의 대비가 커진다(Pandey & Yu 2023 등에서 보고).
#             값이 폭주하지 않도록 logit 을 [-10, 10] 으로 자른다
ACTIVATIONS = ("relu", "softplus", "exp")
_EXP_CLAMP = 10.0


def evidence_fn(logits: torch.Tensor, activation: str = "softplus") -> torch.Tensor:
    """logit -> 증거 e >= 0."""
    if activation == "softplus":
        return F.softplus(logits)
    if activation == "relu":
        return F.relu(logits)
    if activation == "exp":
        return torch.exp(torch.clamp(logits, -_EXP_CLAMP, _EXP_CLAMP))
    raise ValueError(f"알 수 없는 증거 활성 함수: {activation} (가능: {ACTIVATIONS})")


class EvidentialNet(nn.Module):
    """joint23 -> 클래스별 증거. 마지막 층에 softmax 를 두지 않는 것이 요점이다.

    **정규화 층을 LayerNorm 으로 둔 이유 (실측).** BatchNorm 은 활성값을 *배치 전체의*
    통계로 정규화한다. 그래서 낯선 입력도 학습 분포의 범위로 끌려 들어가 증거가 줄지 않는다.
    실제로 재보니 정상 vs 애매한 자세 분리 AUC 가 BatchNorm 0.717 / LayerNorm 0.791 /
    정규화 없음 0.722 였다. LayerNorm 은 표본 하나 안에서만 정규화하므로 이 문제가 덜하다.

    Dropout 은 증거가 한두 뉴런에 몰리는 것을 막는다.
    """

    def __init__(self, dim: int, n_classes: int, width: int = 256, drop: float = 0.2,
                 norm: str = "layer", activation: str = "softplus"):
        super().__init__()
        if activation not in ACTIVATIONS:
            raise ValueError(f"알 수 없는 증거 활성 함수: {activation}")
        self.n_classes = n_classes
        self.norm = norm
        # 가중치가 아니라 구조의 일부다 — 학습과 추론이 반드시 같은 함수를 써야 한다
        self.activation = activation

        def block(fan_in: int) -> list[nn.Module]:
            layers: list[nn.Module] = [nn.Linear(fan_in, width)]
            if norm == "batch":
                layers.append(nn.BatchNorm1d(width))
            elif norm == "layer":
                layers.append(nn.LayerNorm(width))
            layers += [nn.ReLU(), nn.Dropout(drop)]
            return layers

        self.body = nn.Sequential(*block(dim), *block(width))
        self.head = nn.Linear(width, n_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """원시 logit 을 돌려준다. 증거로 바꾸는 것은 dirichlet() 이 한다."""
        return self.head(self.body(x))


def dirichlet(logits: torch.Tensor, activation: str = "softplus") -> tuple[torch.Tensor, ...]:
    """logit -> (alpha, S, p, u, b).

    p 는 기대 확률(합 1), b 는 믿음 질량(sum(b) + u = 1). 거부 판단에는 b 와 u 를 쓴다.
    activation 은 반드시 학습 때와 같아야 한다 — 신경망의 `net.activation` 을 넘긴다.
    """
    K = logits.shape[-1]
    evidence = evidence_fn(logits, activation)
    alpha = evidence + 1.0
    S = alpha.sum(-1, keepdim=True)
    p = alpha / S
    u = K / S
    b = evidence / S
    return alpha, S, p, u, b


def kl_dirichlet_uniform(alpha: torch.Tensor) -> torch.Tensor:
    """KL[ Dir(alpha) || Dir(1) ] — 균등 분포로부터 얼마나 멀어졌는가."""
    K = alpha.shape[-1]
    S = alpha.sum(-1)
    lnB = torch.lgamma(S) - torch.lgamma(alpha).sum(-1)
    lnB_uniform = torch.lgamma(torch.tensor(float(K), device=alpha.device))
    digamma_term = ((alpha - 1.0)
                    * (torch.digamma(alpha) - torch.digamma(S.unsqueeze(-1)))).sum(-1)
    return lnB - lnB_uniform + digamma_term


def edl_mse_loss(logits: torch.Tensor, target: torch.Tensor, lam: float,
                 sample_weight: torch.Tensor | None = None,
                 activation: str = "softplus") -> torch.Tensor:
    """Sensoy et al. Eq.5 (MSE 형태) + 증거 억제 KL 항.

    세 조각으로 되어 있다.
      ① (y - p)^2      맞히기
      ② 분산 항         증거가 적을수록 커진다 -> 증거를 모으라는 압력
      ③ KL 항           **정답 클래스의 증거를 지운 뒤** 균등으로 끌어당긴다.
                        즉 "틀린 클래스에는 증거를 내지 마라". 이게 EDL 의 심장이다 —
                        이 항이 없으면 신경망은 모든 것에 자신만만해진다(= softmax 문제).

    lam 은 에폭에 따라 0 -> 1 로 천천히 올린다. 처음부터 세게 걸면 아무것도 못 배운다.
    """
    alpha, S, p, _u, _b = dirichlet(logits, activation)
    err = ((target - p) ** 2).sum(-1)
    var = (alpha * (S - alpha) / (S * S * (S + 1.0))).sum(-1)

    # 정답 클래스의 증거를 제거한 alpha — 틀린 쪽 증거만 남는다
    alpha_tilde = target + (1.0 - target) * alpha
    kl = kl_dirichlet_uniform(alpha_tilde)

    loss = err + var + lam * kl
    if sample_weight is not None:
        loss = loss * sample_weight
    return loss.mean()


def reject_mask(belief: torch.Tensor, u: torch.Tensor,
                rule: str = REJECT_RULE_RELATIVE, tau_u: float = 0.5) -> torch.Tensor:
    """어떤 입력을 unknown 으로 돌릴지 정한다. **믿음 질량 b 를 받는다(확률 p 가 아니다).**

    relative  u > max_k b_k    임계값이 없다. b 와 u 는 합이 1인 같은 저울 위에 있으므로
                               "가장 믿는 클래스보다 모르겠음이 크면 거부"가 성립한다.
                               정리하면 max_k e_k < K — 증거가 클래스 수에 못 미치면 거부.
    threshold u > tau_u        임계값이 있다. 쓰더라도 **고르는 데이터와 채점하는 데이터를
                               반드시 분리해야 한다** (11 §8-6).
    """
    u = u.squeeze(-1)
    if rule == REJECT_RULE_RELATIVE:
        return u > belief.max(-1).values
    if rule == REJECT_RULE_THRESHOLD:
        return u > tau_u
    raise ValueError(f"알 수 없는 거부 규칙: {rule}")
