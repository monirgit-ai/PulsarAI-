"""Trade read endpoints (Phase 4+)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/trades")
async def list_trades() -> dict:
    return {"trades": [], "message": "Trade history available after execution module (Phase 4)."}
