"""Live-path wiring with captured output and fake local dependencies, never inference."""

import builtins
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import intake_draft.api as api
import intake_draft.workflow as workflow
from intake_draft.extraction import note_by_id
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL, ModelUnavailable
from intake_draft.references import KeywordIndex, LocalMiniLM
from intake_draft.tracing import NodeTracer, tracer_from_env
from intake_draft.workflow import ReviewConflict, ReviewRequest, ReviewService


@pytest.fixture
def backend(tmp_path):
    record = json.loads((Path(__file__).parents[1] / "src/intake_draft/data/recorded_name_change.json").read_text())
    calls = {"retrieval": [], "model": [], "settings": []}
    class Index:
        def search(self, query, limit):
            calls["retrieval"].append((query, limit))
            return [{"id": "adult_name_change", "score": 0.9, "required_fields": ["untrusted_override"]}]
    class Model:
        last_result = {"model": DEFAULT_MODEL, "model_digest": DEFAULT_DIGEST}
        def __call__(self, messages, sha):
            calls["model"].append((messages, sha))
            return record["raw_output"]
    def model_factory(**settings):
        calls["settings"].append(settings)
        return Model()
    return SimpleNamespace(record=record, calls=calls, model=model_factory, index=Index,
                           path=tmp_path / "live.sqlite")


class FakeClient:
    def __init__(self):
        self.events, self.flushes = [], 0
    def start_observation(self, **kwargs):
        self.events.append(kwargs)
        return SimpleNamespace(update=lambda **data: kwargs.update(data), end=lambda: kwargs.update(ended=True))
    def flush(self):
        self.flushes += 1


def service_for(backend, **kwargs):
    return ReviewService(backend.path, model_factory=backend.model, index_factory=backend.index, **kwargs)


def finish(service, run):
    for row in run["review_queue"]:
        run = service.submit(run["run_id"], ReviewRequest(action="accept", reviewer="Local Test Reviewer",
            expected_revision=run["revision"], field=row["field"], subject=row["subject"]))
    assert run["draft"] is None
    return service.submit(run["run_id"], ReviewRequest(action="approve", reviewer="Local Test Approver",
        expected_revision=run["revision"], confirmed_complete=True))


def test_live_path_preserves_stored_requirements_and_resumes_without_retrieval_or_inference(backend):
    service = service_for(backend)
    run = service.create_live(backend.record["transcript"], "adult name change")
    assert run["mode"] == "local" and run["status"] == "needs_review" and run["draft"] is None
    assert run["note"] == note_by_id("adult_name_change")
    assert run["retrieval"]["candidates"] == [{"id": "adult_name_change", "score": 0.9}]
    assert backend.calls["retrieval"] == [("adult name change", 3)]
    assert backend.calls["settings"][0]["expected_digest"] == DEFAULT_DIGEST
    assert backend.calls["model"][0][1] == run["source"]["sha256"]
    def forbidden(*args, **kwargs):
        pytest.fail("resume must not invoke retrieval or the model again")
    restarted = ReviewService(backend.path, model_factory=forbidden, index_factory=forbidden)
    assert restarted.get(run["run_id"]) == run
    final = finish(restarted, run)
    assert final["model_info"] == run["model_info"] and final["retrieval"] == run["retrieval"]
    birth = next(row for row in final["draft"]["provenance_table"] if row["field"] == "birth_date")
    assert birth["value"] == "1991-06-19" and birth["lines"] == [8]
    assert birth["earlier_assertions"][0]["citations"][0]["line"] == 4


def test_model_unavailability_routes_to_review_without_recorded_fallback(backend, monkeypatch):
    def unavailable(**settings):
        raise ModelUnavailable("private failure detail")
    monkeypatch.setattr(workflow.RecordedModel, "__call__", lambda *args: pytest.fail("no recorded fallback"))
    service = ReviewService(backend.path, model_factory=unavailable, index_factory=backend.index)
    run = service.create_live(backend.record["transcript"], "adult name change")
    assert run["report"]["issues"] == ["model_step_failed"]
    assert run["report"]["missing"] == run["note"]["required_fields"]
    assert run["model_info"] == {"error": "ModelUnavailable"} and run["draft"] is None
    assert all(row["needs_action"] and row["proposed"] is None for row in run["review_queue"])
    with pytest.raises(ReviewConflict):
        finish(service, run)


