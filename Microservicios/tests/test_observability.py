import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from shared.observability import JsonFormatter, reset_correlation_id, set_correlation_id
from shared.saga_audit import classify_stale_saga


def test_json_log_includes_saga_correlation_environment_and_service(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SERVICE_NAME", "saga-orchestrator-service")
    token = set_correlation_id("corr-123")
    try:
        record = logging.LogRecord(
            "saga-orchestrator-service",
            logging.INFO,
            __file__,
            1,
            "saga_state_saved",
            (),
            None,
        )
        log_entry = json.loads(JsonFormatter().format(record))
    finally:
        reset_correlation_id(token)

    assert log_entry["correlation_id"] == "corr-123"
    assert log_entry["environment"] == "test"
    assert log_entry["service"] == "saga-orchestrator-service"
    assert log_entry["message"] == "saga_state_saved"


def test_saga_auditor_classifies_pending_compensation_and_orphaned_records():
    cutoff = "2026-11-14T05:00:00+00:00"
    compensation = classify_stale_saga(
        {
            "correlation_id": "corr-refund",
            "status": "COMPENSATION_PENDING",
            "step": "REFUNDING",
            "updated_at": "2026-11-14T04:30:00+00:00",
        },
        cutoff,
    )
    orphaned = classify_stale_saga(
        {
            "correlation_id": "corr-stuck",
            "status": "RETRYABLE",
            "step": "DISPATCHING",
            "updated_at": "2026-11-14T04:45:00+00:00",
        },
        cutoff,
    )

    assert compensation["kind"] == "PENDING_COMPENSATION"
    assert compensation["age_seconds"] == 1800
    assert orphaned["kind"] == "ORPHANED_PENDING_SAGA"
    assert orphaned["age_seconds"] == 900
