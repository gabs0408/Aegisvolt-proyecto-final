import os
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from prefect import flow, task

from shared.saga_audit import find_stale_sagas
from shared.observability import configure_logging

SERVICE_NAME = "saga-auditor"
TABLE_NAME = os.getenv("SAGA_TABLE_NAME", "charging-sagas-local")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
DYNAMODB_ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL")
STALE_AFTER_SECONDS = int(os.getenv("SAGA_STALE_AFTER_SECONDS", "600"))
logger = configure_logging(SERVICE_NAME)


def _dynamodb_resource() -> Any:
    options: dict[str, Any] = {"region_name": AWS_REGION}
    if DYNAMODB_ENDPOINT_URL:
        options["endpoint_url"] = DYNAMODB_ENDPOINT_URL
    return boto3.resource("dynamodb", **options)


@task(name="Find stale SAGA transactions", retries=2, retry_delay_seconds=10)
def inspect_saga_table() -> list[dict[str, Any]]:
    if STALE_AFTER_SECONDS <= 0:
        raise ValueError("SAGA_STALE_AFTER_SECONDS must be greater than zero")
    dynamodb = _dynamodb_resource()
    table = dynamodb.Table(TABLE_NAME)
    cutoff = (datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS)).isoformat()
    return find_stale_sagas(table, cutoff)


@task(name="Report SAGA audit findings")
def report_findings(findings: list[dict[str, Any]]) -> None:
    for finding in findings:
        logger.warning(
            "saga_audit_finding",
            extra={
                "correlation_id": finding["correlation_id"],
                "saga_status": finding["status"],
                "step": finding["step"],
                "finding_kind": finding["kind"],
                "age_seconds": finding["age_seconds"],
            },
        )
    logger.info(
        "saga_audit_completed",
        extra={"finding_count": len(findings)},
    )


@flow(name="saga-consistency-audit", log_prints=False)
def audit_saga_consistency() -> list[dict[str, Any]]:
    findings = inspect_saga_table()
    report_findings(findings)
    return findings


if __name__ == "__main__":
    audit_saga_consistency()
