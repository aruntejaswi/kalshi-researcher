"""LLM analyzer: runs selected skills, aggregates output, asks Gemini for a probability."""
from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from .skills import SKILL_REGISTRY, ContextSheet

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL_TMPL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Gemini's responseSchema accepts a subset of OpenAPI 3.0. Keep it hand-written
# so we don't accidentally emit JSON Schema features Gemini rejects.
_GEMINI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "reasoning": {"type": "STRING"},
        "probability": {"type": "NUMBER"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["reasoning", "probability", "confidence"],
}


class AnalysisResult(BaseModel):
    reasoning: str
    probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


async def run_skills(
    skill_ids: list[str], ticker: str, market: dict[str, Any] | None = None
) -> list[ContextSheet]:
    skills = [SKILL_REGISTRY[sid] for sid in skill_ids if sid in SKILL_REGISTRY]
    if not skills:
        return []
    return await asyncio.gather(*(s.run(ticker, market) for s in skills))


def build_prompt(ticker: str, market: dict[str, Any] | None, sheets: list[ContextSheet]) -> str:
    title = (market or {}).get("title", "")
    yes_bid = (market or {}).get("yes_bid")  # dollars 0..1 (V2)
    price_label = f"{yes_bid:.3f}" if isinstance(yes_bid, (int, float)) else "n/a"
    blocks = "\n\n".join(s.to_prompt_block() for s in sheets) or "(no skill output)"
    return (
        "You are a prediction-market analyst. Estimate the probability the YES side "
        "of the following Kalshi market resolves true.\n\n"
        f"Market ticker: {ticker}\n"
        f"Market title: {title}\n"
        f"Current YES bid (dollars, 0..1): {price_label}\n\n"
        "Research context:\n"
        f"{blocks}\n\n"
        "Return JSON with: reasoning (one short paragraph citing the context), "
        "probability (0..1 — your estimate of YES resolving true), "
        "confidence (0..1 — how much weight your estimate should carry vs. the market)."
    )


async def call_gemini(prompt: str, api_key: str) -> AnalysisResult:
    url = GEMINI_URL_TMPL.format(model=GEMINI_MODEL)
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": _GEMINI_RESPONSE_SCHEMA,
            "temperature": 0.4,
        },
    }
    async with httpx.AsyncClient(timeout=60.0) as http:
        resp = await http.post(url, params={"key": api_key}, json=body)
        resp.raise_for_status()
        data = resp.json()

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Gemini returned non-JSON: {text!r}") from e
    return AnalysisResult.model_validate(payload)


def _mock_result(sheets: list[ContextSheet]) -> AnalysisResult:
    summary_chars = sum(len(s.summary) for s in sheets)
    prob = min(0.5 + summary_chars * 1e-5, 0.85) if sheets else 0.5
    return AnalysisResult(
        reasoning=(
            "GEMINI_API_KEY not set — returning a placeholder estimate based on the "
            f"{len(sheets)} skill context sheet(s) collected. Configure GEMINI_API_KEY to "
            "enable real model inference."
        ),
        probability=prob,
        confidence=0.2,
    )


async def analyze(
    ticker: str,
    skill_ids: list[str],
    market: dict[str, Any] | None = None,
) -> tuple[AnalysisResult, list[ContextSheet]]:
    sheets = await run_skills(skill_ids, ticker, market)
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _mock_result(sheets), sheets
    prompt = build_prompt(ticker, market, sheets)
    try:
        return await call_gemini(prompt, api_key), sheets
    except (httpx.HTTPError, RuntimeError, ValidationError) as e:
        return (
            AnalysisResult(
                reasoning=f"Gemini call failed ({type(e).__name__}: {e}); using neutral fallback.",
                probability=0.5,
                confidence=0.1,
            ),
            sheets,
        )
