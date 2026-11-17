"""Committed model evidence must cover the corpus and match its recorded provenance."""

import hashlib
import json
from pathlib import Path

from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.evaluation_run import APPROVER, load_cases, verify_manifest
from intake_draft.extraction import RecordedModel, messages_for, note_by_id
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL, OPTIONS

ROOT = Path(__file__).parents[1]


def test_all_forty_captures_match_frozen_inputs_and_published_review_records():
    verify_manifest(ROOT)
    pairs = load_cases(ROOT)
    directory = ROOT / "eval/recordings/qwen3-coder"
    assert {p.stem for p in directory.glob("*.json")} == {s["id"] for s, _ in pairs}
    heldout = json.loads((ROOT / "eval/holdout_report.json").read_text())
    development = json.loads((ROOT / "eval/development_reviews.json").read_text())
    assert heldout["scores"]["case_count"] == 30 and heldout["scores"]["split"] == "holdout"
    rows = {row["id"]: row for row in heldout["case_results"] + development["cases"]}
    hashes = heldout["recording_sha256"] | development["recording_sha256"]
    for sheet, case in pairs:
        path = directory / (sheet["id"] + ".json")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[sheet["id"]]
        record = json.loads(path.read_text())
        assert record["case_id"] == sheet["id"] and record["note_id"] == sheet["note_id"]
        assert record["transcript"] == case["transcript"]
        assert record["model"] == DEFAULT_MODEL and record["model_digest"] == DEFAULT_DIGEST
        assert record["options"] == OPTIONS and record["keep_alive"] == 0
        source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
        assert RecordedModel(record)(messages_for(source, note_by_id(sheet["note_id"])), source.sha256) == record["raw_output"]
        review = rows[sheet["id"]]["review"]
        if review["status"] == "draft":
            assert review["approval_kind"] == "scripted_fixture"
            assert review["approval"]["reviewer"] == APPROVER
            assert review["approval"]["transcript_sha256"] == source.sha256
            assert review["approval"]["confirmed_complete"] is True
        else:
            assert review["approval"] is None and review["approval_kind"] is None
