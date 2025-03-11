"""
logging_setup.py

This module initializes OpenTelemetry for distributed tracing and logging.
It exports traces to a configured OpenTelemetry Collector.
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Get OpenTelemetry Collector URL from .env
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

# Set up OpenTelemetry tracing
trace.set_tracer_provider(TracerProvider())
tracer = trace.get_tracer(__name__)

# Configure the exporter to send traces to OpenTelemetry Collector
span_processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_EXPORTER_OTLP_ENDPOINT))
trace.get_tracer_provider().add_span_processor(span_processor)

# Function to retrieve the OpenTelemetry tracer
def get_tracer():
    return tracer