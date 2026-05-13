"""FastAPI entrypoint: REST endpoints + WebSocket fan-out from the throttled feed."""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from .batch import BatchProcessor
from .kalshi_client import KalshiClient, KalshiWSFeed, ThrottledManager
from .models import (
    Analysis,
    AnalysisRun,
    Wager,
    cleanup_raw_research,
    engine,
    init_db,
)
from .services import run_analysis
from .skills import SKILLS

log = logging.getLogger(__name__)

load_dotenv()

KEY_ID = os.getenv("KALSHI_KEY_ID", "")
KEY_PATH = os.getenv("KALSHI_PRIVATE_KEY_PATH", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    removed = cleanup_raw_research(older_than_hours=48)
    if removed:
        log.info("startup cleanup pruned %d raw research rows older than 48h", removed)

    manager = ThrottledManager(interval_s=1.0)
    manager.start()
    app.state.manager = manager
    app.state.batch = BatchProcessor(concurrency=3)

    client: KalshiClient | None = None
    feed: KalshiWSFeed | None = None
    if KEY_ID and KEY_PATH and os.path.exists(KEY_PATH):
        client = KalshiClient(KEY_ID, KEY_PATH)
        try:
            markets = await client.list_markets(limit=25)
            tickers = [m["ticker"] for m in markets if m.get("ticker")]
            if tickers:
                feed = KalshiWSFeed(client, manager, tickers)
                feed.start()
        except Exception:
            pass
    app.state.kalshi = client
    app.state.feed = feed

    try:
        yield
    finally:
        if feed:
            await feed.stop()
        await app.state.batch.shutdown()
        await manager.stop()
        if client:
            await client.aclose()


app = FastAPI(title="KalshiResearcher", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/markets")
async def get_markets(limit: int = 25):
    client: KalshiClient | None = app.state.kalshi
    if not client:
        return {"markets": [], "note": "KALSHI_KEY_ID / KALSHI_PRIVATE_KEY_PATH not configured"}
    return {"markets": await client.list_markets(limit=limit)}


@app.get("/api/wagers")
async def list_wagers():
    with Session(engine) as s:
        return s.exec(select(Wager).order_by(Wager.created_at.desc())).all()


@app.post("/api/wagers")
async def create_wager(wager: Wager):
    with Session(engine) as s:
        s.add(wager)
        s.commit()
        s.refresh(wager)
        return wager


@app.get("/api/analyses")
async def list_analyses():
    with Session(engine) as s:
        return s.exec(select(Analysis).order_by(Analysis.created_at.desc())).all()


@app.post("/api/analyses")
async def create_analysis(analysis: Analysis):
    with Session(engine) as s:
        s.add(analysis)
        s.commit()
        s.refresh(analysis)
        return analysis


@app.get("/api/runs")
async def list_runs(limit: int = 50, ticker: str | None = None):
    with Session(engine) as s:
        stmt = select(AnalysisRun).order_by(AnalysisRun.created_at.desc()).limit(limit)
        if ticker:
            stmt = select(AnalysisRun).where(AnalysisRun.ticker == ticker).order_by(AnalysisRun.created_at.desc()).limit(limit)
        return s.exec(stmt).all()


@app.get("/api/skills")
async def list_skills():
    return {"skills": [s.metadata() for s in SKILLS]}


class AnalyzeRequest(BaseModel):
    ticker: str
    skills: list[str] = Field(default_factory=list)
    bankroll: float = 1000.0
    market_price: float | None = None  # V2 dollars 0..1
    market_confidence: float = 1.0


@app.post("/api/analyze")
async def analyze_endpoint(req: AnalyzeRequest):
    try:
        return await run_analysis(
            ticker=req.ticker,
            skill_ids=req.skills,
            bankroll=req.bankroll,
            market_price=req.market_price,
            market_confidence=req.market_confidence,
            kalshi=app.state.kalshi,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


class BatchRequest(BaseModel):
    tickers: list[str]
    skills: list[str] = Field(default_factory=list)
    bankroll: float = 1000.0
    market_prices: dict[str, float] = Field(default_factory=dict)  # ticker -> dollars


@app.post("/api/batch/analyze")
async def batch_analyze(req: BatchRequest):
    batch: BatchProcessor = app.state.batch

    async def runner(ticker: str) -> dict:
        return await run_analysis(
            ticker=ticker,
            skill_ids=req.skills,
            bankroll=req.bankroll,
            market_price=req.market_prices.get(ticker),
            kalshi=app.state.kalshi,
        )

    job = batch.submit(req.tickers, runner)
    return job.snapshot()


@app.get("/api/batch/{job_id}")
async def batch_status(job_id: str):
    batch: BatchProcessor = app.state.batch
    job = batch.get(job_id)
    if not job:
        raise HTTPException(404, "batch not found")
    return job.snapshot()


@app.websocket("/ws/prices")
async def ws_prices(websocket: WebSocket):
    await websocket.accept()
    manager: ThrottledManager = app.state.manager
    queue = manager.subscribe()
    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        manager.unsubscribe(queue)
