import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter

# Initialize OpenTelemetry TracerProvider
_provider = TracerProvider()
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("agenttrace", "0.1.0")

def generate_trace_id() -> str:
    """Generate a 32-character hexadecimal trace ID compatible with OpenTelemetry."""
    return uuid.uuid4().hex

def generate_span_id() -> str:
    """Generate a 16-character hexadecimal span ID compatible with OpenTelemetry."""
    return uuid.uuid4().hex[:16]
