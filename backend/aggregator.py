"""Bayesian log-odds aggregator: combine model probability with market probability."""
from __future__ import annotations

import math
from dataclasses import dataclass

_EPS = 1e-6


def _clip(p: float) -> float:
    return min(max(p, _EPS), 1.0 - _EPS)


def logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class CombinedEstimate:
    model_probability: float
    market_probability: float
    model_weight: float
    market_weight: float
    combined_probability: float


def bayesian_combine(
    model_probability: float,
    model_confidence: float,
    market_probability: float,
    market_confidence: float = 1.0,
) -> CombinedEstimate:
    """Weighted average in log-odds space.

    Weights are the caller-supplied confidences in [0, 1]. The market is treated
    as a noisy prior with a tunable weight (default 1.0 — strong, since it
    reflects pooled trader information). The model's posterior weight comes
    from the analyzer's self-reported confidence.
    """
    w_m = max(model_confidence, 0.0)
    w_k = max(market_confidence, 0.0)
    if w_m + w_k <= 0:
        return CombinedEstimate(
            model_probability=model_probability,
            market_probability=market_probability,
            model_weight=0.0,
            market_weight=0.0,
            combined_probability=market_probability,
        )
    combined = sigmoid((w_m * logit(model_probability) + w_k * logit(market_probability)) / (w_m + w_k))
    return CombinedEstimate(
        model_probability=model_probability,
        market_probability=market_probability,
        model_weight=w_m,
        market_weight=w_k,
        combined_probability=combined,
    )
