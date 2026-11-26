import contextvars
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import Request

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "environment": os.getenv("ENVIRONMENT", "local"),
            "service": os.getenv("SERVICE_NAME", "unknown"),
            "correlation_id": getattr(record, "correlation_id", _correlation_id.get()),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "saga_status",
            "step",
            "finding_kind",
            "age_seconds",
            "finding_count",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(service: str) -> logging.Logger:
    os.environ["SERVICE_NAME"] = service
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    return logging.getLogger(service)


def set_correlation_id(correlation_id: str) -> contextvars.Token[str]:
    return _correlation_id.set(correlation_id)


def reset_correlation_id(token: contextvars.Token[str]) -> None:
    _correlation_id.reset(token)


def log_context_middleware(logger: logging.Logger) -> Callable[..., Any]:
    async def middleware(request: Request, call_next: Callable[..., Any]) -> Any:
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id or len(correlation_id) > 128:
            correlation_id = str(uuid.uuid4())
        token = set_correlation_id(correlation_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            logger.info(
                "http_request_completed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return response
        except Exception:
            logger.exception(
                "http_request_failed",
                extra={"method": request.method, "path": request.url.path},
            )
            raise
        finally:
            reset_correlation_id(token)

    return middleware
