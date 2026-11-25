import json
import os
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"
PROJECT_NAME = "charging-ci"
BASE_URLS = {
    "reservation": "http://127.0.0.1:8001",
    "billing": "http://127.0.0.1:8002",
    "dispatch": "http://127.0.0.1:8003",
    "saga": "http://127.0.0.1:8004",
    "graphql": "http://127.0.0.1:8005",
}


def _compose(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            PROJECT_NAME,
            "-f",
            str(COMPOSE_FILE),
            *arguments,
        ],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
        timeout=600,
        env=os.environ.copy(),
    )


@pytest.fixture(scope="module", autouse=True)
def compose_stack():
    _compose("up", "--detach")
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            try:
                for base_url in BASE_URLS.values():
                    with urllib.request.urlopen(f"{base_url}/health", timeout=2) as response:
                        if response.status != 200:
                            raise OSError(f"{base_url} is not healthy")
                break
            except OSError:
                time.sleep(2)
        else:
            logs = _compose("logs", "--no-color", check=False).stdout
            pytest.fail(f"Compose stack did not become healthy:\n{logs}")
        yield
    finally:
        _compose("down", "--volumes", "--remove-orphans", check=False)


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def test_graphql_mutation_runs_saga_and_queries_aggregate_services():
    fleet_id = f"integration-{uuid.uuid4().hex}"
    connector_id = f"connector-{uuid.uuid4().hex}"
    correlation_id = str(uuid.uuid4())
    _post_json(f"{BASE_URLS['billing']}/wallets/{fleet_id}", {"currency": "USD"})
    _post_json(
        f"{BASE_URLS['billing']}/wallets/{fleet_id}/funds",
        {"amount_cents": 5000},
    )

    result = _post_json(
        f"{BASE_URLS['graphql']}/graphql",
        {
            "query": """
              mutation Start($input: StartChargingSessionInput!) {
                startChargingSession(input: $input)
              }
            """,
            "variables": {
                "input": {
                    "correlationId": correlation_id,
                    "fleetId": fleet_id,
                    "connectorId": connector_id,
                    "estimatedAmountCents": 1200,
                    "reservationDurationSeconds": 300,
                    "chargingDurationSeconds": 60,
                }
            },
        },
    )
    assert "errors" not in result, result
    saga = result["data"]["startChargingSession"]
    assert saga["status"] == "SUCCEEDED", saga
    assert saga["correlation_id"] == correlation_id

    query = _post_json(
        f"{BASE_URLS['graphql']}/graphql",
        {
            "query": """
              query Status($connectorId: String!, $dispatchId: ID!, $correlationId: UUID!) {
                stationStatus(connectorId: $connectorId)
                chargingSession(dispatchId: $dispatchId)
                sagaStatus(correlationId: $correlationId)
              }
            """,
            "variables": {
                "connectorId": connector_id,
                "dispatchId": saga["dispatch"]["dispatch_id"],
                "correlationId": correlation_id,
            },
        },
    )
    assert "errors" not in query, query
    assert query["data"]["stationStatus"]["status"] == "RESERVED"
    assert query["data"]["chargingSession"]["correlation_id"] == correlation_id
    assert query["data"]["sagaStatus"]["status"] == "SUCCEEDED"
