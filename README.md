# PulsarAI

AI self-driving cryptocurrency trading bot for Binance (spot).  
**Dev workflow:** Laptop (Docker Desktop) → GitHub → Ubuntu server.

## Phase 1 (current)

**Week 1:** Docker stack, TimescaleDB, FastAPI, bot health loop, Telegram alerts.  
**Week 2:** Binance historical download, live WebSocket klines, feature engineering.  
**Phase 2:** Event-driven backtesting, walk-forward validation, HTML reports.

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

### 7. Tests (local Python)

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
