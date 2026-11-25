from datetime import datetime
from typing import Any

from boto3.dynamodb.conditions import Key

PENDING_STATUSES = ("STARTED", "RETRYABLE", "COMPENSATING", "COMPENSATION_PENDING")
COMPENSATION_STATUSES = {"COMPENSATING", "COMPENSATION_PENDING"}


def classify_stale_saga(item: dict[str, Any], cutoff: str) -> dict[str, Any]:
    return {
        "correlation_id": item["correlation_id"],
        "status": item["status"],
        "step": item.get("step", "UNKNOWN"),
        "updated_at": item["updated_at"],
        "kind": (
            "PENDING_COMPENSATION"
            if item["status"] in COMPENSATION_STATUSES
            else "ORPHANED_PENDING_SAGA"
        ),
        "age_seconds": max(
            0,
            int(
                (
                    datetime.fromisoformat(cutoff)
                    - datetime.fromisoformat(item["updated_at"])
                ).total_seconds()
            ),
        ),
    }


def find_stale_sagas(table: Any, cutoff: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for status in PENDING_STATUSES:
        query = {
            "IndexName": "status-updated-at-index",
            "KeyConditionExpression": Key("status").eq(status) & Key("updated_at").lt(cutoff),
        }
        while True:
            response = table.query(**query)
            findings.extend(
                classify_stale_saga(item, cutoff) for item in response.get("Items", [])
            )
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            query["ExclusiveStartKey"] = last_key
    return findings
