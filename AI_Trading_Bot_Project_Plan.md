# 🤖 AI Self-Driving Crypto Trading Bot — Full Project Plan

> **Budget:** $500–$5,000 USDT  
> **Exchange:** Binance  
> **Style:** Mixed / AI-decided  
> **Stack:** Python 3.11, PyTorch, FastAPI, TimescaleDB, Redis, Docker

---

## 📁 Project Structure

```
crypto-trading-bot/
├── .cursor/
│   └── rules/
│       └── project.mdc           # Cursor AI rules
├── config/
│   ├── settings.py               # All config via env vars
│   └── logging.yaml
├── data/
│   ├── ingestion/
│   │   ├── binance_ws.py         # WebSocket streams
│   │   ├── binance_rest.py       # REST historical data
│   │   ├── coingecko.py          # Price + market data
│   │   ├── cryptopanic.py        # News sentiment source
│   │   └── onchain.py            # Glassnode / CryptoQuant
│   ├── processing/
│   │   ├── features.py           # Technical indicators
│   │   ├── normalizer.py         # Scaling + transforms
│   │   └── sentiment.py          # NLP pipeline
│   └── storage/
│       ├── timescale.py          # TimescaleDB write/read
│       └── redis_cache.py        # Real-time cache
├── models/
│   ├── regime_classifier.py      # XGBoost market regime
│   ├── tft_model.py              # Temporal Fusion Transformer
│   ├── rl_agent.py               # Stable-Baselines3 RL
│   ├── sentiment_model.py        # FinBERT pipeline
│   └── ensemble.py               # Signal aggregator
├── strategy/
│   ├── universe_selector.py      # Which pairs to trade
│   ├── signal_generator.py       # Combined signals
│   ├── portfolio_optimizer.py    # Allocation optimizer
│   └── genetic_evolver.py        # Strategy evolution
├── risk/
│   ├── risk_manager.py           # Core risk engine
│   ├── position_sizer.py         # Kelly + volatility sizing
│   └── circuit_breaker.py        # Emergency halts
├── execution/
│   ├── order_manager.py          # Order lifecycle
│   ├── binance_executor.py       # Binance API calls
│   └── fee_optimizer.py          # Minimize trading costs
├── monitoring/
│   ├── dashboard/                # Grafana configs
│   ├── telegram_bot.py           # Alerts
│   ├── performance_tracker.py    # P&L, Sharpe, drawdown
│   └── health_check.py
├── backtesting/
│   ├── engine.py                 # Core backtest runner
│   ├── walk_forward.py           # Walk-forward validation
│   └── report_generator.py      # PDF/HTML reports
├── pipeline/
│   ├── retrain_pipeline.py       # Auto-retraining
│   ├── drift_detector.py         # Model drift detection
│   └── meta_learner.py           # Learn from trade history
├── api/
│   ├── main.py                   # FastAPI app
│   ├── routes/
│   │   ├── status.py
│   │   ├── trades.py
│   │   └── config.py
│   └── middleware/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── backtest_fixtures/
├── scripts/
│   ├── setup_db.py
│   ├── download_history.py
│   └── paper_trade.py
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.prod.yml
├── .env.example
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 🗓️ Phase-by-Phase Build Plan

---

### PHASE 1 — Foundation & Data Pipeline
**Duration:** Week 1–2  
**Goal:** Reliable data flowing into database. Nothing else matters until this works.

#### Week 1 — Infrastructure Setup

**Day 1–2: Environment**
- [ ] Create GitHub repo, set up branch strategy (`main`, `develop`, `feature/*`)
- [ ] Set up `.env` file with all secrets (never committed)
- [ ] Create `docker-compose.yml` with: TimescaleDB, Redis, Grafana, the bot app
- [ ] Write `config/settings.py` using `pydantic-settings` — all config from env vars
- [ ] Set up structured logging with `structlog`
- [ ] Create DB schema and run migrations with `alembic`

**Database Schema:**
```sql
-- OHLCV candles (TimescaleDB hypertable)
CREATE TABLE candles (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    num_trades  INTEGER
);
SELECT create_hypertable('candles', 'time');
CREATE INDEX ON candles (symbol, timeframe, time DESC);

-- Computed features
CREATE TABLE features (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    timeframe   TEXT NOT NULL,
    features    JSONB
);

-- Signals
CREATE TABLE signals (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    signal_type TEXT,
    direction   TEXT,       -- BUY / SELL / HOLD
    confidence  DOUBLE PRECISION,
    metadata    JSONB
);

-- Trades
CREATE TABLE trades (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    opened_at       TIMESTAMPTZ NOT NULL,
    closed_at       TIMESTAMPTZ,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,   -- LONG / SHORT
    entry_price     DOUBLE PRECISION,
    exit_price      DOUBLE PRECISION,
    quantity        DOUBLE PRECISION,
    pnl_usdt        DOUBLE PRECISION,
    pnl_pct         DOUBLE PRECISION,
    fees_paid       DOUBLE PRECISION,
    stop_loss       DOUBLE PRECISION,
    take_profit     DOUBLE PRECISION,
    signals_used    JSONB,
    market_regime   TEXT,
    status          TEXT             -- OPEN / CLOSED / CANCELLED
);

-- Sentiment
CREATE TABLE sentiment (
    time        TIMESTAMPTZ NOT NULL,
    symbol      TEXT NOT NULL,
    source      TEXT NOT NULL,
    score       DOUBLE PRECISION,   -- -1.0 to 1.0
    raw_text    TEXT,
    metadata    JSONB
);
```

**Day 3–4: Historical Data Download**
- [ ] Script to download 2 years of OHLCV for top 50 Binance USDT pairs
- [ ] Store all timeframes: 1m, 5m, 15m, 1h, 4h, 1d
- [ ] Validate data: check for gaps, bad values, duplicates
- [ ] Write unit tests for data integrity

**Day 5–7: Live WebSocket Ingestion**
- [ ] Async WebSocket manager using `python-binance` v1.x async
- [ ] Auto-reconnect with exponential backoff
- [ ] Subscribe to: trade streams, kline streams, depth streams (order book)
- [ ] Write incoming data to Redis (real-time) and TimescaleDB (persistence)
- [ ] Health check endpoint to confirm streams are alive

#### Week 2 — Feature Engineering

- [ ] Implement 50+ technical indicators via `pandas-ta`:
  - Trend: EMA(9,21,50,200), MACD, ADX, Supertrend
  - Momentum: RSI, Stochastic, Williams %R, CCI, MFI
  - Volatility: Bollinger Bands, ATR, Keltner Channels, VIX-like metric
  - Volume: OBV, VWAP, Volume Delta, CVD (Cumulative Volume Delta)
  - Custom: Order book imbalance, trade flow imbalance
- [ ] Multi-timeframe feature alignment (15m + 1h + 4h on same timestamp)
- [ ] Feature store: precompute and cache features for fast model inference
- [ ] Write comprehensive tests for all feature calculations

**Deliverable:** Database with 2 years of clean OHLCV + features, live WebSocket running, all tests green.

---

### PHASE 2 — Backtesting Engine
**Duration:** Week 3  
**Goal:** Be able to validate any strategy before it touches real money.

- [ ] Build event-driven backtesting engine (not vectorized — needs to simulate real execution)
- [ ] Realistic simulation:
  - Binance maker/taker fees (0.075% with BNB)
  - Slippage model (0.05–0.2% depending on size)
  - Partial fills for large orders
  - No look-ahead bias (strict timestamp ordering)
- [ ] Walk-forward validation framework:
  - Rolling 6-month train window, 1-month test window
  - Minimum 10 out-of-sample periods required to pass
- [ ] Performance metrics:
  - Total return, CAGR
  - Sharpe Ratio (target > 1.5)
  - Sortino Ratio
  - Max Drawdown (target < 20%)
  - Calmar Ratio
  - Win rate, profit factor
  - Average trade duration
  - Trades per month (check for overtrading)
- [ ] HTML/PDF report generator with equity curves, drawdown charts

**Gate:** No model or strategy goes live without passing backtest. This is law.

---

### PHASE 3 — AI Models
**Duration:** Week 4–6  
**Goal:** Three-layer AI decision engine trained and validated.

#### Week 4 — Regime Classifier + Sentiment

**Market Regime Classifier:**
- [ ] Labels: `trending_up`, `trending_down`, `ranging`, `volatile`, `crash`
- [ ] Features: ADX, ATR%, Bollinger width, 24h return, volume ratio, correlation matrix
- [ ] Model: LightGBM (fast, interpretable, handles missing features)
- [ ] Training: 2 years of labeled data, walk-forward validation
- [ ] Target: >75% accuracy on out-of-sample regimes

**Sentiment Pipeline:**
- [ ] FinBERT model for crypto news scoring
- [ ] Sources: CryptoPanic API (news), Fear & Greed Index (Alternative.me), Reddit via Pushshift
- [ ] Funding rate from Binance futures API (free)
- [ ] Output: Per-asset sentiment score updated every 15 minutes
- [ ] Cache in Redis with TTL

#### Week 5 — Temporal Fusion Transformer (TFT)

- [ ] Implement TFT using `pytorch-forecasting` library
- [ ] Inputs:
  - Past: OHLCV, all 50 indicators, order book metrics (168 hours lookback)
  - Future: Known future inputs (time of day, day of week, upcoming events)
  - Static: Asset metadata (market cap bucket, sector)
- [ ] Output: Quantile predictions (10th, 50th, 90th percentile) for next 4/8/12 candles
- [ ] Per-asset models for BTC, ETH, BNB + one universal model for altcoins
- [ ] GPU training if available, otherwise CPU (slower but works)
- [ ] Hyperparameter search with Optuna (50 trials)
- [ ] Validation: Directional accuracy > 55%, calibrated uncertainty

#### Week 6 — RL Agent + Ensemble

**Reinforcement Learning Agent:**
- [ ] Custom OpenAI Gym environment:
  - State: Portfolio state + market features + sentiment + model predictions
  - Actions: `{hold, buy_5%, buy_10%, buy_20%, sell_25%, sell_50%, sell_100%}` per asset
  - Reward: Risk-adjusted PnL minus fees, penalized for excessive trading
- [ ] Algorithm: PPO (Proximal Policy Optimization) via Stable-Baselines3
- [ ] Train on 18 months, validate on last 6 months
- [ ] Constrain: Max position limits, no shorting in phase 1

**Ensemble Signal Aggregator:**
```python
final_signal = (
    regime_weight * regime_score +       # 0.25
    tft_weight * tft_direction +         # 0.35
    rl_weight * rl_action +              # 0.25
    sentiment_weight * sentiment_score   # 0.15
)
# Weights adapt weekly based on recent signal accuracy
```

---

### PHASE 4 — Risk Engine & Execution
**Duration:** Week 7  
**Goal:** Capital protection and reliable order execution.

**Risk Manager:**
- [ ] Max 2% portfolio risk per trade (hard limit, never overridden)
- [ ] Max 5 concurrent positions
- [ ] Max 20% in any single asset
- [ ] Daily drawdown circuit breaker: halt all trading if down 5% in 24h
- [ ] Weekly drawdown circuit breaker: halt if down 10% in 7 days
- [ ] Correlation check: refuse new position if correlation >0.85 with existing
- [ ] Volatility-adjusted position sizing (ATR-based)
- [ ] Kelly Criterion for position sizing (use fractional Kelly: 25% of full Kelly)

**Order Manager:**
- [ ] Entry: Market orders (speed priority)
- [ ] Exit: Limit orders 0.1% above/below market (save fees)
- [ ] Always set stop-loss at entry (1.5–2.5× ATR below entry)
- [ ] Always set take-profit at entry (2:1 minimum risk/reward ratio)
- [ ] Dynamic trailing stop: move stop-loss up as price moves in your favor
- [ ] Order state machine: `PENDING → OPEN → PARTIAL → FILLED / CANCELLED`
- [ ] Retry logic with exponential backoff on API errors

**Fee Optimizer:**
- [ ] Use BNB for fee discount
- [ ] Prefer maker orders where possible
- [ ] Minimum trade size: $50 USDT (to keep fees under 0.3% impact)
- [ ] Monthly fee report

---

### PHASE 5 — Monitoring & Alerts
**Duration:** Week 8  
**Goal:** Full observability, never flying blind.

- [ ] Grafana dashboard panels:
  - Live P&L (realized + unrealized)
  - Open positions with entry/current price/stop/target
  - Win rate and Sharpe (rolling 30 days)
  - Max drawdown current period
  - Signal heatmap by asset
  - Model confidence over time
  - Fees paid (daily/monthly)
  - WebSocket health status
- [ ] Telegram bot alerts for:
  - Trade opened/closed (with details)
  - Stop-loss hit
  - Circuit breaker triggered
  - Model drift detected
  - System errors
  - Daily P&L summary at 00:00 UTC
- [ ] Health checks every 60 seconds:
  - WebSocket connections alive
  - DB write latency < 100ms
  - Model inference latency < 500ms
  - Binance API responding
  - Redis connected

---

### PHASE 6 — Paper Trading
**Duration:** Week 9–10 (minimum 2 weeks, no exceptions)  
**Goal:** Prove the system works end-to-end with zero financial risk.

- [ ] Paper trading mode: real market data, simulated orders, tracked P&L
- [ ] Run identically to live — same code path, just order execution is mocked
- [ ] Track: all metrics, all alerts, all model decisions
- [ ] Compare paper results vs backtest expectations
- [ ] Fix any discrepancies (slippage model, timing issues, etc.)
- [ ] Acceptance criteria to go live:
  - 2+ weeks of paper trading
  - Positive Sharpe ratio in paper period
  - No critical bugs or unexpected behaviors
  - All alerts firing correctly
  - Manual review of 20+ trade decisions (do they make sense?)

---

### PHASE 7 — Self-Driving Layer
**Duration:** Week 11–12 (can run in parallel with Phase 6)  
**Goal:** Bot improves itself without human intervention.

**Auto-Retraining Pipeline:**
- [ ] Drift detector using Evidently AI:
  - Monitor feature distributions vs training distribution
  - Monitor prediction confidence trends
  - Monitor Sharpe rolling 30d vs historical baseline
- [ ] Trigger retraining when: Sharpe drops >30%, or feature drift detected
- [ ] Retraining job: pull latest data, retrain all models, run backtest
- [ ] Shadow deployment: new model runs alongside old for 48 hours
- [ ] Auto-promote if new model outperforms old on live data
- [ ] Full version history of all models with performance logs

**Meta-Learning:**
- [ ] Store full context of every trade decision
- [ ] Weekly analysis: which signals predicted winners/losers?
- [ ] Adjust signal weights based on recent accuracy
- [ ] Learn temporal patterns: time-of-day, day-of-week effects
- [ ] Feed insights back into feature engineering

**Genetic Strategy Evolver (weekend job):**
- [ ] Population of 50 strategy parameter sets
- [ ] Backtest all 50 every weekend on rolling 3-month window
- [ ] Select top 25, breed new 25 with mutation
- [ ] Best strategy parameters auto-applied to live bot
- [ ] Full evolution history logged

---

### PHASE 8 — Go Live
**Duration:** Week 13+

**Week 13: Soft Launch**
- [ ] Deploy 10% of budget ($50–$500 depending on total)
- [ ] Monitor intensely for first week (check every few hours)
- [ ] Compare live results to paper trading and backtest

**Week 14–16: Scale Up**
- [ ] If first week Sharpe > 1.0: deploy 25% of budget
- [ ] If month 1 Sharpe > 1.5: deploy 50% of budget
- [ ] Never deploy 100% — keep 20% as reserve always

**Ongoing:**
- [ ] Weekly performance review
- [ ] Monthly model retraining (manual review even with auto-retrain)
- [ ] Quarterly strategy audit
- [ ] Annual security audit

---

## 🔐 Security Checklist

- [ ] API keys stored only in `.env` — never in code or git
- [ ] Binance API: enable IP whitelist to VPS IP only
- [ ] Binance API: enable Trade permissions only — NO withdrawal permission
- [ ] VPS: SSH key only (no password login)
- [ ] VPS: UFW firewall, only ports 22/80/443 open
- [ ] All secrets in environment variables, never hardcoded
- [ ] Rotate API keys every 90 days
- [ ] Keep 20–30% of budget in separate cold wallet, not on exchange

---

## 📊 Success Metrics

| Metric | Minimum | Target |
|---|---|---|
| Monthly Return | 3% | 8–15% |
| Sharpe Ratio | 1.0 | > 1.5 |
| Max Drawdown | < 20% | < 10% |
| Win Rate | 45% | > 55% |
| Profit Factor | 1.2 | > 1.5 |
| Uptime | 99% | 99.9% |
| Avg Trade Duration | — | 4–72 hours |

---

## 💰 Cost Estimate

| Item | Monthly Cost |
|---|---|
| VPS (4 core, 8GB RAM) | $20–40 |
| TimescaleDB Cloud (optional) | $0 (self-hosted) |
| CryptoPanic API | $0 (free tier) |
| Glassnode | $0 (free tier) |
| Telegram Bot | $0 |
| Grafana | $0 (self-hosted) |
| **Total Infrastructure** | **~$30/month** |

Binance trading fees: 0.075% per trade with BNB discount.

---

## 📚 Key Dependencies

```txt
# Core
python-binance==1.0.19
fastapi==0.111.0
uvicorn==0.30.0
celery==5.4.0
redis==5.0.4
asyncpg==0.29.0
alembic==1.13.0
pydantic-settings==2.3.0
structlog==24.2.0

# Data & Features
pandas==2.2.2
pandas-ta==0.3.14b
numpy==1.26.4
scikit-learn==1.5.0

# ML Models
torch==2.3.0
pytorch-forecasting==1.0.0
lightgbm==4.3.0
xgboost==2.0.3
stable-baselines3==2.3.0
gymnasium==0.29.1
transformers==4.41.0  # FinBERT
optuna==3.6.1

# Monitoring
evidently==0.4.30
python-telegram-bot==21.3

# Backtesting
vectorbt==0.26.1

# Utils
httpx==0.27.0
aiohttp==3.9.5
python-dotenv==1.0.1
pytest==8.2.2
pytest-asyncio==0.23.7
```
