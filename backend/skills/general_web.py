"""General web research via Tavily, with a deterministic mock when no key is set."""
from __future__ import annotations

import os
from typing import Any

import httpx

from .base import ContextSheet, ResearchSkill

TAVILY_URL = "https://api.tavily.com/search"


class GeneralWebSkill(ResearchSkill):
    id = "general_web"
    name = "General Web Search"
    description = "Searches the open web for news and context about the market topic."

    def __init__(self, max_results: int = 5):
        self.max_results = max_results
        self.api_key = os.getenv("TAVILY_API_KEY", "").strip()

    async def run(self, ticker: str, market: dict[str, Any] | None = None) -> ContextSheet:
        query = self._build_query(ticker, market)
        if not self.api_key:
            return self._mock(query, ticker)
        return await self._tavily(query)

    def _build_query(self, ticker: str, market: dict[str, Any] | None) -> str:
        title = (market or {}).get("title")
        return title if title else f"Kalshi market {ticker} news outcome"

    async def _tavily(self, query: str) -> ContextSheet:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": self.max_results,
            "include_answer": True,
            "search_depth": "advanced",
        }
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(TAVILY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", [])
        answer = data.get("answer") or ""
        summary_parts = [answer.strip()] if answer else []
        for r in results[: self.max_results]:
            snippet = (r.get("content") or "").strip().replace("\n", " ")
            if snippet:
                summary_parts.append(f"- {snippet}")
        summary = "\n".join(summary_parts) or "No web results returned."

        return ContextSheet(
            skill_id=self.id,
            headline=f"Web context for: {query}",
            summary=summary,
            citations=[
                {"title": r.get("title", ""), "url": r.get("url", "")}
                for r in results
                if r.get("url")
            ],
            raw={"query": query, "answer": answer},
        )

    def _mock(self, query: str, ticker: str) -> ContextSheet:
        return ContextSheet(
            skill_id=self.id,
            headline=f"[mock] Web context for: {query}",
            summary=(
                f"No TAVILY_API_KEY configured — returning a placeholder context for {ticker}. "
                "Set TAVILY_API_KEY in your .env to enable live web research."
            ),
            citations=[],
            raw={"mock": True, "query": query},
        )
