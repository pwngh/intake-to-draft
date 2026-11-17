"""Versioned prompting and real API routing, using only development fixtures."""

from copy import deepcopy
import json
from pathlib import Path

from fastapi.testclient import TestClient
import httpx
import pytest

from intake_draft import api, workflow
from intake_draft.child_extraction import (
    CHILD_PROMPT_VERSION, ChildLocalModel, RecordedChildModel, child_messages,
)
from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.extraction import messages_for, note_by_id, prompt_hash
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL

ROOT = Path(__file__).parents[1]


def fixture(case_id):
    record = json.loads((ROOT / f"eval/recordings/qwen3-coder/{case_id}.json").read_text())
    source = number_transcript(TranscriptRequest(transcript=record["transcript"]))
    return record, source, messages_for(source, note_by_id(record["note_id"]))


def transport_for(raw, requests):
    def handle(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": DEFAULT_MODEL, "digest": DEFAULT_DIGEST}]})
        return httpx.Response(200, json={"model": DEFAULT_MODEL, "done": True, "done_reason": "stop",
                                        "message": {"role": "assistant", "content": raw}})
    return httpx.MockTransport(handle)


def test_nonchild_request_and_recording_remain_exactly_v2():
    record, source, messages = fixture("c31")
    requests = []
    model = ChildLocalModel(transport=transport_for(record["raw_output"], requests))
    assert model(messages, source.sha256) == record["raw_output"]
    assert json.loads(requests[-1].content)["messages"] == messages
    assert model.last_result["prompt_version"] == record["prompt_version"] == "extract-v2"
    assert model.last_result["prompt_sha256"] == record["prompt_sha256"]
    assert RecordedChildModel(record)(messages, source.sha256) == record["raw_output"]


def test_child_request_binds_actual_prompt_without_mutating_evidence_or_repairing_output():
    _, source, messages = fixture("c13")
    original, requests = deepcopy(messages), []
    raw = '{"facts":'  # Deliberately malformed test payload, not measured model output.
    model = ChildLocalModel(transport=transport_for(raw, requests))
    assert model(messages, source.sha256) == raw
    body = json.loads(requests[-1].content)
    assert messages == original and body["messages"][1:] == original[1:]
    assert body["messages"][0]["content"].startswith(original[0]["content"])
    assert model.last_result["prompt_version"] == CHILD_PROMPT_VERSION
    assert model.last_result["prompt_sha256"] == prompt_hash(body["messages"]) != prompt_hash(messages)
    assert model.last_result["transcript_sha256"] == source.sha256
    assert RecordedChildModel(model.last_result)(messages, source.sha256) == raw


@pytest.mark.parametrize("change", ["prompt_version", "prompt_sha256", "transcript_sha256"])
def test_child_replay_refuses_a_different_prompt_or_source(change):
    record, source, messages = fixture("c13")
    record |= {"prompt_version": CHILD_PROMPT_VERSION, "prompt_sha256": prompt_hash(child_messages(messages))}
    replay = RecordedChildModel(record)
    replay(messages, source.sha256)
    replay.record[change] = "wrong"
    with pytest.raises(ValueError, match="does not match"):
        replay(messages, source.sha256)
    assert replay.last_result == {}


def test_api_uses_child_prompt_and_preserves_correction_history_before_review(tmp_path, monkeypatch):
    record, _, _ = fixture("c13")
    case = json.loads((ROOT / "eval/cases/c13.json").read_text())
    # Authored gold is a synthetic transport fixture, not an inference measurement.
    raw, requests = json.dumps({"facts": case["evidence"]}), []
    monkeypatch.setenv("INTAKE_REVIEW_DB", str(tmp_path / "review.sqlite"))
    monkeypatch.setenv("INTAKE_TRACING", "off")
    monkeypatch.setattr(api, "ChildLocalModel", lambda **kwargs: ChildLocalModel(
        transport=transport_for(raw, requests), **kwargs))
    class Index:
        def search(self, query, limit):
            return [{"id": record["note_id"], "score": 1.0}]
    monkeypatch.setattr(workflow, "live_index", lambda path: Index())
    with TestClient(api.app) as client:
        response = client.post("/runs", json={"transcript": case["transcript"], "query": "development custody facts"})
        assert response.status_code == 201
        run = response.json()
        assert run["model_info"]["prompt_version"] == CHILD_PROMPT_VERSION
        children = [row for row in run["review_queue"] if row["field"] == "children"]
        assert len(children) == 2 and all(row["needs_action"] for row in children)
        corrected = next(row for row in children if row["subject"] == "child-1")
        assert corrected["proposed"]["value"] == "Leva Vale born 2012-09-12"
        assert [a["value"] for a in corrected["history"]] == [
            "Leva Vale born 2012-09-21", "Leva Vale born 2012-09-12"]
        assert client.get(f"/runs/{run['run_id']}/draft").status_code == 409
        assert run["approval"] is None and run["audit"] == []
        assert len(requests) == 2
