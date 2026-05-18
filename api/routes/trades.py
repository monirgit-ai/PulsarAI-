"""Trade read endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from execution.trade_repository import TradeRepository

router = APIRouter()
_repo = TradeRepository()


@router.get("/trades")
async def list_trades(status: str | None = None) -> dict:
    rows = await _repo.list_open_trades() if status == "OPEN" else await _list_all()
    return {"count": len(rows), "trades": rows}


async def _list_all() -> list[dict]:
    from data.storage import timescale

    pool = await timescale.get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, symbol, side, entry_price, exit_price, quantity, "
            "pnl_usdt, pnl_pct, fees_paid, status, opened_at, closed_at "
            "FROM trades ORDER BY opened_at DESC LIMIT 100"
        )
    return [dict(r) for r in rows]
