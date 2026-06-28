"""Shared logging and tracing setup for ZavaShop services."""

from __future__ import annotations

import logging
from typing import Final

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_configured: bool = False
_SERVICE_NAMESPACE: Final[str] = "zavashop"


def setup_tracing(*, service_name: str) -> None:
    """Configure structlog and OpenTelemetry once per process."""

    global _configured  # noqa: PLW0603
    if _configured:
        return

    logging.basicConfig(format="%(message)s", level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
    trace.set_tracer_provider(
        TracerProvider(
            resource=Resource.create(
                {
                    "service.name": service_name,
                    "service.namespace": _SERVICE_NAMESPACE,
                }
            )
        )
    )
    _configured = True
