import json
import os
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx
import strawberry
from fastapi import FastAPI
from graphql import GraphQLError
from strawberry.fastapi import GraphQLRouter
from strawberry.scalars import JSON

from shared.observability import configure_logging, log_context_middleware

SERVICE_URLS = {
    "reservation": os.getenv("STATION_RESERVATION_URL", "http://station-reservation-service:8000"),
    "dispatch": os.getenv("ENERGY_DISPATCH_URL", "http://energy-dispatch-service:8000"),
    "saga": os.getenv("SAGA_ORCHESTRATOR_URL", "http://saga-orchestrator-service:8000"),
}
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
STREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
logger = configure_logging("graphql-api-gateway")


async def _request_json(
    service: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    headers = {"X-Correlation-ID": correlation_id} if correlation_id else {}
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.request(
                method,
                f"{SERVICE_URLS[service]}{path}",
                json=payload,
                headers=headers,
            )
    except httpx.RequestError as error:
        raise GraphQLError(
            f"{service} service is unavailable",
            extensions={"code": "SERVICE_UNAVAILABLE", "service": service},
        ) from error

    try:
        result = response.json()
    except ValueError as error:
        raise GraphQLError(
            f"{service} service returned an invalid response",
            extensions={"code": "INVALID_UPSTREAM_RESPONSE", "service": service},
        ) from error
    if not response.is_success:
        detail = result.get("detail", result) if isinstance(result, dict) else result
        message = detail if isinstance(detail, str) else json.dumps(detail)
        raise GraphQLError(
            message,
            extensions={
                "code": "UPSTREAM_ERROR",
                "service": service,
                "statusCode": response.status_code,
                "detail": detail,
            },
        )
    if not isinstance(result, dict):
        raise GraphQLError(
            f"{service} service returned an unexpected response",
            extensions={"code": "INVALID_UPSTREAM_RESPONSE", "service": service},
        )
    return result


@strawberry.input
class StartChargingSessionInput:
    correlation_id: UUID
    fleet_id: str
    connector_id: str
    estimated_amount_cents: int
    reservation_duration_seconds: int = 300
    charging_duration_seconds: int = 60


@strawberry.type
class Query:
    @strawberry.field
    async def station_status(self, connector_id: str) -> JSON:
        connector = quote(connector_id, safe="")
        return await _request_json(
            "reservation",
            "GET",
            f"/connectors/{connector}/availability",
        )

    @strawberry.field
    async def charging_session(self, dispatch_id: strawberry.ID) -> JSON:
        dispatch = quote(str(dispatch_id), safe="")
        return await _request_json("dispatch", "GET", f"/dispatches/{dispatch}")

    @strawberry.field
    async def latest_telemetry(self, dispatch_id: strawberry.ID) -> JSON:
        dispatch = quote(str(dispatch_id), safe="")
        return await _request_json("dispatch", "GET", f"/dispatches/{dispatch}/telemetry/latest")

    @strawberry.field
    async def saga_status(self, correlation_id: UUID) -> JSON:
        return await _request_json("saga", "GET", f"/sagas/{correlation_id}")


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def start_charging_session(self, input: StartChargingSessionInput) -> JSON:
        if input.estimated_amount_cents <= 0:
            raise GraphQLError(
                "estimatedAmountCents must be greater than zero",
                extensions={"code": "BAD_USER_INPUT"},
            )
        if not 30 <= input.reservation_duration_seconds <= 3600:
            raise GraphQLError(
                "reservationDurationSeconds must be between 30 and 3600",
                extensions={"code": "BAD_USER_INPUT"},
            )
        if not 1 <= input.charging_duration_seconds <= 3600:
            raise GraphQLError(
                "chargingDurationSeconds must be between 1 and 3600",
                extensions={"code": "BAD_USER_INPUT"},
            )
        correlation_id = str(input.correlation_id)
        logger.info("saga_request_started", extra={"correlation_id": correlation_id})
        result = await _request_json(
            "saga",
            "POST",
            "/sagas/reserve-and-activate",
            payload={
                "correlation_id": correlation_id,
                "fleet_id": input.fleet_id,
                "connector_id": input.connector_id,
                "estimated_amount_cents": input.estimated_amount_cents,
                "reservation_duration_seconds": input.reservation_duration_seconds,
                "charging_duration_seconds": input.charging_duration_seconds,
            },
            correlation_id=correlation_id,
        )
        logger.info(
            "saga_request_completed",
            extra={"correlation_id": correlation_id, "saga_status": result.get("status")},
        )
        return result


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def telemetry(self, dispatch_id: strawberry.ID) -> AsyncGenerator[JSON, None]:
        dispatch = quote(str(dispatch_id), safe="")
        url = f"{SERVICE_URLS['dispatch']}/dispatches/{dispatch}/telemetry"
        try:
            async with (
                httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client,
                client.stream("GET", url) as response,
            ):
                    if not response.is_success:
                        try:
                            body = await response.aread()
                            detail = response.json() if body else {}
                            message = detail.get("detail", detail) if isinstance(detail, dict) else detail
                        except ValueError:
                            message = "Energy dispatch service returned an invalid response"
                        raise GraphQLError(
                            str(message),
                            extensions={
                                "code": "UPSTREAM_ERROR",
                                "service": "dispatch",
                                "statusCode": response.status_code,
                            },
                        )

                    event_data: list[str] = []
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            event_data.append(line[5:].strip())
                        elif not line and event_data:
                            try:
                                event = json.loads("\n".join(event_data))
                            except json.JSONDecodeError as error:
                                raise GraphQLError(
                                    "Energy dispatch service emitted invalid telemetry",
                                    extensions={
                                        "code": "INVALID_UPSTREAM_RESPONSE",
                                        "service": "dispatch",
                                    },
                                ) from error
                            event_data.clear()
                            yield event
        except httpx.RequestError as error:
            raise GraphQLError(
                "energy dispatch service is unavailable",
                extensions={"code": "SERVICE_UNAVAILABLE", "service": "dispatch"},
            ) from error


schema = strawberry.Schema(query=Query, mutation=Mutation, subscription=Subscription)
graphql_app = GraphQLRouter(
    schema,
    subscription_protocols=("graphql-transport-ws",),
)
app = FastAPI(title="Charging GraphQL API Gateway")
app.middleware("http")(log_context_middleware(logger))
app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
