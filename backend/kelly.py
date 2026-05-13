"""Kelly criterion sizing for binary Kalshi contracts.

Prices are dollars in [0, 1] (V2 standard), not cents.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KellyRecommendation:
    side: str            # "yes" | "no" | "pass"
    edge: float          # signed: true_probability - market_price (YES edge)
    kelly_fraction: float
    fractional_kelly: float
    bankroll: float
    recommended_dollars: float
    recommended_contracts: int


def kelly_position(
    bankroll: float,
    true_probability: float,
    market_price: float,
    fraction: float = 0.5,
    max_fraction_of_bankroll: float = 0.25,
) -> KellyRecommendation:
    """Recommend a position given a true-probability estimate.

    A YES contract costs `market_price` dollars and pays $1 on YES resolution.
    f* = (p - price) / (1 - price)  for YES,  symmetrically for NO.
    Fractional Kelly defaults to 0.5x; total exposure is capped.
    """
    if not 0 < market_price < 1:
        return KellyRecommendation("pass", 0.0, 0.0, 0.0, bankroll, 0.0, 0)

    p = max(0.0, min(1.0, true_probability))
    yes_price = market_price
    no_price = 1.0 - market_price

    edge_yes = p - yes_price

    if edge_yes > 0:
        side = "yes"
        kelly = edge_yes / (1.0 - yes_price)
        contract_cost = yes_price
    elif edge_yes < 0:
        side = "no"
        kelly = (-edge_yes) / (1.0 - no_price)
        contract_cost = no_price
    else:
        return KellyRecommendation("pass", 0.0, 0.0, 0.0, bankroll, 0.0, 0)

    kelly = max(0.0, min(kelly, 1.0))
    sized = kelly * fraction
    capped = min(sized, max_fraction_of_bankroll)

    dollars = capped * bankroll
    contracts = int(dollars // contract_cost) if contract_cost > 0 else 0

    return KellyRecommendation(
        side=side,
        edge=edge_yes,
        kelly_fraction=kelly,
        fractional_kelly=capped,
        bankroll=bankroll,
        recommended_dollars=round(dollars, 2),
        recommended_contracts=contracts,
    )
