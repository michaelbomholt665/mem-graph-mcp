import os
import sys
import pathlib
from dotenv import load_dotenv

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

load_dotenv()

# Setup OpenTelemetry BEFORE importing FastMCP


provider = TracerProvider()
# Fallback Console Exporter for debugging and inline trace viewing
provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr)))

# Optionally add OTLP Exporter if configured natively
otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
if otlp_endpoint:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
        )
    except ImportError:
        pass

trace.set_tracer_provider(provider)

# Allow imports from 'src'
sys.path.insert(0, str(pathlib.Path(__file__).parent / "src"))

from mem_graph.server import run  # noqa: E402

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nServer shut down gracefully.", flush=True)
