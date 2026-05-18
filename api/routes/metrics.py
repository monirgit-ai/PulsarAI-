"""Prometheus metrics endpoint."""

from fastapi import APIRouter, Response

from monitoring.metrics import metrics_payload

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics() -> Response:
    return Response(content=metrics_payload(), media_type="text/plain; version=0.0.4; charset=utf-8")
