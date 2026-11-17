"""Exercise durable human decisions; synthetic payloads are not model measurements."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.extraction import PROMPT_VERSION, messages_for, note_by_id, prompt_hash
from intake_draft.workflow import ReviewConflict, ReviewRequest, ReviewService
import intake_draft.workflow as workflow


@pytest.fixture
def service(tmp_path):
    return ReviewService(tmp_path / "reviews.sqlite")


@pytest.fixture
def recording():
    return json.loads((Path(__file__).parents[1] / "src/intake_draft/data/recorded_name_change.json").read_text())


def synthetic_record(note_id="adult_name_change", missing=(), children=()):
    """Build explicit test payloads, not pretend captures from a model."""
    note = note_by_id(note_id)
    lines, facts = [], []
    entries = [(field, "case", field.replace("_", " "), "stated")
               for field in note["required_fields"] if field not in {*missing, "children"}]
    entries += [("children", f"child-{i}", value, kind)
                for i, (value, kind) in enumerate(children, 1)]
    for field, subject, value, kind in entries:
        lines.append(f"Caller: {value}.")
        facts.append({"field": field, "subject": subject, "assertions": [{
            "value": value, "kind": kind, "citations": [{"line": len(lines), "quote": value}]}]})
    source = number_transcript(TranscriptRequest(transcript="\n".join(lines)))
    return {"transcript": source.transcript, "transcript_sha256": source.sha256,
            "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_hash(messages_for(source, note)),
            "note_id": note_id, "raw_output": json.dumps({"facts": facts})}


def decide(service, run, action, field=None, **kwargs):
    payload = {"action": action, "reviewer": "Demo Reviewer", "expected_revision": run["revision"], **kwargs}
    if field is not None:
        payload["field"] = field
    if action == "approve":
        payload.setdefault("confirmed_complete", True)
    return service.submit(run["run_id"], ReviewRequest(**payload))


def accept_all(service, run):
    for row in run["review_queue"]:
        if row["needs_action"] and row["proposed"] is not None:
            run = decide(service, run, "accept", row["field"], subject=row["subject"])
    return run


def test_graph_pauses_until_fields_and_explicit_final_approval(service, recording):
    run = service.create(recording)
    assert run["status"] == "needs_review" and run["draft"] is None and run["revision"] == 0
    assert all(row["needs_action"] for row in run["review_queue"])
    with pytest.raises(ReviewConflict):
        decide(service, run, "approve")
    run = accept_all(service, run)
    assert run["draft"] is None and run["approval"] is None
    birth = next(row for row in run["review_queue"] if row["field"] == "birth_date")
    assert birth["decision"]["selected"]["value"] == "1991-06-19"
    assert [a["value"] for a in birth["history"]] == ["1991-06-18", "1991-06-19"]
    run = decide(service, run, "approve", reviewer="Final Reviewer")
    assert run["status"] == "draft" and run["approval"]["reviewer"] == "Final Reviewer"
    assert run["approval"]["draft_sha256"] == hashlib.sha256(run["draft"]["text"].encode()).hexdigest()
    assert run["report"]["approved"] is False  # Extraction never becomes a human decision.
    rows = {row["field"]: row for row in run["draft"]["provenance_table"]}
    assert rows["birth_date"]["lines"] == [8]
    assert rows["birth_date"]["earlier_assertions"][0]["value"] == "1991-06-18"
    assert rows["petitioner_address"]["lines"] == [5, 6]
    assert "Fictional Demonstration Jurisdiction" in run["draft"]["text"]


def test_reject_then_correct_preserves_audited_identity_time_and_before_after(service, recording):
    run = accept_all(service, service.create(recording))
    run = decide(service, run, "reject", "petitioner_address", reviewer="First Reviewer", reason="Check punctuation")
    assert run["audit"][-1]["before"]["value"] == "18 Example Lane, Sampletown"
    assert run["audit"][-1]["after"] is None
    with pytest.raises(ReviewConflict):
        decide(service, run, "approve")
    run = decide(service, run, "correct", "petitioner_address", reviewer="Second Reviewer", reason="Use joined source fragments",
                 value="18 Example Lane Sampletown", citations=[{"line": 5, "quote": "18 Example Lane"},
                                                               {"line": 6, "quote": "Sampletown"}])
    event = run["audit"][-1]
    assert event["before"] is None and event["after"]["value"] == "18 Example Lane Sampletown"
    assert event["reviewer"] == "Second Reviewer" and event["reason"] == "Use joined source fragments"
    assert datetime.fromisoformat(event["at"]).utcoffset().total_seconds() == 0
    assert run["audit"][-2]["reviewer"] == "First Reviewer"
    assert decide(service, run, "approve")["draft"] is not None


@pytest.mark.parametrize("citations", [[], [{"line": 99, "quote": "Mara Vale"}],
    [{"line": 2, "quote": "Fabricated"}], [{"line": 2, "quote": "Vale"}, {"line": 2, "quote": "Mara"}]])
def test_invalid_correction_does_not_consume_the_interrupt_or_create_an_audit_event(service, recording, citations):
    run = service.create(recording)
    with pytest.raises(ValueError):
        decide(service, run, "correct", "petitioner_name", value="Mara Vale", citations=citations, reason="Verify source")
    assert service.get(run["run_id"]) == run
    assert decide(service, run, "accept", "petitioner_name")["revision"] == 1


def test_accept_cannot_supply_its_own_value_or_bypass_missing_evidence(service):
    run = service.create(synthetic_record(missing=("petitioner_address",)))
    row = next(row for row in run["review_queue"] if row["field"] == "petitioner_address")
    assert row["proposed"] is None and "missing_fact" in row["issues"]
    with pytest.raises(ReviewConflict):
        decide(service, run, "accept", "petitioner_address")
    with pytest.raises(ValueError):
        decide(service, run, "accept", "petitioner_name", value="Invented person")
    with pytest.raises(ValueError):
        decide(service, run, "correct", "petitioner_address", value="9 Guessed Road",
               citations=[{"line": 1, "quote": "9 Guessed Road"}], reason="Not in intake")
    run = accept_all(service, run)
    with pytest.raises(ReviewConflict):
        decide(service, run, "approve")
    assert run["draft"] is None


def test_malformed_model_output_routes_every_requirement_to_review(service, recording):
    recording["raw_output"] = "not JSON"
    run = service.create(recording)
    assert run["report"]["issues"] == ["malformed_model_output"]
    assert len(run["review_queue"]) == len(run["note"]["required_fields"])
    assert all(row["needs_action"] and row["proposed"] is None for row in run["review_queue"])
    with pytest.raises(ReviewConflict):
        decide(service, run, "approve")
    assert run["audit"] == [] and run["draft"] is None


def test_unresolved_sibling_blocks_approval_and_reviewer_can_add_an_omitted_child(service):
    record = synthetic_record("divorce_with_children", children=(("Ada Vale", "stated"), ("Ava Vale", "uncertain")))
    run = accept_all(service, service.create(record))
    with pytest.raises(ReviewConflict):
        decide(service, run, "approve")
    line = len(run["source"]["lines"])
    run = decide(service, run, "correct", "children", subject="child-2", value="Ava Vale",
                 citations=[{"line": line, "quote": "Ava Vale"}], reason="Human verified against full source")
    assert len([row for row in decide(service, run, "approve")["draft"]["provenance_table"]
                if row["field"] == "children"]) == 2
    # The source still names both children, but this second synthetic output omits Ava.
    output = json.loads(record["raw_output"])
    output["facts"] = [f for f in output["facts"] if f["subject"] != "child-2"]
    record["raw_output"] = json.dumps(output)
    run = accept_all(service, service.create(record))
    run = decide(service, run, "correct", "children", subject="child-2", value="Ava Vale",
                 citations=[{"line": line, "quote": "Ava Vale"}], reason="Add child omitted by model")
    assert run["audit"][-1]["before"] is None
    assert len([row for row in decide(service, run, "approve")["draft"]["provenance_table"]
                if row["field"] == "children"]) == 2


def test_restart_preserves_audit_and_resumes_without_extracting_again(service, recording, monkeypatch):
    run = decide(service, service.create(recording), "accept", "petitioner_name")
    restarted = ReviewService(service.path)
    assert restarted.get(run["run_id"]) == run
    monkeypatch.setattr(workflow.RecordedModel, "__call__", lambda *args: pytest.fail("must not re-extract on resume"))
    assert decide(restarted, run, "accept", "birth_date")["revision"] == 2


def test_stale_requests_and_completed_runs_cannot_change_the_log(service, recording):
    old = service.create(recording)
    current = decide(service, old, "accept", "petitioner_name")
    with pytest.raises(ReviewConflict):
        decide(service, old, "reject", "petitioner_name", reason="Stale decision")
    assert service.get(old["run_id"]) == current
    final = decide(service, accept_all(service, current), "approve")
    with pytest.raises(ReviewConflict):
        decide(service, final, "reject", "petitioner_name", reason="Already sealed")
    assert service.get(final["run_id"]) == final


def test_same_source_and_decisions_produce_identical_draft_bytes(service, recording):
    drafts = [decide(service, accept_all(service, service.create(recording)), "approve") for _ in range(2)]
    assert drafts[0]["run_id"] != drafts[1]["run_id"]
    assert drafts[0]["draft"]["text"].encode() == drafts[1]["draft"]["text"].encode()
    assert drafts[0]["approval"]["draft_sha256"] == drafts[1]["approval"]["draft_sha256"]


def test_two_service_instances_cannot_accept_the_same_revision(service, recording):
    run = service.create(recording)
    def submit(_):
        try:
            return decide(ReviewService(service.path), run, "accept", "petitioner_name")
        except ReviewConflict:
            return None
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, range(2)))
    assert sum(result is not None for result in results) == 1
    stored = service.get(run["run_id"])
    assert stored["revision"] == 1 and len(stored["audit"]) == 1


def test_failure_after_approval_checkpoint_recovers_without_duplicate_audit(service, recording, monkeypatch):
    run = accept_all(service, service.create(recording))
    render = workflow.render_draft
    calls = 0
    def fail_on_fill(*args):
        nonlocal calls
        calls += 1
        if calls == 3:  # submit validation, review node validation, then fill
            raise RuntimeError("simulated fill interruption")
        return render(*args)
    monkeypatch.setattr(workflow, "render_draft", fail_on_fill)
    with pytest.raises(RuntimeError, match="simulated fill interruption"):
        decide(service, run, "approve")
    monkeypatch.setattr(workflow, "render_draft", render)
    recovered = ReviewService(service.path).get(run["run_id"])
    assert recovered["status"] == "draft"
    assert [event["action"] for event in recovered["audit"]].count("approve") == 1
    assert recovered["revision"] == run["revision"] + 1
    assert service.get(run["run_id"]) == recovered


@pytest.mark.parametrize(("action", "stage"), [
    ("accept", "review"), ("approve", "review"), ("approve", "route"), ("approve", "fill"),
])
def test_killed_worker_pending_writes_recover_before_the_next_decision(service, recording, action, stage):
    run = service.create(recording)
    if action == "approve":
        run = accept_all(service, run)
    request = {"action": action, "reviewer": "Interrupted Reviewer", "expected_revision": run["revision"]}
    request.update({"confirmed_complete": True} if action == "approve" else {"field": "birth_date"})
    # Kill a separate worker AFTER SQLite commits node writes but BEFORE the next checkpoint.
    worker = '''
import json, os, signal, sys
from intake_draft.workflow import ReviewRequest, ReviewService, SqliteSaver
original = SqliteSaver.put_writes
def put_writes(self, config, writes, task_id, task_path=""):
    result = original(self, config, writes, task_id, task_path)
    channels = {channel for channel, _ in writes}
    required = {"review": {"revision", "audit", "branch:to:route"},
                "route": {"status", "branch:to:fill"}, "fill": {"draft", "status"}}[sys.argv[3]]
    if required <= channels:
        os.kill(os.getpid(), signal.SIGKILL)
    return result
SqliteSaver.put_writes = put_writes
ReviewService(sys.argv[1]).submit(sys.argv[2], ReviewRequest.model_validate_json(sys.argv[4]))
'''
    child = subprocess.run([sys.executable, "-c", worker, str(service.path), run["run_id"], stage,
                            json.dumps(request)], capture_output=True, text=True, timeout=30)
    assert child.returncode == -signal.SIGKILL, child.stderr
    reopened = ReviewService(service.path)
    recovered = reopened.get(run["run_id"])
    assert recovered["revision"] == run["revision"] + 1
    assert len(recovered["audit"]) == len(run["audit"]) + 1
    assert reopened.get(run["run_id"]) == recovered
    if action == "approve":
        assert recovered["status"] == "draft" and recovered["draft"] is not None
        assert sum(e["action"] == "approve" for e in recovered["audit"]) == 1
    else:
        following = decide(reopened, recovered, "accept", "requested_name")
        assert following["revision"] == recovered["revision"] + 1
        assert following["audit"][-1]["field"] == "requested_name"
