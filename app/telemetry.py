from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any

from azure.monitor.opentelemetry.exporter import (
    AzureMonitorTraceExporter,
)
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.ext.asyncio import AsyncEngine

from app.conf import Settings


def setup_telemetry(settings: Settings) -> None:
    if not settings.azure_insights_connection_string:
        return

    exporter = AzureMonitorTraceExporter(
        connection_string=settings.azure_insights_connection_string,
    )

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(trace_provider)

    HTTPXClientInstrumentor().instrument()
    LoggingInstrumentor().instrument(set_logging_format=True)


def setup_fastapi_instrumentor(settings: Settings, app: FastAPI) -> None:
    """
    Setup FastAPI instrumentation for the application.
    """
    if not settings.azure_insights_connection_string:
        return

    FastAPIInstrumentor.instrument_app(app)


def setup_sqlalchemy_instrumentor(settings: Settings, dbengine: AsyncEngine) -> None:
    if not settings.azure_insights_connection_string:
        return

    SQLAlchemyInstrumentor().instrument(engine=dbengine.sync_engine, enable_commenter=True)


def capture_telemetry[**P, R](
    tracer_name: str, span_name: str
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
    def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
        @wraps(func)
        async def _wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            tracer = trace.get_tracer(tracer_name)

            with tracer.start_as_current_span(span_name, kind=trace.SpanKind.CLIENT):
                return await func(*args, **kwargs)

        return _wrapper

    return decorator
