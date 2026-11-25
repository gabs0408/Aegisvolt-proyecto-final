import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from graphql import GraphQLError

sys.path.insert(0, str(Path(__file__).parents[1]))
sys.path.insert(0, str(Path(__file__).parents[1] / "graphql-api-gateway"))
from app import main as gateway


def test_station_status_query_aggregates_reservation_service(monkeypatch):
    async def request_json(service, method, path, **kwargs):
        assert (service, method, path) == (
            "reservation",
            "GET",
            "/connectors/connector-1/availability",
        )
        return {"connector_id": "connector-1", "available": True, "status": "AVAILABLE"}

    monkeypatch.setattr(gateway, "_request_json", request_json)
    result = asyncio.run(
        gateway.schema.execute('{ stationStatus(connectorId: "connector-1") }')
    )

    assert result.errors is None
    assert result.data == {
        "stationStatus": {
            "connector_id": "connector-1",
            "available": True,
            "status": "AVAILABLE",
        }
    }


def test_start_charging_session_routes_through_saga(monkeypatch):
    correlation_id = str(uuid4())
    calls = []

    async def request_json(service, method, path, **kwargs):
        calls.append((service, method, path, kwargs))
        return {"correlation_id": correlation_id, "status": "SUCCEEDED"}

    monkeypatch.setattr(gateway, "_request_json", request_json)
    result = asyncio.run(
        gateway.schema.execute(
            """
            mutation Start($input: StartChargingSessionInput!) {
              startChargingSession(input: $input)
            }
            """,
            variable_values={
                "input": {
                    "correlationId": correlation_id,
                    "fleetId": "fleet-1",
                    "connectorId": "connector-1",
                    "estimatedAmountCents": 1200,
                    "reservationDurationSeconds": 300,
                    "chargingDurationSeconds": 60,
                }
            },
        )
    )

    assert result.errors is None
    assert result.data["startChargingSession"]["status"] == "SUCCEEDED"
    assert len(calls) == 1
    service, method, path, kwargs = calls[0]
    assert (service, method, path) == ("saga", "POST", "/sagas/reserve-and-activate")
    assert kwargs["correlation_id"] == correlation_id
    assert kwargs["payload"]["correlation_id"] == correlation_id


def test_start_charging_session_rejects_invalid_amount(monkeypatch):
    async def unexpected_request(*args, **kwargs):
        pytest.fail("invalid input must not call any upstream service")

    monkeypatch.setattr(gateway, "_request_json", unexpected_request)
    result = asyncio.run(
        gateway.schema.execute(
            """
            mutation {
              startChargingSession(input: {
                correlationId: "1d00bc5f-3d09-4de6-8a7a-f2072f9f23e4",
                fleetId: "fleet-1",
                connectorId: "connector-1",
                estimatedAmountCents: 0
              })
            }
            """
        )
    )

    assert result.data is None
    assert result.errors
    assert result.errors[0].extensions["code"] == "BAD_USER_INPUT"


def test_upstream_error_is_exposed_as_graphql_error(monkeypatch):
    async def request_json(*args, **kwargs):
        raise GraphQLError(
            "billing unavailable",
            extensions={"code": "SERVICE_UNAVAILABLE", "service": "billing"},
        )

    monkeypatch.setattr(gateway, "_request_json", request_json)
    result = asyncio.run(
        gateway.schema.execute(
            """
            query {
              stationStatus(connectorId: "connector-1")
            }
            """
        )
    )

    assert result.errors
    assert result.errors[0].extensions["code"] == "SERVICE_UNAVAILABLE"
