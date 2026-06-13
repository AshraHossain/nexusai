"""
OpenTelemetry Setup for NexusAI
Traces every agent run, LLM call, and integration call.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def setup_telemetry() -> None:
    """Initialize OpenTelemetry with OTLP gRPC exporter."""
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        from app.config import settings

        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": settings.app_version,
                "deployment.environment": "production" if not settings.debug else "development",
            }
        )

        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Auto-instrument FastAPI and httpx
        FastAPIInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()

        logger.info("OpenTelemetry initialized → %s", settings.otel_endpoint)

    except ImportError as exc:
        logger.warning("OpenTelemetry not fully installed: %s — skipping instrumentation", exc)
    except Exception as exc:
        logger.warning("OpenTelemetry setup failed: %s — continuing without tracing", exc)


def get_tracer(name: str = "nexusai"):
    """Get a named tracer (no-op if OTel not initialized)."""
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None
