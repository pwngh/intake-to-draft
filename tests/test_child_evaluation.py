"""The child comparison is dev-only, replayable, and preserves retained evidence."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from intake_draft.child_extraction import CHILD_PROMPT_VERSION, child_messages
from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.extraction import messages_for, note_by_id, prompt_hash
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL, OPTIONS

ROOT = Path(__file__).parents[1]


@pytest.fixture
def runner():
    spec = importlib.util.spec_from_file_location("child_evaluation_cli", ROOT / "scripts/evaluate_children.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record_for(sheet, case, raw):
    source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
    return {"case_id": sheet["id"], "note_id": sheet["note_id"], "transcript": case["transcript"],
            "model": DEFAULT_MODEL, "model_digest": DEFAULT_DIGEST, "options": OPTIONS,
            "keep_alive": 0, "prompt_version": CHILD_PROMPT_VERSION,
            "prompt_sha256": prompt_hash(child_messages(messages_for(source, note_by_id(sheet["note_id"])))),
            "transcript_sha256": source.sha256, "raw_output": raw, "usage": {}}


def test_loader_filters_shared_sheets_before_opening_cases(runner, monkeypatch, tmp_path):
    sheets = []
    for case_id in runner.DEV_IDS:
        note = "divorce_with_children" if case_id in runner.CHILD_IDS else "adult_name_change"
        sheets.append({"id": case_id, "split": "dev", "note_id": note})
        path = tmp_path / "eval/cases" / (case_id + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"id": case_id}))
    # An excluded row has no facts/split/note; inspecting it would fail.
    sheets.append({"id": "c40"})
    directory = tmp_path / "eval/fact_sheets"
    directory.mkdir()
    (directory / "sheets.json").write_text(json.dumps(sheets))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    opened = []
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path.parent.name == "cases":
            assert path.stem in runner.DEV_IDS
            opened.append(path.stem)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    assert len(runner.load_dev_cases()) == 10
    assert opened == list(runner.DEV_IDS)


def test_explicit_capture_is_once_and_keeps_malformed_output(runner, monkeypatch, tmp_path):
    sheet = {"id": "c11", "split": "dev", "note_id": "divorce_with_children"}
    case = {"id": "c11", "transcript": "Caller: Fictional child evidence."}
    calls = []
    class FakeModel:
        def __call__(self, messages, source_sha):
            calls.append((messages, source_sha))
            self.last_result = record_for(sheet, case, "{malformed raw output")
            return self.last_result["raw_output"]
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ChildLocalModel", FakeModel)
    with pytest.raises(ValueError, match="explicit --live"):
        runner.recording_for(sheet, case, child=True)
    first = runner.recording_for(sheet, case, child=True, live=True)
    assert first[0]["raw_output"] == "{malformed raw output"
    assert runner.recording_for(sheet, case, child=True, live=True) == first
    assert runner.recording_for(sheet, case, child=True) == first
    assert len(calls) == 1
    with pytest.raises(ValueError, match="restricted"):
        runner.recording_for({**sheet, "id": "c40"}, case, child=True, live=True)
    assert len(calls) == 1


@pytest.mark.parametrize("field,value", [("model_digest", "wrong"), ("options", {}),
    ("keep_alive", 1), ("prompt_sha256", "wrong"), ("transcript_sha256", "wrong"),
    ("prompt_version", "extract-v2"), ("note_id", "adult_name_change")])
def test_capture_provenance_failure_never_replaces_or_recaptures(runner, monkeypatch, tmp_path, field, value):
    sheet = {"id": "c11", "note_id": "divorce_with_children"}
    case = {"id": "c11", "transcript": "Caller: Fictional child evidence."}
    record = record_for(sheet, case, '{"facts":[]}')
    record[field] = value
    path = tmp_path / "eval/child_extraction/recordings/c11.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(record))
    original = path.read_bytes()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "ChildLocalModel", lambda: pytest.fail("retained output cannot trigger inference"))
    with pytest.raises(ValueError):
        runner.recording_for(sheet, case, child=True, live=True)
    assert path.read_bytes() == original


def test_report_checks_entire_evidence_before_writing(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    report = {"generated_at": "earlier", "before": {"count": 10}, "case_results": [{"report": {"value": "original"}}]}
    committed = tmp_path / "eval/child_extraction/report.json"
    committed.parent.mkdir(parents=True)
    committed.write_text(json.dumps(report))
    changed = deepcopy(report)
    changed["case_results"][0]["report"]["value"] = "changed without changing scores"
    with pytest.raises(ValueError, match="replay differs"):
        runner.check_and_write(changed, check=True)
    assert not (tmp_path / ".runtime/child-extraction/report.json").exists()
    replay = {**report, "generated_at": "later"}
    output = runner.check_and_write(replay, check=True)
    assert json.loads(output.read_text()) == replay
    assert json.loads(committed.read_text()) == report


def test_manifest_requires_frozen_dev_inputs_and_detects_changes(runner, monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    baseline_checks = []
    monkeypatch.setattr(runner, "verify_manifest", lambda root: baseline_checks.append(root))
    files = ["eval/manifest.json", "src/intake_draft/child_extraction.py",
             "scripts/evaluate_children.py", "scripts/evaluate-children", "eval/fact_sheets/dev.json"]
    files += [f"eval/{directory}/{case_id}.json" for directory in ("cases", "recordings/qwen3-coder")
              for case_id in runner.DEV_IDS]
    for relative in files:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("frozen content")
    manifest = {"schema_version": 1, "scope": runner.SCOPE, "dev_case_ids": list(runner.DEV_IDS),
                "child_case_ids": list(runner.CHILD_IDS), "prompt_version": CHILD_PROMPT_VERSION,
                "baseline_manifest_sha256": runner.sha256(tmp_path / "eval/manifest.json"),
                "files": {relative: runner.sha256(tmp_path / relative) for relative in files}}
    path = tmp_path / "eval/child_extraction/manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest))
    assert runner.verify_child_manifest() == runner.sha256(path)
    assert baseline_checks == [tmp_path]
    (tmp_path / "scripts/evaluate_children.py").write_text("changed source")
    with pytest.raises(ValueError, match="frozen child evaluation input changed"):
        runner.verify_child_manifest()
    del manifest["files"]["scripts/evaluate_children.py"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="required files differ"):
        runner.verify_child_manifest()


def test_fixed_comparison_uses_actual_graph_and_unchanged_scores(runner, monkeypatch, tmp_path):
    pairs = runner.load_dev_cases()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "verify_child_manifest", lambda: "test-manifest")
    monkeypatch.setattr(runner, "load_dev_cases", lambda: pairs)
    monkeypatch.setattr(runner, "sha256", lambda path: "test-hash")
    monkeypatch.setattr(runner, "ChildLocalModel", lambda: pytest.fail("offline replay must not infer"))
    calls = []
    def recordings(sheet, case, *, child=False, live=False):
        calls.append((sheet["id"], child, live))
        if child:
            # Authored evidence is only a fake model response for this wiring test.
            return record_for(sheet, case, json.dumps({"facts": case["evidence"]})), "candidate-hash"
        path = ROOT / "eval/recordings/qwen3-coder" / (sheet["id"] + ".json")
        return json.loads(path.read_text()), "baseline-hash"
    monkeypatch.setattr(runner, "recording_for", recordings)
    report = runner.compare()
    assert report["before"]["scores"]["case_ids"] == list(runner.DEV_IDS)
    assert report["after"]["child_field_accuracy"] == {"numerator": 7, "denominator": 7, "rate": 1.0}
    assert report["after"]["correction_history"]["numerator"] == 2
    assert report["after"]["correction_history"]["denominator"] == 2
    assert len(calls) == 15 and sum(child for _, child, _ in calls) == 5
    assert all(not live for _, _, live in calls)
    for row in report["case_results"]:
        assert row["after"]["report"]["status"] == "needs_review"
        assert all(r["needs_action"] for r in row["after"]["review_queue"])
        if row["id"] not in runner.CHILD_IDS:
            assert row["before"] == row["after"]
            assert row["candidate_source"] == "unchanged_baseline_capture"
    original_recordings = recordings
    def corrupted(sheet, case, **kwargs):
        record, digest = original_recordings(sheet, case, **kwargs)
        if kwargs.get("child"):
            record["prompt_sha256"] = "incorrect"
        return record, digest
    monkeypatch.setattr(runner, "recording_for", corrupted)
    with pytest.raises(ValueError, match="without model failures"):
        runner.compare()


def test_correction_history_requires_supported_assertions_in_one_child_group(runner):
    old = {"value": "Ari Wisp born 2010-03-04", "kind": "stated", "citations": [{"line": 1, "quote": "earlier"}]}
    new = {"value": "Ari Wisp born 2010-03-14", "kind": "correction", "citations": [{"line": 3, "quote": "later"}]}
    case = {"id": "synthetic", "evidence": [{"field": "children", "subject": "child-1", "assertions": [old, new]}]}
    def row(subject, assertions):
        return {"field": "children", "subject": subject, "history": [{**a, "evidence_valid": True} for a in assertions]}
    check, = runner.correction_checks(case, {"fields": [row("child-9", [old, new])]})
    assert check["group_preserved"]
    check, = runner.correction_checks(case, {"fields": [row("child-8", [old]), row("child-9", [new])]})
    assert not check["group_preserved"]
    unsupported = row("child-9", [old, new])
    unsupported["history"][0]["evidence_valid"] = False
    check, = runner.correction_checks(case, {"fields": [unsupported]})
    assert [a["preserved"] for a in check["assertions"]] == [False, True]


@pytest.mark.parametrize("arguments", [["--split", "holdout"], ["--case", "c40"], ["--output", "elsewhere"], ["--live", "--check"]])
def test_cli_has_no_case_split_or_path_selector(runner, monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["evaluate_children.py", *arguments])
    monkeypatch.setattr(runner, "compare", lambda *args: pytest.fail("invalid CLI must stop before work"))
    with pytest.raises(SystemExit) as stopped:
        runner.main()
    assert stopped.value.code == 2
