"""Exercise all authored cases through actual review gates using gold test payloads."""

import json
from pathlib import Path

import pytest

from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.evaluation import tokens
from intake_draft.evaluation_run import APPROVER, REVIEWER, load_cases, scripted_review, verify_manifest
from intake_draft.extraction import PROMPT_VERSION, messages_for, note_by_id, prompt_hash
from intake_draft.workflow import ReviewService

ROOT = Path(__file__).parents[1]
PAIRS = load_cases(ROOT)


def test_corpus_has_frozen_split_and_required_hard_cases():
    assert len(PAIRS) == 40
    assert sum(s["split"] == "dev" for s, _ in PAIRS) == 10
    assert sum(s["split"] == "holdout" for s, _ in PAIRS) == 30
    assert len({s["note_id"] for s, _ in PAIRS}) == 40
    injection = next(c for s, c in PAIRS if s["id"] == "c38")
    assert "999 Fabrication Way" in injection["transcript"]
    assert not any(e["field"] == "petitioner_address" for e in injection["evidence"])
    assert any(len(a["citations"]) > 1 for _, c in PAIRS for e in c["evidence"] for a in e["assertions"])
    assert verify_manifest(ROOT)["model"]["name"] == "qwen3-coder:latest"


@pytest.mark.parametrize("sheet,case", PAIRS, ids=[s["id"] for s, _ in PAIRS])
def test_gold_payloads_use_named_review_and_leave_unresolved_cases_blocked(tmp_path, sheet, case):
    source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
    note = note_by_id(sheet["note_id"])
    record = {"model": "synthetic gold test payload, not a model capture", "note_id": sheet["note_id"],
              "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_hash(messages_for(source, note)),
              "transcript": case["transcript"], "transcript_sha256": source.sha256,
              "raw_output": json.dumps({"facts": case["evidence"]})}
    service = ReviewService(tmp_path / "review.sqlite")
    run = service.create(record)
    assert run["draft"] is None and run["approval"] is None
    final = scripted_review(service, run, sheet, case)
    assert all(event["reviewer"] in {REVIEWER, APPROVER} for event in final["audit"])
    if any(f["status"] != "known" for f in sheet["facts"]):
        assert final["status"] == "needs_review" and final["draft"] is None and final["approval"] is None
        assert any(event["action"] == "reject" for event in final["audit"])
    else:
        assert final["approval"]["reviewer"] == APPROVER
        assert final["status"] == "draft"
        assert sorted(tokens(r["value"]) for r in final["draft"]["provenance_table"]) == sorted(tokens(f["value"]) for f in sheet["facts"])
        assert all(row["lines"] for row in final["draft"]["provenance_table"])


def test_scripted_review_corrects_punctuation_in_requested_name_before_approval(tmp_path):
    sheet, case = next(pair for pair in PAIRS if pair[0]["id"] == "c35")
    expected = next(f["value"] for f in sheet["facts"] if f["field"] == "requested_name")
    facts = json.loads(json.dumps(case["evidence"]))
    requested = next(f for f in facts if f["field"] == "requested_name")
    requested["assertions"][0]["value"] = "Neri Dale Fern"
    source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
    record = {"model": "synthetic punctuation regression, not a model capture", "note_id": sheet["note_id"],
              "prompt_version": PROMPT_VERSION,
              "prompt_sha256": prompt_hash(messages_for(source, note_by_id(sheet["note_id"]))),
              "transcript": case["transcript"], "transcript_sha256": source.sha256,
              "raw_output": json.dumps({"facts": facts})}
    service = ReviewService(tmp_path / "review.sqlite")
    run = service.create(record)
    proposal = next(r for r in run["review_queue"] if r["field"] == "requested_name")["proposed"]
    assert proposal["value"] == "Neri Dale Fern"
    assert proposal["citations"][0]["quote"] == "Neri Dale-Fern"

    final = scripted_review(service, run, sheet, case)
    filled = next(r for r in final["draft"]["provenance_table"] if r["field"] == "requested_name")
    assert filled["value"] == expected == "Neri Dale-Fern"
    assert filled["action"] == "correct" and filled["reviewer"] == REVIEWER
    event, = [e for e in final["audit"] if e["field"] == "requested_name"]
    assert event["action"] == "correct" and event["reviewer"] == REVIEWER
    assert event["before"]["value"] == "Neri Dale Fern"
    assert event["after"]["value"] == expected
    assert final["approval"]["reviewer"] == APPROVER and final["status"] == "draft"
