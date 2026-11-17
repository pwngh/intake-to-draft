"""Capture publication and report checking must not corrupt evaluation evidence."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from threading import Barrier
import time

import pytest

from intake_draft.extraction import PROMPT_VERSION, prompt_hash
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL, OPTIONS

ROOT = Path(__file__).parents[1]


@pytest.fixture
def runner(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("evaluation_cli", ROOT / "scripts/evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "RECORDINGS", tmp_path / "eval/recordings/qwen3-coder")
    return module


def fake_model(runner, monkeypatch):
    calls = []
    class Model:
        def __call__(self, messages, sha):
            calls.append(1)
            time.sleep(0.05)
            self.last_result = {"model": DEFAULT_MODEL, "model_digest": DEFAULT_DIGEST,
                "options": OPTIONS, "keep_alive": 0, "prompt_version": PROMPT_VERSION,
                "prompt_sha256": prompt_hash(messages), "transcript_sha256": sha,
                "raw_output": '{"facts":[]}', "usage": {}}
            return self.last_result["raw_output"]
    monkeypatch.setattr(runner, "LocalModel", Model)
    return calls


def test_concurrent_capture_invokes_once_and_replay_never_invokes(runner, monkeypatch):
    calls = fake_model(runner, monkeypatch)
    sheet = {"id": "c31", "split": "dev", "note_id": "adult_name_change"}
    case = {"transcript": "Caller: Invented example."}
    start = Barrier(2)
    def capture():
        start.wait()
        return runner.recording_for(sheet, case, True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: capture(), range(2)))
    assert first == second and len(calls) == 1
    assert runner.recording_for(sheet, case, False) == first
    assert len(calls) == 1


def test_failed_atomic_publication_leaves_no_partial_capture(runner, monkeypatch):
    fake_model(runner, monkeypatch)
    def fail_link(source, destination):
        assert json.loads(source.read_text())["case_id"] == "c31"
        assert not destination.exists()
        raise OSError("synthetic publication failure")
    monkeypatch.setattr(runner.os, "link", fail_link)
    with pytest.raises(OSError, match="publication failure"):
        runner.recording_for({"id": "c31", "split": "dev", "note_id": "adult_name_change"},
                             {"transcript": "Caller: Invented example."}, True)
    assert not (runner.RECORDINGS / "c31.json").exists()
    assert not list((runner.ROOT / ".runtime").glob("tmp*"))


def example_report():
    return {"generated_at": "one", "scores": {"count": 1}, "case_results": [{
        "review": {"approval": {"at": "one", "reviewer": "Scripted Reviewer"}},
        "citation_checks": [{"supported": True, "value": "Invented"}]}]}


def test_report_check_happens_before_write_and_checks_details(runner):
    baseline = runner.ROOT / "eval/holdout_report.json"
    baseline.parent.mkdir()
    original = example_report()
    baseline.write_text(json.dumps(original))
    changed = deepcopy(original)
    changed["case_results"][0]["citation_checks"][0]["value"] = "Different evidence, same count"
    destination = runner.ROOT / ".runtime/report.json"
    with pytest.raises(ValueError, match="replay differs"):
        runner.check_and_write(changed, destination, baseline)
    assert not destination.exists() and json.loads(baseline.read_text()) == original
    with pytest.raises(ValueError, match="ignored .runtime"):
        runner.check_and_write(changed, baseline, baseline)
    assert json.loads(baseline.read_text()) == original
    replay = deepcopy(original)
    replay["generated_at"] = "later"
    replay["case_results"][0]["review"]["approval"]["at"] = "later"
    runner.check_and_write(replay, destination, baseline)
    assert json.loads(destination.read_text()) == replay
