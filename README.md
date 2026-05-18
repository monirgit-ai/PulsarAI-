# PulsarAI

AI self-driving cryptocurrency trading bot for Binance (spot).  
**Dev workflow:** Laptop (Docker Desktop) → GitHub → Ubuntu server.

## Phase 1 (current)

Infrastructure: Docker stack, TimescaleDB schema, FastAPI health API, bot health loop, Telegram alert stub.

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

### 5. Tests (local Python)

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
