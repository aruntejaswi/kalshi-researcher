"""Base contracts for research skills."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContextSheet:
    """The output of one research skill — fed to the analyzer LLM."""

    skill_id: str
    headline: str
    summary: str
    citations: list[dict[str, str]] = field(default_factory=list)
    raw: dict[str, Any] | None = None

    def to_prompt_block(self) -> str:
        cite_lines = "\n".join(
            f"  - [{c.get('title', 'source')}]({c.get('url', '')})" for c in self.citations
        )
        body = self.summary.strip()
        if cite_lines:
            body += "\n  Sources:\n" + cite_lines
        return f"### {self.skill_id} — {self.headline}\n{body}"


class ResearchSkill(ABC):
    """A pluggable research capability.

    Subclasses set class-level id/name/description and implement run().
    """

    id: str = ""
    name: str = ""
    description: str = ""

    def metadata(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "description": self.description}

    @abstractmethod
    async def run(self, ticker: str, market: dict[str, Any] | None = None) -> ContextSheet:
        """Produce a context sheet for the given Kalshi ticker."""
