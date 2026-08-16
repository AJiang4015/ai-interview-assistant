"""OTel 初始化：可选启用，失败静默降级。"""
import os

try:
    from opentelemetry import trace
    tracer = trace.get_tracer(__name__)
except ImportError:
    trace = None
    tracer = None

from app.config import settings  # noqa: E402


def init_tracing(app) -> None:
    if not settings.otel_enabled:
        return
    try:
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXInstrumentor

        provider = TracerProvider()
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=os.getenv("OTLP_ENDPOINT", settings.otel_endpoint)))
        )
        trace.set_tracer_provider(provider)
        if app is not None:
            FastAPIInstrumentor.instrument_app(app)
        HTTPXInstrumentor().instrument()
    except Exception:
        pass  # 无 OTel 端点或依赖缺失时静默降级