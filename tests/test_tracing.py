"""Tracing is optional and cannot change a human-review transition."""

import builtins
import json

import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt

from intake_draft.tracing import NodeTracer, _local_base_url, tracer_from_env
import intake_draft.tracing as tracing


class Observation:
    def __init__(self, fail=None):
        self.fail, self.output, self.ended = fail, None, False

    def update(self, **kwargs):
        if self.fail == "update":
            raise RuntimeError("secret must not be logged")
        self.output = kwargs

    def end(self):
        self.ended = True
        if self.fail == "end":
            raise RuntimeError("secret must not be logged")


class Client:
    def __init__(self, fail=None):
        self.fail, self.started = fail, []
        self.span = Observation(fail)

    def start_observation(self, **kwargs):
        self.started.append(kwargs)
        if self.fail == "start":
            raise RuntimeError("secret must not be logged")
        return self.span

    def flush(self):
        if self.fail == "flush":
            raise RuntimeError("secret must not be logged")


def test_node_input_output_and_run_identity_are_preserved():
    client = Client()
    tracer = NodeTracer(client)
    inputs = {"pending": ["birth_date"]}
    def node():
        inputs["pending"].clear()
        return {"status": "needs_review"}
    result = tracer.call("route", "a" * 32, inputs, node)
    tracer.call("review", "a" * 32, {}, lambda: {"revision": 1})
    assert client.started[0]["input"] == {"pending": ["birth_date"]}
    assert [s["trace_context"]["trace_id"] for s in client.started] == ["a" * 32] * 2
    assert result == {"status": "needs_review"} and client.span.ended
    assert client.span.output["output"] == {"revision": 1}


@pytest.mark.parametrize("failure", ["start", "update", "end", "flush"])
def test_tracing_failures_do_not_repeat_a_node_or_change_its_result(failure, caplog):
    calls = []
    tracer = NodeTracer(Client(failure))
    result = tracer.call("fill", "b" * 32, {}, lambda: calls.append("executed") or {"draft": "example"})
    tracer.flush()
    assert calls == ["executed"] and result == {"draft": "example"}
    assert "secret must not be logged" not in caplog.text
    assert "Local tracing" in caplog.text


@pytest.mark.parametrize("error", [ValueError("application failure"), GraphInterrupt((Interrupt("review"),))])
def test_original_errors_and_human_pause_propagate_even_if_trace_update_fails(error):
    for failure in (None, "update", "end"):
        client, calls = Client(failure), []
        def node():
            calls.append(1)
            raise error
        with pytest.raises(type(error)) as raised:
            NodeTracer(client).call("review", "c" * 32, {}, node)
        assert raised.value is error and calls == [1] and client.span.ended
        if failure != "update":
            expected = "DEFAULT" if isinstance(error, GraphInterrupt) else "ERROR"
            assert client.span.output["level"] == expected
            if isinstance(error, GraphInterrupt):
                assert client.span.output["output"] == {"status": "waiting_for_human"}


def test_off_ignores_cloud_environment_and_does_not_import_langfuse(monkeypatch):
    monkeypatch.setenv("INTAKE_TRACING", "off")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    monkeypatch.setenv("INTAKE_LANGFUSE_CONFIG", "/missing/config.json")
    original = builtins.__import__
    def checked_import(name, *args, **kwargs):
        assert not name.startswith("langfuse")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", checked_import)
    tracer = tracer_from_env()
    assert tracer.call("fill", "d" * 32, {}, lambda: "unchanged") == "unchanged"
    tracer.flush()


@pytest.mark.parametrize("url", ["https://cloud.langfuse.com", "http://example.com", "file:///tmp/a",
    "http://127.0.0.1/path", "http://user:password@127.0.0.1", "http://localhost?token=x", "http://[::1]:0"])
def test_trace_destination_must_be_local_origin(url):
    with pytest.raises(ValueError):
        _local_base_url(url)


def test_enabled_config_uses_explicit_local_values(monkeypatch, tmp_path):
    path = tmp_path / "client.json"
    path.write_text(json.dumps({"base_url": "http://127.0.0.1:13000/", "public_key": "demo-public",
                                "secret_key": "demo-secret", "project_id": "intake-demo"}))
    monkeypatch.setenv("INTAKE_TRACING", "langfuse")
    monkeypatch.setenv("INTAKE_LANGFUSE_CONFIG", str(path))
    monkeypatch.setattr(tracing, "_configured_tracer", lambda *args: args)
    assert tracer_from_env() == ("http://127.0.0.1:13000", "demo-public", "demo-secret")
    path.write_text("not JSON")
    with pytest.raises(ValueError, match="configuration is missing or invalid"):
        tracer_from_env()


def test_sdk_transport_is_local_isolated_and_flush_is_bounded(monkeypatch, caplog):
    import langfuse
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as exporters
    import opentelemetry.sdk.trace as sdk_trace
    import requests

    captured = {}
    monkeypatch.setenv("HTTPS_PROXY", "http://outside.invalid:9999")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://outside.invalid")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    def exporter(**kwargs):
        captured["exporter"] = kwargs
        return object()
    class Provider:
        def __init__(self, **kwargs):
            captured["provider"] = self
        def force_flush(self, **kwargs):
            captured["flush"] = kwargs
            return False
    def client(**kwargs):
        captured["client"] = kwargs
        return Client()
    monkeypatch.setattr(exporters, "OTLPSpanExporter", exporter)
    monkeypatch.setattr(sdk_trace, "TracerProvider", Provider)
    monkeypatch.setattr(langfuse, "Langfuse", client)
    monkeypatch.setattr(requests.Session, "request", lambda self, *args, **kwargs: kwargs)
    tracer = tracing._configured_tracer.__wrapped__("http://127.0.0.1:13000", "demo-public", "demo-secret")
    transport = captured["exporter"]["session"]
    assert transport.trust_env is False
    assert transport.post("http://127.0.0.1", allow_redirects=True)["allow_redirects"] is False
    assert captured["exporter"]["endpoint"] == "http://127.0.0.1:13000/api/public/otel/v1/traces"
    assert captured["client"]["base_url"] == "http://127.0.0.1:13000"
    assert captured["client"]["tracer_provider"] is captured["provider"]
    assert captured["client"]["httpx_client"].follow_redirects is False
    tracer.flush()
    assert captured["flush"] == {"timeout_millis": 2_000}
    assert "incomplete" in caplog.text
    captured["client"]["httpx_client"].close()
    transport.close()


@pytest.mark.parametrize(("variable", "value"), [
    ("LANGFUSE_TRACING_ENABLED", "false"), ("OTEL_SDK_DISABLED", "true"),
])
def test_requested_tracing_rejects_ambient_disable_flags(monkeypatch, variable, value):
    monkeypatch.setenv("INTAKE_TRACING", "langfuse")
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError, match="conflicts"):
        tracer_from_env()
    monkeypatch.setenv("INTAKE_TRACING", "off")
    assert tracer_from_env().client is None


def test_slow_export_flush_has_one_in_flight_worker_and_a_real_wait_bound():
    from threading import Event
    import time

    entered, release = Event(), Event()
    calls = []
    def slow_export():
        calls.append(1)
        entered.set()
        release.wait(5)
        return True
    flush = tracing._BoundedFlush(slow_export, wait_seconds=0.05)
    try:
        started = time.monotonic()
        assert flush() is False and entered.is_set()
        assert flush() is False
        assert time.monotonic() - started < 0.5
        assert calls == [1]
    finally:
        release.set()
    assert flush.pending["done"].wait(1)
    assert flush.pending["result"] is True
