from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from azure.monitor.opentelemetry.exporter import (
    AzureMonitorTraceExporter,
)
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.sqlalchemy.engine import EngineTracer
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SpanExporter
from opentelemetry.semconv.trace import SpanAttributes
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.conf import OpenTelemetryExporter, Settings


def setup_telemetry(settings: Settings) -> None:  # pragma: no cover
    if settings.opentelemetry_exporter is None:
        return

    resource = Resource(
        attributes={"service.name": "ffc-operations-api"},
    )
    trace_provider = TracerProvider(resource=resource)

    exporter: SpanExporter

    if settings.opentelemetry_exporter == OpenTelemetryExporter.AZURE_APP_INSIGHTS:
        exporter = AzureMonitorTraceExporter(
            connection_string=settings.azure_insights_connection_string,
        )
    elif settings.opentelemetry_exporter == OpenTelemetryExporter.JAEGER:
        exporter = OTLPSpanExporter(endpoint=settings.jaeger_endpoint)  # type: ignore[arg-type]
    elif settings.opentelemetry_exporter == OpenTelemetryExporter.CONSOLE:
        exporter = ConsoleSpanExporter()
    else:
        raise ValueError(f"Unsupported OpenTelemetry exporter: {settings.opentelemetry_exporter}")

    trace_provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(trace_provider)

    HTTPXClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)


def setup_fastapi_instrumentor(settings: Settings, app: FastAPI) -> None:  # pragma: no cover
    """
    Setup FastAPI instrumentation for the application.
    """
    if settings.opentelemetry_exporter is None:
        return

    FastAPIInstrumentor.instrument_app(app)


def setup_sqlalchemy_instrumentor(
    settings: Settings, dbengine: AsyncEngine
) -> None:  # pragma: no cover
    if settings.opentelemetry_exporter is None:
        return

    engine_tracer: EngineTracer | None = SQLAlchemyInstrumentor().instrument(
        engine=dbengine.sync_engine, enable_commenter=True
    )

    if engine_tracer is None:
        return

    def on_begin(conn: Connection) -> None:
        transaction_span_ctx_mngr = engine_tracer.tracer.start_as_current_span(
            "SQLAlchemy Transaction",
            kind=trace.SpanKind.CLIENT,
            attributes={
                SpanAttributes.DB_NAME: dbengine.url.database,
                SpanAttributes.DB_STATEMENT: "BEGIN",
                SpanAttributes.DB_OPERATION: "BEGIN",
            },
        )

        transaction_span_ctx_mngr.__enter__()

        conn.info["otel_transaction_span_ctx_mngr"] = transaction_span_ctx_mngr

    def on_commit(conn: Connection) -> None:
        transaction_span_ctx_mngr = conn.info.pop("otel_transaction_span_ctx_mngr", None)

        if transaction_span_ctx_mngr is not None:
            transaction_span_ctx_mngr.__exit__(None, None, None)

    def on_rollback(conn: Connection) -> None:
        transaction_span_ctx_mngr = conn.info.pop("otel_transaction_span_ctx_mngr", None)

        if transaction_span_ctx_mngr is not None:
            transaction_span_ctx_mngr.__exit__(None, None, None)

    engine_tracer._register_event_listener(dbengine.sync_engine, "begin", on_begin)
    engine_tracer._register_event_listener(dbengine.sync_engine, "commit", on_commit)
    engine_tracer._register_event_listener(dbengine.sync_engine, "rollback", on_rollback)


def capture_telemetry_cli_command[**P, R](
    tracer_name: str, span_name: str
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = trace.get_tracer(tracer_name)

            with tracer.start_as_current_span(
                span_name,
                kind=trace.SpanKind.CLIENT,
                attributes={
                    "az.namespace": "CLI Command",
                },
            ):
                return await func(*args, **kwargs)

        return _wrapper

    return decorator
