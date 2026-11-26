import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared.observability import configure_logging, log_context_middleware

TELEMETRY_INTERVAL_SECONDS = float(os.getenv("TELEMETRY_INTERVAL_SECONDS", "2"))
if TELEMETRY_INTERVAL_SECONDS <= 0:
    raise ValueError("TELEMETRY_INTERVAL_SECONDS must be greater than zero")
SIMULATE_CHARGER_HARDWARE_FAULT = os.getenv(
    "SIMULATE_CHARGER_HARDWARE_FAULT", "false"
).lower() == "true"


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Dispatch:
    dispatch_id: str
    reservation_id: str
    connector_id: str
    duration_seconds: int
    correlation_id: str
    status: str = "active"
    started_at: datetime = field(default_factory=_utc_now)
    latest_telemetry: dict[str, Any] | None = None
    events: asyncio.Queue[dict[str, Any] | None] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None


_dispatches: dict[str, Dispatch] = {}
_active_connectors: dict[str, str] = {}
_dispatches_by_correlation: dict[str, Dispatch] = {}
logger = configure_logging("energy-dispatch-service")

app = FastAPI(title="Energy Dispatch Service")
app.middleware("http")(log_context_middleware(logger))


class DispatchRequest(BaseModel):
    reservation_id: str = Field(min_length=1, max_length=128)
    connector_id: str = Field(min_length=1, max_length=128)
    duration_seconds: int = Field(default=60, ge=1, le=3600)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)


class DispatchResponse(BaseModel):
    dispatch_id: str
    reservation_id: str
    connector_id: str
    duration_seconds: int
    correlation_id: str
    status: str
    started_at: datetime


def _as_response(dispatch: Dispatch) -> dict[str, Any]:
    return {
        "dispatch_id": dispatch.dispatch_id,
        "reservation_id": dispatch.reservation_id,
        "connector_id": dispatch.connector_id,
        "duration_seconds": dispatch.duration_seconds,
        "correlation_id": dispatch.correlation_id,
        "status": dispatch.status,
        "started_at": dispatch.started_at,
    }


async def _simulate_charging(dispatch: Dispatch) -> None:
    loop = asyncio.get_running_loop()
    end_time = loop.time() + dispatch.duration_seconds
    energy_kwh = 0.0
    try:
        while loop.time() < end_time:
            telemetry = {
                "dispatch_id": dispatch.dispatch_id,
                "connector_id": dispatch.connector_id,
                "timestamp": _utc_now().isoformat(),
                "power_kw": 7.2,
                "energy_kwh": round(energy_kwh, 3),
                "state": "charging",
            }
            dispatch.latest_telemetry = telemetry
            dispatch.events.put_nowait(telemetry)
            sample_seconds = min(TELEMETRY_INTERVAL_SECONDS, max(0, end_time - loop.time()))
            await asyncio.sleep(sample_seconds)
            energy_kwh += 7.2 * sample_seconds / 3600
        dispatch.status = "completed"
        _active_connectors.pop(dispatch.connector_id, None)
        dispatch.events.put_nowait(
            {
                "dispatch_id": dispatch.dispatch_id,
                "connector_id": dispatch.connector_id,
                "timestamp": _utc_now().isoformat(),
                "power_kw": 0.0,
                "energy_kwh": round(energy_kwh, 3),
                "state": "completed",
            }
        )
    except asyncio.CancelledError:
        dispatch.events.put_nowait(None)
        raise
    finally:
        if dispatch.status != "active":
            _active_connectors.pop(dispatch.connector_id, None)
    dispatch.events.put_nowait(None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/dispatches", response_model=DispatchResponse, status_code=202)
async def start_dispatch(
    request: DispatchRequest,
    correlation_header: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> dict[str, Any]:
    if request.correlation_id and correlation_header and request.correlation_id != correlation_header:
        raise HTTPException(status_code=400, detail="Correlation ID does not match request body")
    correlation_id = request.correlation_id or correlation_header or str(uuid.uuid4())
    existing = _dispatches_by_correlation.get(correlation_id)
    if existing is not None:
        if (
            existing.reservation_id != request.reservation_id
            or existing.connector_id != request.connector_id
            or existing.duration_seconds != request.duration_seconds
        ):
            raise HTTPException(status_code=409, detail="Correlation ID was used for a different dispatch")
        return _as_response(existing)

    if SIMULATE_CHARGER_HARDWARE_FAULT:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "SIMULATED_HARDWARE_FAULT",
                "message": "Simulated charger hardware activation failure",
            },
        )
    if request.connector_id in _active_connectors:
        raise HTTPException(status_code=409, detail="Connector already has an active dispatch")

    dispatch = Dispatch(
        dispatch_id=str(uuid.uuid4()),
        reservation_id=request.reservation_id,
        connector_id=request.connector_id,
        duration_seconds=request.duration_seconds,
        correlation_id=correlation_id,
    )
    _dispatches[dispatch.dispatch_id] = dispatch
    _dispatches_by_correlation[correlation_id] = dispatch
    _active_connectors[dispatch.connector_id] = dispatch.dispatch_id
    dispatch.task = asyncio.create_task(_simulate_charging(dispatch))
    return _as_response(dispatch)


@app.get("/dispatches/{dispatch_id}", response_model=DispatchResponse)
def get_dispatch(dispatch_id: str) -> dict[str, Any]:
    dispatch = _dispatches.get(dispatch_id)
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return _as_response(dispatch)


@app.get("/dispatches/{dispatch_id}/telemetry/latest")
def latest_telemetry(dispatch_id: str) -> dict[str, Any]:
    dispatch = _dispatches.get(dispatch_id)
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if dispatch.latest_telemetry is None:
        raise HTTPException(status_code=404, detail="Telemetry is not available yet")
    return dispatch.latest_telemetry


@app.get("/dispatches/{dispatch_id}/telemetry")
async def telemetry_stream(dispatch_id: str) -> StreamingResponse:
    dispatch = _dispatches.get(dispatch_id)
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")

    async def stream() -> AsyncIterator[str]:
        while True:
            event = await dispatch.events.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@app.post("/dispatches/{dispatch_id}/stop", response_model=DispatchResponse)
async def stop_dispatch(dispatch_id: str) -> dict[str, Any]:
    dispatch = _dispatches.get(dispatch_id)
    if dispatch is None:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if dispatch.status == "active":
        dispatch.status = "stopped"
        if dispatch.task is not None:
            dispatch.task.cancel()
            try:
                await dispatch.task
            except asyncio.CancelledError:
                pass
        _active_connectors.pop(dispatch.connector_id, None)
    return _as_response(dispatch)
