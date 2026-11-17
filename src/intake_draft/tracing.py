"""Optional local node observations; tracing cannot repeat or alter a graph action."""

import base64
from contextlib import nullcontext
from copy import deepcopy
from functools import lru_cache
import ipaddress
import json
import logging
import os
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import urlsplit

from langgraph.errors import GraphInterrupt

logger = logging.getLogger(__name__)


class _BoundedFlush:
    """OTEL 1.45's batch processor ignores its timeout; bound our caller's wait."""

    def __init__(self, flush, wait_seconds=2):
        self.flush, self.wait_seconds = flush, wait_seconds
        self.lock, self.pending = Lock(), None

    def __call__(self):
        with self.lock:
            pending = self.pending
            if pending is None or pending["done"].is_set():
                pending = {"done": Event(), "result": False, "error": None}
                def complete():
                    try:
                        pending["result"] = self.flush()
                    except Exception as exc:
                        pending["error"] = exc
                    finally:
                        pending["done"].set()
                self.pending = pending
                Thread(target=complete, daemon=True).start()
        if not pending["done"].wait(self.wait_seconds):
            return False
        if pending["error"] is not None:
            raise pending["error"]
        return pending["result"]


class NodeTracer:
    def __init__(self, client=None, attributes=None, flush=None):
        self.client = client
        self.attributes = attributes or (lambda _run_id: nullcontext())
        self._flush = flush or (client.flush if client is not None else None)

    def _finish(self, span, output, *, level="DEFAULT", status_message=None):
        if span is None:
            return
        try:
            span.update(output=deepcopy(output), level=level, status_message=status_message)
        except Exception:
            logger.warning("Local tracing could not record a node result.")
        finally:
            try:
                span.end()
            except Exception:
                logger.warning("Local tracing could not finish a node observation.")

    def call(self, name, run_id, inputs, fn):
        if self.client is None:
            return fn()
        span = None
        try:
            with self.attributes(run_id):
                span = self.client.start_observation(
                    name=name, as_type="span", trace_context={"trace_id": run_id},
                    input=deepcopy(inputs), metadata={"workflow": "intake-to-draft", "run_id": run_id},
                )
        except Exception:
            logger.warning("Local tracing could not start a node observation.")
        try:
            result = fn()  # Never put the application call inside a tracing retry/fallback.
        except GraphInterrupt:
            self._finish(span, {"status": "waiting_for_human"})
            raise
        except BaseException as exc:
            self._finish(span, {"error_type": type(exc).__name__}, level="ERROR",
                         status_message="Node execution failed; inspect the local workflow error.")
            raise
        self._finish(span, result)
        return result

    def flush(self):
        if self._flush is not None:
            try:
                if self._flush() is False:
                    logger.warning("Local tracing flush is incomplete; observations may be delayed or unavailable.")
            except Exception:
                logger.warning("Local tracing could not flush observations.")


def _local_base_url(value):
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
        valid = (parsed.scheme in {"http", "https"} and loopback and parsed.port != 0
                 and not parsed.username and not parsed.password and not parsed.query
                 and not parsed.fragment and parsed.path in {"", "/"})
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Langfuse base_url must be a loopback HTTP(S) origin")
    return value.rstrip("/")


@lru_cache(maxsize=4)
def _configured_tracer(base_url, public_key, secret_key):
    # Imported only when explicitly enabled. Give the SDK its own provider and transport.
    import httpx
    from langfuse import Langfuse, propagate_attributes
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON
    import requests

    # SDK 5.2 exposes this only through the process environment. This text-only
    # application must preserve data URI strings, never schedule media uploads.
    os.environ["LANGFUSE_MEDIA_UPLOAD_ENABLED"] = "false"

    class LocalSession(requests.Session):
        def request(self, *args, **kwargs):
            kwargs["allow_redirects"] = False
            return super().request(*args, **kwargs)

    session = LocalSession()
    session.trust_env = False
    authorization = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    exporter = OTLPSpanExporter(
        endpoint=base_url + "/api/public/otel/v1/traces", headers={"Authorization": "Basic " + authorization},
        timeout=10, session=session,
    )
    provider = TracerProvider(resource=Resource({"service.name": "intake-to-draft"}), sampler=ALWAYS_ON)
    client = Langfuse(
        base_url=base_url, public_key=public_key, secret_key=secret_key, timeout=2,
        httpx_client=httpx.Client(trust_env=False, follow_redirects=False, timeout=2),
        tracer_provider=provider, span_exporter=exporter, sample_rate=1,
        environment="local-demonstration", release="pr3-local-tracing", flush_interval=1,
    )
    return NodeTracer(client, lambda run_id: propagate_attributes(
        trace_name="Intake to fictional draft", session_id=run_id,
    ), flush=_BoundedFlush(lambda: provider.force_flush(timeout_millis=2_000)))


def tracer_from_env():
    mode = os.environ.get("INTAKE_TRACING", "off").lower()
    if mode == "off":
        return NodeTracer()
    if mode != "langfuse":
        raise ValueError("INTAKE_TRACING must be off or langfuse")
    if (os.environ.get("LANGFUSE_TRACING_ENABLED", "true").lower() == "false"
            or os.environ.get("OTEL_SDK_DISABLED", "false").lower() == "true"):
        raise ValueError("Requested local tracing conflicts with LANGFUSE_TRACING_ENABLED or OTEL_SDK_DISABLED")
    # The pinned exporter merges these headers even with Session.trust_env=False.
    if any(os.environ.get(name) for name in (
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS", "OTEL_EXPORTER_OTLP_HEADERS")):
        raise ValueError("Local tracing requires OTEL_EXPORTER_OTLP_TRACES_HEADERS and OTEL_EXPORTER_OTLP_HEADERS to be unset")
    path = Path(os.environ.get("INTAKE_LANGFUSE_CONFIG", ".runtime/langfuse-client.json"))
    try:
        config = json.loads(path.read_text())
        base_url = _local_base_url(config["base_url"])
        public_key, secret_key = config["public_key"], config["secret_key"]
        if not all(isinstance(key, str) and key.strip() for key in (public_key, secret_key)):
            raise ValueError("missing credentials")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("Local Langfuse configuration is missing or invalid; run scripts/langfuse up") from None
    return _configured_tracer(base_url, public_key, secret_key)