def test_tracing_keeps_each_node_input_output_and_one_trace_across_review_and_fill(backend):
    client = FakeClient()
    service = service_for(backend, tracer=NodeTracer(client))
    run = finish(service, service.create_live(backend.record["transcript"], "adult name change"))
    assert {event["name"] for event in client.events} == {"retrieve", "extract", "check", "route", "review", "fill"}
    assert all(event["trace_context"]["trace_id"] == run["trace_id"] for event in client.events)
    assert all("input" in event and "output" in event and event["ended"] for event in client.events)
    assert any(event["output"] == {"status": "waiting_for_human"} for event in client.events)
    assert next(e for e in client.events if e["name"] == "extract")["input"]["source"] == run["source"]
    assert next(e for e in client.events if e["name"] == "fill")["output"]["draft"] == run["draft"]
    assert client.flushes > 0


@pytest.mark.parametrize("missing", ["results", "dependency"])
def test_missing_embeddings_raise_without_keyword_fallback_and_trace_the_error(backend, monkeypatch, missing):
    monkeypatch.setattr(KeywordIndex, "search", lambda *args, **kwargs: pytest.fail("no keyword fallback"))
    client = FakeClient()
    def index_factory():
        if missing == "dependency":
            raise ImportError("optional local dependency is absent")
        return SimpleNamespace(search=lambda *args, **kwargs: [])
    service = ReviewService(backend.path, model_factory=backend.model, tracer=NodeTracer(client),
                            index_factory=index_factory)
    with pytest.raises(ModelUnavailable):
        service.create_live(backend.record["transcript"], "adult name change")
    assert backend.calls["model"] == []
    event, = client.events
    assert event["name"] == "retrieve" and event["level"] == "ERROR" and event["ended"]
    assert event["output"] == {"error_type": "ModelUnavailable"}


def test_tracing_off_and_live_http_validation_need_no_trace_client(backend, monkeypatch):
    monkeypatch.setenv("INTAKE_TRACING", "off")
    monkeypatch.setattr("intake_draft.tracing._configured_tracer", lambda *args: pytest.fail("tracing is off"))
    service = service_for(backend, tracer=tracer_from_env())
    monkeypatch.setattr(api, "review_service", lambda: service)
    payload = {"transcript": backend.record["transcript"], "query": "adult name change"}
    with TestClient(api.app) as client:
        response = client.post("/runs", json=payload)
        assert response.status_code == 201 and response.json()["mode"] == "local"
        for invalid in ({"query": " "}, {"query": 42}, {"transcript": " "}, {"transcript": 42}, {"approved": True}):
            assert client.post("/runs", json={**payload, **invalid}).status_code == 422
    assert len(backend.calls["model"]) == 1


def test_bad_embedding_hash_is_rejected_before_optional_dependencies_are_imported(tmp_path, monkeypatch):
    (tmp_path / "model.onnx").write_bytes(b"not the pinned model")
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name in {"onnxruntime", "tokenizers"}:
            pytest.fail("hash verification must precede optional imports")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    with pytest.raises(ValueError, match="pinned revision"):
        LocalMiniLM(tmp_path)


def test_invalid_model_url_credentials_are_not_copied_into_node_observations(backend):
    client = FakeClient()
    service = ReviewService(backend.path, tracer=NodeTracer(client), index_factory=backend.index,
                            model_settings={"base_url": "http://demo:PrivateMarker@127.0.0.1:11434"})
    run = service.create_live(backend.record["transcript"], "adult name change")
    assert run["model_info"] == {"error": "ModelUnavailable"}
    assert "PrivateMarker" not in json.dumps(client.events)


def test_live_http_preserves_the_validation_endpoint_source_hash_and_final_blank(backend, monkeypatch):
    monkeypatch.setattr(api, "review_service", lambda: service_for(backend))
    transcript = "Mara Vale\r\n\r\n"
    with TestClient(api.app) as client:
        source = client.post("/intakes/validate", json={"transcript": transcript}).json()
        response = client.post("/runs", json={"transcript": transcript, "query": "adult name change"})
    assert response.status_code == 201
    assert response.json()["source"] == source
    assert source["lines"][-1] == {"number": 2, "text": ""}


def test_oversized_citation_line_reaches_persisted_review_instead_of_crashing_checkpoint(backend):
    raw = json.loads(backend.record["raw_output"])
    raw["facts"][0]["assertions"][0]["citations"][0]["line"] = 10**80
    class Model:
        def __call__(self, *args):
            return json.dumps(raw)
    service = ReviewService(backend.path, model_factory=lambda **kwargs: Model(), index_factory=backend.index)
    run = service.create_live(backend.record["transcript"], "adult name change")
    assert service.get(run["run_id"]) == run
    assert run["report"]["issues"] == ["malformed_model_output"]
    assert run["report"]["missing"] == run["note"]["required_fields"]
    assert run["draft"] is None
