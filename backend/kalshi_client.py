"""Kalshi REST + WebSocket client with a 1Hz throttled fan-out."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import httpx
import websockets

from .auth_utils import SignedHeaders, load_private_key, sign_request

log = logging.getLogger(__name__)

KALSHI_REST_BASE = os.getenv("KALSHI_REST_BASE", "https://api.elections.kalshi.com/trade-api/v2")
KALSHI_WS_URL = os.getenv("KALSHI_WS_URL", "wss://api.elections.kalshi.com/trade-api/ws/v2")


_DOLLAR_FIELDS = (
    ("yes_bid", "yes_bid_dollars"),
    ("yes_ask", "yes_ask_dollars"),
    ("no_bid", "no_bid_dollars"),
    ("no_ask", "no_ask_dollars"),
    ("last_price", "last_price_dollars"),
    ("price", "price_dollars"),
)


def _to_dollars(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


_INACTIVE_STATUSES = {"closed", "settled", "determined", "finalized", "expired"}


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_tradeable(m: dict[str, Any], now: datetime) -> bool:
    """Drop markets that are determined, settled, or past close_time."""
    status = (m.get("status") or "").lower()
    if status in _INACTIVE_STATUSES:
        return False
    if m.get("result"):  # YES/NO winner already assigned
        return False
    close = _parse_iso(m.get("close_time"))
    if close and close <= now:
        return False
    return True


def normalize_market(m: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Kalshi market/ticker dict to V2 dollar units (0..1 floats).

    Prefers the V2 `*_dollars` fields. Falls back to legacy cent fields when
    the V2 fields are absent, converting cents → dollars so downstream code
    only sees one canonical price representation.
    """
    out = dict(m)
    for cents_key, dollars_key in _DOLLAR_FIELDS:
        if dollars_key in out and out[dollars_key] is not None:
            out[cents_key] = _to_dollars(out[dollars_key])
        elif cents_key in out and out[cents_key] is not None:
            cents = _to_dollars(out[cents_key])
            if cents is not None and abs(cents) > 1.0:  # looks like legacy cents
                out[cents_key] = cents / 100.0
    return out


class KalshiClient:
    """Thin async client over the Kalshi V2 REST API."""

    def __init__(self, key_id: str, private_key_path: str, base_url: str = KALSHI_REST_BASE):
        self.key_id = key_id
        self.private_key = load_private_key(private_key_path)
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)
        self._event_cache: dict[str, str] = {}  # event_ticker -> category

    async def aclose(self) -> None:
        await self._http.aclose()

    def _sign(self, method: str, path: str) -> SignedHeaders:
        return sign_request(self.private_key, self.key_id, method, path)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = self._sign(method, path).as_dict()
        headers.update(kwargs.pop("headers", {}))
        resp = await self._http.request(method, path, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.json()

    async def list_markets(
        self,
        limit: int = 50,
        status: str = "open",
        active_only: bool = True,
        with_categories: bool = True,
    ) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/markets?limit={limit}&status={status}")
        markets = [normalize_market(m) for m in data.get("markets", [])]
        if active_only:
            now = datetime.now(timezone.utc)
            markets = [m for m in markets if _is_tradeable(m, now)]
        if with_categories:
            await self._attach_categories(markets)
        return markets

    async def get_market(self, ticker: str) -> dict[str, Any]:
        data = await self._request("GET", f"/markets/{ticker}")
        return normalize_market(data.get("market", {}))

    async def get_event(self, event_ticker: str) -> dict[str, Any]:
        data = await self._request("GET", f"/events/{event_ticker}")
        return data.get("event", {})

    async def _attach_categories(self, markets: list[dict[str, Any]]) -> None:
        """Look up each unique event_ticker's category and stamp it on the market.

        Results are cached on the client so subsequent /api/markets calls only
        pay for newly-seen events.
        """
        unknown = sorted({
            m["event_ticker"] for m in markets
            if m.get("event_ticker") and m["event_ticker"] not in self._event_cache
        })
        if unknown:
            sem = asyncio.Semaphore(5)

            async def fetch(t: str) -> None:
                async with sem:
                    try:
                        ev = await self.get_event(t)
                        self._event_cache[t] = (ev.get("category") or "").strip() or "Uncategorized"
                    except Exception:
                        self._event_cache[t] = "Uncategorized"

            await asyncio.gather(*(fetch(t) for t in unknown))
        for m in markets:
            m["category"] = self._event_cache.get(m.get("event_ticker", ""), "Uncategorized")


class ThrottledManager:
    """Buffers Kalshi WS ticker updates and pushes the latest snapshot at 1Hz.

    Subscribers are local asyncio.Queues (usually one per FastAPI WebSocket client).
    Per-ticker price is collapsed to the most recent value within each 1-second tick;
    bursty markets won't flood the browser.
    """

    def __init__(self, interval_s: float = 1.0):
        self.interval_s = interval_s
        self._latest: dict[str, dict[str, Any]] = {}
        self._dirty: set[str] = set()
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._flusher_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._flusher_task is None or self._flusher_task.done():
            self._flusher_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        if self._flusher_task:
            self._flusher_task.cancel()
            try:
                await self._flusher_task
            except asyncio.CancelledError:
                pass
            self._flusher_task = None

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)

    async def ingest(self, ticker: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            self._latest[ticker] = payload
            self._dirty.add(ticker)

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_s)
            async with self._lock:
                if not self._dirty:
                    continue
                batch = {t: self._latest[t] for t in self._dirty}
                self._dirty.clear()
            message = {"type": "prices", "data": batch}
            for q in list(self._subscribers):
                if q.full():
                    # Drop oldest rather than block the flusher.
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    log.warning("subscriber queue still full after drop; skipping")


class KalshiWSFeed:
    """Connects to Kalshi WS, subscribes to ticker channels, feeds the throttler."""

    def __init__(self, client: KalshiClient, manager: ThrottledManager, tickers: list[str]):
        self.client = client
        self.manager = manager
        self.tickers = tickers
        self._task: asyncio.Task[None] | None = None
        self._cmd_id = 0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _next_id(self) -> int:
        self._cmd_id += 1
        return self._cmd_id

    async def _run(self) -> None:
        while True:
            try:
                async for payload in self._stream():
                    await self._handle(payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Kalshi WS feed crashed; reconnecting in 2s")
                await asyncio.sleep(2.0)

    async def _stream(self) -> AsyncIterator[dict[str, Any]]:
        # Sign the WS upgrade per Kalshi V2 (path is the WS path without query).
        ws_path = "/trade-api/ws/v2"
        headers = sign_request(self.client.private_key, self.client.key_id, "GET", ws_path).as_dict()
        async with websockets.connect(KALSHI_WS_URL, additional_headers=headers) as ws:
            await ws.send(json.dumps({
                "id": self._next_id(),
                "cmd": "subscribe",
                "params": {"channels": ["ticker"], "market_tickers": self.tickers},
            }))
            async for raw in ws:
                yield json.loads(raw)

    async def _handle(self, msg: dict[str, Any]) -> None:
        if msg.get("type") != "ticker":
            return
        m = msg.get("msg") or {}
        ticker = m.get("market_ticker")
        if not ticker:
            return
        norm = normalize_market(m)
        await self.manager.ingest(ticker, {
            "yes_bid": norm.get("yes_bid"),
            "yes_ask": norm.get("yes_ask"),
            "price": norm.get("price") if norm.get("price") is not None else norm.get("last_price"),
            "ts": m.get("ts"),
        })
