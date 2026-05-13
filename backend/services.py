"""Shared orchestration: run skills → Gemini → Bayes → Kelly → persist."""
from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from .aggregator import bayesian_combine
from .analyzer import analyze
from .kalshi_client import KalshiClient
from .kelly import kelly_position
from .models import AnalysisRun, RawResearch, engine


def _serialize_response(
    ticker: str,
    sheets,
    llm,
    market_price: float,
    combined,
    kelly,
    run_id: int,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "run_id": run_id,
        "context_sheets": [
            {
                "skill_id": s.skill_id,
                "headline": s.headline,
                "summary": s.summary,
                "citations": s.citations,
            }
            for s in sheets
        ],
        "llm": llm.model_dump(),
        "market": {"price": market_price, "probability": market_price},
        "combined": {
            "probability": combined.combined_probability,
            "model_weight": combined.model_weight,
            "market_weight": combined.market_weight,
        },
        "kelly": {
            "side": kelly.side,
            "edge": kelly.edge,
            "kelly_fraction": kelly.kelly_fraction,
            "fractional_kelly": kelly.fractional_kelly,
            "recommended_dollars": kelly.recommended_dollars,
            "recommended_contracts": kelly.recommended_contracts,
        },
        "edge": llm.probability - market_price,
    }


async def run_analysis(
    ticker: str,
    skill_ids: list[str],
    bankroll: float = 1000.0,
    market_price: float | None = None,
    market_confidence: float = 1.0,
    kalshi: KalshiClient | None = None,
) -> dict[str, Any]:
    """Run the full analyze pipeline and persist the final summary.

    market_price is in V2 dollars (0..1). If omitted, fetched from Kalshi.
    Raises ValueError if no price can be determined.
    """
    market: dict[str, Any] | None = None
    if kalshi:
        try:
            market = await kalshi.get_market(ticker)
        except Exception:
            market = None

    price = market_price
    if price is None and market:
        price = market.get("yes_bid")
    if price is None:
        raise ValueError(f"no market price available for {ticker}")

    llm, sheets = await analyze(ticker, skill_ids, market)

    combined = bayesian_combine(
        model_probability=llm.probability,
        model_confidence=llm.confidence,
        market_probability=price,
        market_confidence=market_confidence,
    )
    kelly = kelly_position(
        bankroll=bankroll,
        true_probability=combined.combined_probability,
        market_price=price,
    )

    with Session(engine) as s:
        run = AnalysisRun(
            ticker=ticker,
            market_price=price,
            model_probability=llm.probability,
            model_confidence=llm.confidence,
            combined_probability=combined.combined_probability,
            edge=llm.probability - price,
            kelly_side=kelly.side,
            kelly_dollars=kelly.recommended_dollars,
            kelly_contracts=kelly.recommended_contracts,
            reasoning=llm.reasoning,
        )
        s.add(run)
        s.commit()
        s.refresh(run)
        for sheet in sheets:
            s.add(RawResearch(
                run_id=run.id,
                skill_id=sheet.skill_id,
                headline=sheet.headline,
                summary=sheet.summary,
                citations_json=json.dumps(sheet.citations),
            ))
        s.commit()
        run_id = run.id

    return _serialize_response(ticker, sheets, llm, price, combined, kelly, run_id)


def latest_run_for(ticker: str) -> AnalysisRun | None:
    with Session(engine) as s:
        return s.exec(
            select(AnalysisRun).where(AnalysisRun.ticker == ticker).order_by(AnalysisRun.created_at.desc())
        ).first()
