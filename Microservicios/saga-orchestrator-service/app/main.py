import asyncio
import os
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from shared.observability import configure_logging, log_context_middleware

TABLE_NAME = os.getenv("SAGA_TABLE_NAME", "charging-sagas-local")
DYNAMODB_ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL")
SERVICE_URLS = {
    "reservation": os.getenv("STATION_RESERVATION_URL", "http://station-reservation-service:8000"),
    "billing": os.getenv("BILLING_WALLET_URL", "http://billing-wallet-service:8000"),
    "dispatch": os.getenv("ENERGY_DISPATCH_URL", "http://energy-dispatch-service:8000"),
}
_saga_lock = threading.RLock()
_table: Any = None
logger = configure_logging("saga-orchestrator-service")


class ParticipantFailure(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class ParticipantUnavailable(Exception):
    pass


def _dynamodb_resource() -> Any:
    options: dict[str, Any] = {"region_name": os.getenv("AWS_DEFAULT_REGION", "us-east-1")}
    if DYNAMODB_ENDPOINT_URL:
        options["endpoint_url"] = DYNAMODB_ENDPOINT_URL
    return boto3.resource("dynamodb", **options)


def _initialize_table() -> Any:
    dynamodb = _dynamodb_resource()
    table = dynamodb.Table(TABLE_NAME)
    if DYNAMODB_ENDPOINT_URL:
        try:
            table.load()
        except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            try:
                table = dynamodb.create_table(
                    TableName=TABLE_NAME,
                    KeySchema=[{"AttributeName": "correlation_id", "KeyType": "HASH"}],
                    AttributeDefinitions=[
                        {"AttributeName": "correlation_id", "AttributeType": "S"},
                        {"AttributeName": "status", "AttributeType": "S"},
                        {"AttributeName": "updated_at", "AttributeType": "S"},
                    ],
                    GlobalSecondaryIndexes=[
                        {
                            "IndexName": "status-updated-at-index",
                            "KeySchema": [
                                {"AttributeName": "status", "KeyType": "HASH"},
                                {"AttributeName": "updated_at", "KeyType": "RANGE"},
                            ],
                            "Projection": {"ProjectionType": "ALL"},
                        }
                    ],
                    BillingMode="PAY_PER_REQUEST",
                )
                table.wait_until_exists()
            except ClientError as create_error:
                if create_error.response["Error"]["Code"] != "ResourceInUseException":
                    raise
                table = dynamodb.Table(TABLE_NAME)
                table.wait_until_exists()
        return table
    table.load()
    return table


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _table
    for attempt in range(10):
        try:
            _table = _initialize_table()
            break
        except (BotoCoreError, ClientError) as error:
            if attempt == 9:
                raise RuntimeError(f"Unable to initialize SAGA table {TABLE_NAME}") from error
            await asyncio.sleep(2)
    yield
    _table = None


app = FastAPI(title="Charge Activation Saga Orchestrator", lifespan=lifespan)
app.middleware("http")(log_context_middleware(logger))


class ChargeActivationRequest(BaseModel):
    correlation_id: UUID
    fleet_id: str = Field(min_length=1, max_length=128)
    connector_id: str = Field(min_length=1, max_length=128)
    estimated_amount_cents: int = Field(gt=0)
    reservation_duration_seconds: int = Field(default=300, ge=30, le=3600)
    charging_duration_seconds: int = Field(default=60, ge=1, le=3600)


def _load_saga(correlation_id: str) -> dict[str, Any] | None:
    response = _table.get_item(Key={"correlation_id": correlation_id}, ConsistentRead=True)
    item = response.get("Item")
    if item is None:
        return None
    item.pop("pk", None)
    if "revision" in item:
        item["revision"] = int(item["revision"])
    return item


def _save_saga(saga: dict[str, Any]) -> None:
    saga["updated_at"] = datetime.now(UTC).isoformat()
    expected_revision = saga.get("revision")
    saga["revision"] = (expected_revision or 0) + 1
    try:
        if expected_revision is None:
            _table.put_item(
                Item=saga,
                ConditionExpression="attribute_not_exists(correlation_id)",
            )
        else:
            _table.put_item(
                Item=saga,
                ConditionExpression="revision = :expected_revision",
                ExpressionAttributeValues={":expected_revision": expected_revision},
            )
    except ClientError as error:
        saga["revision"] = expected_revision
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise HTTPException(
                status_code=409,
                detail="Saga state changed concurrently; retry with the same correlation ID",
            ) from error
        raise
    logger.info(
        "saga_state_saved",
        extra={
            "correlation_id": saga["correlation_id"],
            "saga_status": saga["status"],
            "step": saga["step"],
        },
    )


def _participant_call(
    service: str,
    method: str,
    path: str,
    correlation_id: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = httpx.request(
            method,
            f"{SERVICE_URLS[service]}{path}",
            json=payload,
            headers={"X-Correlation-ID": correlation_id},
            timeout=5.0,
        )
    except httpx.RequestError as error:
        raise ParticipantUnavailable(f"{service} service could not be reached: {error}") from error

    try:
        body = response.json()
    except ValueError as error:
        raise ParticipantUnavailable(
            f"{service} service returned a non-JSON response with status {response.status_code}"
        ) from error
    if not response.is_success:
        detail = body.get("detail", body) if isinstance(body, dict) else body
        raise ParticipantFailure(response.status_code, detail)
    if not isinstance(body, dict):
        raise ParticipantUnavailable(f"{service} service returned an unexpected response")
    return body


def _failure(service: str, step: str, error: ParticipantFailure | ParticipantUnavailable) -> dict[str, Any]:
    failure: dict[str, Any] = {"service": service, "step": step, "message": str(error)}
    if isinstance(error, ParticipantFailure):
        failure.update(status_code=error.status_code, detail=error.detail)
    return failure


def _mark_retryable(
    saga: dict[str, Any], service: str, step: str, error: ParticipantUnavailable
) -> None:
    saga.update(
        status="RETRYABLE",
        step=step,
        failure=_failure(service, step, error),
    )
    _save_saga(saga)


def _begin_compensation(saga: dict[str, Any], failure: dict[str, Any]) -> None:
    saga.update(
        status="COMPENSATING",
        step="REFUNDING" if saga.get("charge") else "RELEASING",
        failure=failure,
        compensation_error=None,
    )
    _save_saga(saga)


def _compensate(saga: dict[str, Any]) -> dict[str, Any]:
    correlation_id = saga["correlation_id"]
    if saga["step"] == "REFUNDING":
        try:
            saga["refund"] = _participant_call(
                "billing",
                "POST",
                f"/correlations/{quote(correlation_id, safe='')}/refunds",
                correlation_id,
                {"idempotency_key": correlation_id, "correlation_id": correlation_id},
            )
        except (ParticipantFailure, ParticipantUnavailable) as error:
            saga.update(
                status="COMPENSATION_PENDING",
                compensation_error=_failure("billing", "REFUNDING", error),
            )
            _save_saga(saga)
            return saga
        saga.update(step="RELEASING", compensation_error=None)
        _save_saga(saga)

    if saga["step"] == "RELEASING":
        reservation = saga.get("reservation")
        if reservation is not None:
            connector_id = quote(saga["request"]["connector_id"], safe="")
            reservation_id = quote(reservation["reservation_id"], safe="")
            try:
                _participant_call(
                    "reservation",
                    "DELETE",
                    f"/connectors/{connector_id}/reservations/{reservation_id}",
                    correlation_id,
                )
            except (ParticipantFailure, ParticipantUnavailable) as error:
                saga.update(
                    status="COMPENSATION_PENDING",
                    compensation_error=_failure("reservation", "RELEASING", error),
                )
                _save_saga(saga)
                return saga
        saga.update(status="COMPENSATED", step="COMPLETED", compensation_error=None)
        _save_saga(saga)
    return saga


def _run_saga(saga: dict[str, Any]) -> dict[str, Any]:
    correlation_id = saga["correlation_id"]
    request = saga["request"]

    if saga["status"] in {"COMPENSATING", "COMPENSATION_PENDING"}:
        saga["status"] = "COMPENSATING"
        _save_saga(saga)
        return _compensate(saga)
    if saga["status"] in {"SUCCEEDED", "COMPENSATED", "FAILED"}:
        return saga

    if saga["step"] == "RESERVING":
        try:
            saga["reservation"] = _participant_call(
                "reservation",
                "POST",
                f"/connectors/{quote(request['connector_id'], safe='')}/reservations",
                correlation_id,
                {
                    "fleet_id": request["fleet_id"],
                    "duration_seconds": request["reservation_duration_seconds"],
                    "reservation_id": correlation_id,
                    "correlation_id": correlation_id,
                },
            )
        except ParticipantUnavailable as error:
            _mark_retryable(saga, "reservation", "RESERVING", error)
            return saga
        except ParticipantFailure as error:
            if error.status_code >= 500:
                _mark_retryable(saga, "reservation", "RESERVING", ParticipantUnavailable(str(error)))
                return saga
            saga.update(
                status="FAILED",
                step="FAILED",
                failure=_failure("reservation", "RESERVING", error),
            )
            _save_saga(saga)
            return saga
        saga.update(status="STARTED", step="CHARGING")
        _save_saga(saga)

    if saga["step"] == "CHARGING":
        try:
            saga["charge"] = _participant_call(
                "billing",
                "POST",
                "/charges",
                correlation_id,
                {
                    "fleet_id": request["fleet_id"],
                    "reservation_id": correlation_id,
                    "estimated_amount_cents": request["estimated_amount_cents"],
                    "idempotency_key": correlation_id,
                    "correlation_id": correlation_id,
                },
            )
        except ParticipantUnavailable as error:
            _mark_retryable(saga, "billing", "CHARGING", error)
            return saga
        except ParticipantFailure as error:
            if error.status_code >= 500:
                _mark_retryable(saga, "billing", "CHARGING", ParticipantUnavailable(str(error)))
                return saga
            _begin_compensation(saga, _failure("billing", "CHARGING", error))
            return _compensate(saga)
        saga.update(status="STARTED", step="DISPATCHING")
        _save_saga(saga)

    if saga["step"] == "DISPATCHING":
        try:
            saga["dispatch"] = _participant_call(
                "dispatch",
                "POST",
                "/dispatches",
                correlation_id,
                {
                    "reservation_id": correlation_id,
                    "connector_id": request["connector_id"],
                    "duration_seconds": request["charging_duration_seconds"],
                    "correlation_id": correlation_id,
                },
            )
        except ParticipantUnavailable as error:
            _mark_retryable(saga, "dispatch", "DISPATCHING", error)
            return saga
        except ParticipantFailure as error:
            detail = error.detail
            simulated_fault = (
                error.status_code == 503
                and isinstance(detail, dict)
                and detail.get("code") == "SIMULATED_HARDWARE_FAULT"
            )
            if error.status_code >= 500 and not simulated_fault:
                _mark_retryable(saga, "dispatch", "DISPATCHING", ParticipantUnavailable(str(error)))
                return saga
            _begin_compensation(saga, _failure("dispatch", "DISPATCHING", error))
            return _compensate(saga)
        saga.update(status="SUCCEEDED", step="COMPLETED", failure=None)
        _save_saga(saga)

    return saga


def _response(saga: dict[str, Any]) -> JSONResponse:
    status_code = 202 if saga["status"] in {"RETRYABLE", "COMPENSATION_PENDING"} else 200
    return JSONResponse(status_code=status_code, content=saga)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/sagas/reserve-and-activate")
def reserve_and_activate(request: ChargeActivationRequest) -> JSONResponse:
    correlation_id = str(request.correlation_id)
    request_document = request.model_dump(mode="json")
    with _saga_lock:
        saga = _load_saga(correlation_id)
        if saga is None:
            saga = {
                "correlation_id": correlation_id,
                "request": request_document,
                "status": "STARTED",
                "step": "RESERVING",
                "reservation": None,
                "charge": None,
                "dispatch": None,
                "refund": None,
                "failure": None,
                "compensation_error": None,
            }
            try:
                _save_saga(saga)
            except HTTPException as error:
                if error.status_code != 409:
                    raise
                saga = _load_saga(correlation_id)
                if saga is None:
                    raise
        if saga["request"] != request_document:
            raise HTTPException(
                status_code=409,
                detail="Correlation ID was already used for a different saga request",
            )
        return _response(_run_saga(saga))


@app.get("/sagas/{correlation_id}")
def get_saga(correlation_id: UUID) -> dict[str, Any]:
    with _saga_lock:
        saga = _load_saga(str(correlation_id))
    if saga is None:
        raise HTTPException(status_code=404, detail="Saga not found")
    return saga
