# PulsarAI

AI self-driving cryptocurrency trading bot for Binance (spot).  
**Dev workflow:** Laptop (Docker Desktop) → GitHub → Ubuntu server.

## Build status

**Phase 1:** Docker stack, TimescaleDB, FastAPI, bot health, Telegram alerts, Binance ingestion.  
**Phase 2:** Event-driven backtesting, walk-forward validation, HTML reports.  
**Phase 3:** Regime (LightGBM), sentiment (FinBERT), TFT/LSTM forecaster, RL (PPO), ensemble signals.  
**Phase 4:** Risk manager, circuit breaker, position sizing, paper/live execution, order manager.  
**Phase 5:** Prometheus metrics, Grafana dashboards, full Telegram alerts, scheduler, drift detection.

## Quick start (laptop)

### 1. Environment

```powershell
copy .env.example .env
# Edit .env — optional: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, TELEGRAM_ALERTS_ENABLED=true
```

### 2. Start stack

```powershell
docker compose -f docker/docker-compose.yml up -d --build
```

### 3. Verify

| Service | URL / Port |
|---------|------------|
| API docs | http://localhost:18888/docs |
| Health | http://localhost:18888/api/v1/health |
| Grafana | http://localhost:13000 (admin / see `.env`) |
| PostgreSQL | `localhost:15432` |
| Redis | `localhost:16379` |
| Prometheus | http://localhost:19090 |

Ports are intentionally **non-standard** to avoid conflicts with other projects.

### 4. Logs

```powershell
docker compose -f docker/docker-compose.yml logs -f bot api
```

### 5. Download history + features

```powershell
# Inside running stack (7 days quick test)
docker compose -f docker/docker-compose.yml run --rm api python scripts/download_history.py --days 7 --features

# Or locally with venv + DB on localhost:15432
python scripts/download_history.py --days 30 --features
```

### 6. Run backtest

```powershell
# Single backtest (uses DB candles)
docker compose -f docker/docker-compose.yml run --rm api python scripts/run_backtest.py --symbol BTCUSDT --timeframe 1h

# Walk-forward validation (needs ~12+ months of 1h data for 10 OOS periods)
docker compose -f docker/docker-compose.yml run --rm api python scripts/run_backtest.py --symbol BTCUSDT --walk-forward

# Reports saved to reports/ (HTML with equity and drawdown charts)
```

### 7. Train AI models (Phase 3)

Requires 500+ candles in DB per symbol/timeframe.

```powershell
docker compose -f docker/docker-compose.yml build api
docker compose -f docker/docker-compose.yml run --rm api python scripts/download_history.py --symbol BTCUSDT --days 180 --intervals 1h

# Train regime + TFT + RL (CPU; may take 10-30 min)
docker compose -f docker/docker-compose.yml run --rm api python scripts/train_models.py --symbol BTCUSDT --timeframe 1h

# Generate ensemble signal
docker compose -f docker/docker-compose.yml run --rm api python scripts/predict_signal.py --symbol BTCUSDT
```

Artifacts saved under `models/artifacts/` (gitignored).

### 8. Paper trade one cycle (Phase 4)

Requires trained models and `PAPER_TRADING=true` in `.env`.

```powershell
docker compose -f docker/docker-compose.yml run --rm api python scripts/paper_trade.py --symbol BTCUSDT
```

Flow: ensemble signal → `RiskManager.validate()` → paper fill → `trades` table.

### 9. Monitoring (Phase 5)

| Service | URL |
|---------|-----|
| Grafana dashboards | http://localhost:13000 (login: see `.env` `GF_SECURITY_*`) |
| Prometheus | http://localhost:19090 |
| Metrics | http://localhost:18888/metrics |

The `scheduler` service refreshes portfolio metrics, runs drift checks, and sends the daily P&L summary at 00:00 UTC.

**Telegram commands** (optional, whitelist your chat ID):

```env
TELEGRAM_COMMANDS_ENABLED=true
```

Then message your bot: `/status`, `/positions`, `/pnl`

### 10. Tests (local Python)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest tests/ -q
```

## Telegram setup

1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy token into `.env`
2. Start your bot in Telegram → send a message
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy `chat.id` → `TELEGRAM_CHAT_ID`
4. Set `TELEGRAM_ALERTS_ENABLED=true` and restart: `docker compose -f docker/docker-compose.yml up -d bot`

## Server deploy

```bash
cp .env.example .env   # configure on server only
./scripts/deploy.sh
```

## Project docs

- [AI_Trading_Bot_Project_Plan.md](AI_Trading_Bot_Project_Plan.md) — full roadmap
- [.cursor/rules/project.mdc](.cursor/rules/project.mdc) — coding rules

## License

See [LICENSE](LICENSE).
