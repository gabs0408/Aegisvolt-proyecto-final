import asyncio
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from shared.observability import configure_logging, log_context_middleware

TABLE_NAME = os.getenv("TABLE_NAME", "connector-locks-local")
DYNAMODB_ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL")
_table: Any = None
logger = configure_logging("station-reservation-service")


def _dynamodb_resource() -> Any:
    options: dict[str, Any] = {"region_name": os.getenv("AWS_DEFAULT_REGION", "us-east-1")}
    if DYNAMODB_ENDPOINT_URL:
        options["endpoint_url"] = DYNAMODB_ENDPOINT_URL
    return boto3.resource("dynamodb", **options)


def _ensure_table() -> Any:
    dynamodb = _dynamodb_resource()
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.load()
        return table
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    try:
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()
        return table
    except ClientError as error:
        if error.response["Error"]["Code"] != "ResourceInUseException":
            raise
        table = dynamodb.Table(TABLE_NAME)
        table.wait_until_exists()
        return table


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _table
    for attempt in range(10):
        try:
            _table = _ensure_table()
            break
        except (BotoCoreError, ClientError) as error:
            if attempt == 9:
                raise RuntimeError(f"Unable to initialize DynamoDB table {TABLE_NAME}") from error
            await asyncio.sleep(2)
    yield
    _table = None


app = FastAPI(title="Station Reservation Service", lifespan=lifespan)
app.middleware("http")(log_context_middleware(logger))


class ReservationRequest(BaseModel):
    fleet_id: str = Field(min_length=1, max_length=128)
    duration_seconds: int = Field(default=300, ge=30, le=3600)
    reservation_id: str | None = Field(default=None, min_length=1, max_length=128)
    correlation_id: str | None = Field(default=None, min_length=1, max_length=128)


class ReservationResponse(BaseModel):
    reservation_id: str
    connector_id: str
    fleet_id: str
    correlation_id: str
    expires_at: datetime
    status: str


def _table_or_error() -> Any:
    if _table is None:
        raise HTTPException(status_code=503, detail="Reservation storage is not initialized")
    return _table


@app.get("/health")
def health() -> dict[str, str]:
    if _table is None:
        raise HTTPException(status_code=503, detail="Reservation storage is not initialized")
    return {"status": "ok"}


@app.get("/connectors/{connector_id}/availability")
def connector_availability(connector_id: str) -> dict[str, Any]:
    now = int(time.time())
    response = _table_or_error().get_item(Key={"pk": f"CONNECTOR#{connector_id}", "sk": "LOCK"})
    lock = response.get("Item")
    available = lock is None or int(lock["expires_at"]) <= now
    result: dict[str, Any] = {
        "connector_id": connector_id,
        "available": available,
        "status": "AVAILABLE" if available else "RESERVED",
    }
    if lock is not None and not available:
        result.update(
            reservation_id=lock["reservation_id"],
            expires_at=datetime.fromtimestamp(int(lock["expires_at"]), UTC),
        )
    return result


@app.post("/connectors/{connector_id}/reservations", response_model=ReservationResponse)
def reserve_connector(
    connector_id: str,
    request: ReservationRequest,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> dict[str, Any]:
    if request.correlation_id and correlation_id and request.correlation_id != correlation_id:
        raise HTTPException(status_code=400, detail="Correlation ID does not match request body")
    now = int(time.time())
    reservation_id = request.reservation_id or str(uuid.uuid4())
    correlation_id = request.correlation_id or correlation_id or reservation_id
    expires_at = now + request.duration_seconds
    item = {
        "pk": f"CONNECTOR#{connector_id}",
        "sk": "LOCK",
        "reservation_id": reservation_id,
        "connector_id": connector_id,
        "fleet_id": request.fleet_id,
        "correlation_id": correlation_id,
        "status": "RESERVED",
        "expires_at": expires_at,
    }

    try:
        _table_or_error().put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk) OR expires_at <= :now",
            ExpressionAttributeValues={":now": now},
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            existing = _table_or_error().get_item(
                Key={"pk": f"CONNECTOR#{connector_id}", "sk": "LOCK"}
            ).get("Item")
            if (
                existing is not None
                and existing["reservation_id"] == reservation_id
                and existing["fleet_id"] == request.fleet_id
                and existing.get("correlation_id", reservation_id) == correlation_id
            ):
                return {
                    "reservation_id": reservation_id,
                    "connector_id": connector_id,
                    "fleet_id": request.fleet_id,
                    "correlation_id": correlation_id,
                    "expires_at": datetime.fromtimestamp(int(existing["expires_at"]), UTC),
                    "status": "RESERVED",
                }
            raise HTTPException(status_code=409, detail="Connector is already reserved") from error
        raise

    return {
        "reservation_id": reservation_id,
        "connector_id": connector_id,
        "fleet_id": request.fleet_id,
        "correlation_id": correlation_id,
        "expires_at": datetime.fromtimestamp(expires_at, UTC),
        "status": "RESERVED",
    }


@app.delete("/connectors/{connector_id}/reservations/{reservation_id}")
def release_reservation(
    connector_id: str,
    reservation_id: str,
    correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> dict[str, str]:
    table = _table_or_error()
    key = {"pk": f"CONNECTOR#{connector_id}", "sk": "LOCK"}
    existing = table.get_item(Key=key).get("Item")
    if existing is None:
        return {"reservation_id": reservation_id, "status": "AVAILABLE"}
    if existing["reservation_id"] != reservation_id:
        raise HTTPException(status_code=409, detail="Connector is reserved by a different reservation")
    if correlation_id and existing.get("correlation_id", reservation_id) != correlation_id:
        raise HTTPException(status_code=409, detail="Correlation ID does not match reservation")

    condition = "reservation_id = :reservation_id"
    values = {":reservation_id": reservation_id}
    if "correlation_id" in existing:
        condition += " AND correlation_id = :stored_correlation_id"
        values[":stored_correlation_id"] = existing["correlation_id"]
    try:
        table.delete_item(
            Key=key,
            ConditionExpression=condition,
            ExpressionAttributeValues=values,
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            latest = table.get_item(Key=key).get("Item")
            if latest is None:
                return {"reservation_id": reservation_id, "status": "AVAILABLE"}
            raise HTTPException(status_code=409, detail="Connector is reserved by a different reservation") from error
        raise
    return {"reservation_id": reservation_id, "status": "AVAILABLE"}
