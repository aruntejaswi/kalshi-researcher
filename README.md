# KalshiResearcher

A research dashboard for [Kalshi](https://kalshi.com) prediction markets. Pulls live markets and ticker prices, runs a pluggable set of research "skills" (web search, etc.), asks an LLM for a probability estimate, then combines that with the market price (Bayesian log-odds) and recommends a Kelly-sized position.

- **Backend**: FastAPI · SQLModel/SQLite · httpx · websockets · cryptography (RSA-PSS V2 signing)
- **Frontend**: Vite + React · Tailwind · shadcn-style UI · Zustand · TanStack Query
- **LLM**: Google Gemini (REST, structured JSON output)
- **Search**: Tavily (optional — falls back to a deterministic mock)

## Prerequisites

- Python **3.11+**
- Node **18+** and npm
- A Kalshi account with an API key (key ID + RSA private key PEM)
- *(Optional)* a Gemini API key and a Tavily API key

## Setup

### 1. Clone

```bash
git clone https://github.com/aruntejaswi/kalshi-researcher.git
cd kalshi-researcher
```

### 2. Kalshi API key

You need two things from Kalshi:

1. **Key ID** — a UUID, shown in the Kalshi dashboard.
2. **RSA private key** — you generate the keypair locally and upload the *public* half to Kalshi. They keep the public key; you keep the private key.

Quick way to generate a fresh keypair:

```bash
mkdir -p secrets
openssl genrsa -out secrets/kalshi_private_key.pem 2048
openssl rsa -in secrets/kalshi_private_key.pem -pubout -out secrets/kalshi_public_key.pem
```

Then upload `secrets/kalshi_public_key.pem` to Kalshi under **Settings → API Keys** and copy the resulting key ID.

The `secrets/` directory is git-ignored — your private key never leaves your machine.

### 3. Environment variables

Copy the template and fill it in:

```bash
cp .env.example .env
```

Edit `.env`:

```env
KALSHI_KEY_ID=your-key-id-uuid-here
KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi_private_key.pem

# Optional: enables real web research instead of mock context
TAVILY_API_KEY=

# Optional: enables the Gemini analyzer instead of a placeholder estimate
GEMINI_API_KEY=
# GEMINI_MODEL=gemini-2.0-flash

# Optional: override Kalshi endpoints (defaults are production)
# KALSHI_REST_BASE=https://api.elections.kalshi.com/trade-api/v2
# KALSHI_WS_URL=wss://api.elections.kalshi.com/trade-api/ws/v2
```

The app will start even without Tavily or Gemini keys — the missing skill returns a clearly-labeled placeholder context, and the analyzer returns a neutral 0.5/0.1 estimate. You'll still see live markets, prices, and the UI controls.

### 4. Backend

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 5. Frontend

```bash
cd frontend
npm install
cd ..
```

## Running

Two terminals from the repo root:

```bash
# Terminal 1 — API on :8000
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — UI on :5173
cd frontend && npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api/*` and `/ws/*` through to FastAPI, so everything runs on one origin.

## Using the dashboard

- **Sidebar** — toggle which research skills run during analysis.
- **Analyze button** (per row) — runs the selected skills against that ticker, calls Gemini, combines with the market price via Bayesian log-odds, then sizes a position via fractional Kelly. The result expands inline.
- **Batch Analyze** (header) — runs the same pipeline against every visible market, 3 concurrently, with a progress bar.
- **Category dropdown** — filters the visible markets by their parent event's category.
- **Settings** — choose how many markets to pull (25–1000) and clear local cache.
- **Sort by Edge** — click the Edge column header.

## Project layout

```
backend/
  main.py            FastAPI app, routes, lifespan (startup cleanup, WS feed boot)
  auth_utils.py      Kalshi V2 RSA-PSS signing
  kalshi_client.py   REST + WS client, throttled 1Hz fan-out, V2 dollars normalization
  analyzer.py        Gemini call with structured Pydantic output
  aggregator.py      Bayesian log-odds combiner
  kelly.py           Kelly criterion for binary contracts
  batch.py           asyncio batch processor (semaphore=3)
  services.py        Shared analyze pipeline (skills → LLM → bayes → kelly → persist)
  models.py          SQLModel: Wager, Analysis, AnalysisRun (permanent), RawResearch (48h cleanup)
  skills/
    base.py          ResearchSkill ABC + ContextSheet dataclass
    general_web.py   Tavily (or mock) implementation

frontend/src/
  components/        Dashboard, SkillSidebar, AnalysisRow, ProgressBar, SettingsMenu, ui/
  store/             Zustand stores: prices, skills, settings (persisted)
  hooks/             WebSocket subscriber for live ticker prices
  lib/utils.ts       Price formatting, classnames helper
```

## Implementation notes

- **V2 dollars** — internally all prices are floats in `[0, 1]`. The Kalshi client normalizes incoming `*_dollars` fields and falls back to legacy cent fields, converting once at ingest.
- **1Hz throttling** — the WS feed dedupes per-ticker updates and flushes the latest snapshot to subscribers every 1s, so a chatty market doesn't flood the browser.
- **Storage policy** — `AnalysisRun` (final reasoning + Kelly recommendation) is permanent; `RawResearch` (per-skill context snippets) is pruned on startup if older than 48 hours. The DB never stores raw HTML — only pre-summarized text from skills.
- **Active markets only** — `/api/markets` filters out anything with `result` set, status in `{closed, settled, determined, finalized, expired}`, or a `close_time` in the past.

## Adding a skill

1. Subclass `ResearchSkill` in `backend/skills/your_skill.py`.
2. Implement `async def run(self, ticker, market) -> ContextSheet`.
3. Register it in `backend/skills/__init__.py` by appending to `SKILLS`.

It'll appear in the sidebar automatically.

## License

No license specified — treat as proprietary unless one is added.
