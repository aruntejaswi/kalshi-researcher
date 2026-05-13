"""SQLModel schema for KalshiResearcher persistence.

Storage policy
--------------
- AnalysisRun and Wager are permanent: they hold the final result + position metrics.
- RawResearch is ephemeral context (skill output snippets) and gets pruned by
  cleanup_raw_research() on startup. We never store raw HTML — only the
  pre-summarized text our skills produced.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select


class Wager(SQLModel, table=True):
    __tablename__ = "wagers"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    side: str  # "yes" | "no"
    contracts: int
    entry_price: float  # dollars 0..1 (V2 standard)
    exit_price: Optional[float] = None
    status: str = Field(default="open", index=True)  # "open" | "closed" | "cancelled"
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    closed_at: Optional[datetime] = None


class Analysis(SQLModel, table=True):
    """User-authored analysis notes (separate from AnalysisRun)."""
    __tablename__ = "analyses"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    title: str
    thesis: str
    confidence: float = Field(default=0.5)
    fair_value: Optional[float] = None  # dollars 0..1
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class AnalysisRun(SQLModel, table=True):
    """Permanent record of one analyzer run — the final summary, not raw text."""
    __tablename__ = "analysis_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    market_price: float  # dollars 0..1
    model_probability: float
    model_confidence: float
    combined_probability: float
    edge: float  # model_probability - market_price
    kelly_side: str
    kelly_dollars: float
    kelly_contracts: int
    reasoning: str
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


class RawResearch(SQLModel, table=True):
    """Per-skill context sheet — pruned after 48h by cleanup_raw_research()."""
    __tablename__ = "raw_research"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="analysis_runs.id", index=True)
    skill_id: str
    headline: str
    summary: str
    citations_json: str = ""  # JSON-encoded list[{title,url}]
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)


DB_URL = "sqlite:///./kalshi_researcher.db"
engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


def cleanup_raw_research(older_than_hours: int = 48) -> int:
    """Delete RawResearch rows older than the cutoff. Returns how many were removed.

    Keeps AnalysisRun (the final summary + Kelly recommendation) untouched.
    """
    cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
    with Session(engine) as s:
        rows = s.exec(select(RawResearch).where(RawResearch.created_at < cutoff)).all()
        for r in rows:
            s.delete(r)
        s.commit()
        return len(rows)
