"""Replay frozen local captures; --live explicitly captures the selected split once."""

import argparse
from collections import Counter
from copy import deepcopy
import fcntl
import os
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile

from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.evaluation import aggregate, score_case
from intake_draft.evaluation_run import load_cases, review_summary, scripted_review, verify_manifest
from intake_draft.extraction import PROMPT_VERSION, RecordedModel, messages_for, note_by_id, prompt_hash
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL, LocalModel, OPTIONS
from intake_draft.workflow import ReviewService

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / "eval/recordings/qwen3-coder"


def recording_for(sheet, case, live):
    directory = ROOT / ".runtime"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "evaluation-capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _recording_for(sheet, case, live)


def _recording_for(sheet, case, live):
    source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
    messages = messages_for(source, note_by_id(sheet["note_id"]))
    path = RECORDINGS / (sheet["id"] + ".json")
    if not path.exists():
        if not live:
            raise ValueError(f"missing capture {path.name}; use --live explicitly with the pinned local model")
        print(f"Capturing {sheet['id']} ({sheet['split']}) with {DEFAULT_MODEL}", flush=True)
        model = LocalModel()
        model(messages, source.sha256)  # Any transport/envelope failure stops; no substitute or repair.
        record = {"case_id": sheet["id"], "captured_at": datetime.now(timezone.utc).isoformat(),
                  "transcript": case["transcript"], "note_id": sheet["note_id"], **model.last_result}
        path.parent.mkdir(parents=True, exist_ok=True)
        # Publish a fully written file atomically. A link fails if a capture exists.
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=ROOT / ".runtime", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(json.dumps(record, indent=2) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    record = json.loads(path.read_text())
    if (record["case_id"] != sheet["id"] or record["note_id"] != sheet["note_id"]
            or record["transcript"] != case["transcript"] or record["model"] != DEFAULT_MODEL
            or record["model_digest"] != DEFAULT_DIGEST or record["options"] != OPTIONS
            or record.get("keep_alive") != 0):
        raise ValueError(f"capture identity/settings differ: {path.name}")
    RecordedModel(record)(messages, source.sha256)  # Verify prompt/source hashes even when replaying.
    return record, hashlib.sha256(path.read_bytes()).hexdigest()


def stable_result(report):
    """Compare all measurements and evidence, excluding server-assigned timestamps."""
    stable = deepcopy(report)
    stable.pop("generated_at", None)
    for row in stable["case_results"]:
        if row["review"]["approval"] is not None:
            row["review"]["approval"].pop("at", None)
    return stable


def check_and_write(report, output, expected_path=None):
    # Runtime reports must never replace the gold baseline, captures, or other source files.
    if not output.resolve().is_relative_to((ROOT / ".runtime").resolve()):
        raise ValueError("evaluation output must stay inside this checkout's ignored .runtime directory")
    if expected_path is not None:
        expected = json.loads(expected_path.read_text())
        if stable_result(report) != stable_result(expected):
            raise ValueError("replay differs from the committed measurements, evidence, or draft hashes")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout"), default="holdout")
    parser.add_argument("--live", action="store_true", help="Capture absent outputs using the pinned local model; never overwrite.")
    parser.add_argument("--check", action="store_true", help="Compare replay to the committed report.")
    parser.add_argument("--output", type=Path, help="Default: ignored .runtime/evaluation/<split>/report.json")
    args = parser.parse_args()
    if args.check and args.split != "holdout":
        parser.error("only the holdout has a published benchmark report; development is diagnostic")
    if args.live and args.check:
        parser.error("capture and committed-report checking are separate operations")
    manifest = verify_manifest(ROOT)
    pairs = [(s, c) for s, c in load_cases(ROOT) if s["split"] == args.split]
    output = args.output or ROOT / ".runtime/evaluation" / args.split / "report.json"
    if not output.resolve().is_relative_to((ROOT / ".runtime").resolve()):
        parser.error("--output must stay inside this checkout's ignored .runtime directory")
    artifacts = ROOT / ".runtime/evaluation" / args.split / "runs"
    artifacts.mkdir(parents=True, exist_ok=True)
    rows, hashes = [], {}
    with tempfile.TemporaryDirectory(prefix="intake-evaluation-") as directory:
        service = ReviewService(Path(directory) / "reviews.sqlite")  # Tracing off; no Docker required.
        for sheet, case in pairs:
            record, digest = recording_for(sheet, case, args.live)
            run = service.create(record)
            row = score_case(sheet, case, record["raw_output"], run)  # Score BEFORE gold-assisted review.
            run = scripted_review(service, run, sheet, case)
            row["review"] = review_summary(run)
            rows.append(row)
            hashes[sheet["id"]] = digest
            (artifacts / (sheet["id"] + ".json")).write_text(json.dumps(run, indent=2) + "\n")
            print(f"{sheet['id']}: {run['status']}; {len(run['audit'])} scripted decisions", flush=True)
    report = {"model": {"name": DEFAULT_MODEL, "digest": DEFAULT_DIGEST, "options": OPTIONS},
              "generated_at": datetime.now(timezone.utc).isoformat(), "requirement_source": "specified fictional note; retrieval evaluated separately",
              "manifest_sha256": hashlib.sha256((ROOT / "eval/manifest.json").read_bytes()).hexdigest(),
              "recording_sha256": hashes, "scores": aggregate(rows), "case_results": rows,
              "review_outcomes": dict(Counter(row["review"]["status"] for row in rows)),
              "approval_kind": "Scripted fact-sheet review, not a claim of human inspection; model scores precede corrections."}
    check_and_write(report, output, ROOT / "eval" / (args.split + "_report.json") if args.check else None)
    print(f"\n{args.split}: {len(rows)} cases; {DEFAULT_MODEL}")
    for name, metric in report["scores"]["metrics"].items():
        rate = "undefined (zero denominator)" if metric["rate"] is None else f"{100 * metric['rate']:.2f}%"
        print(f"{name}: {metric['numerator']}/{metric['denominator']} = {rate}")
    print("Drafts/reviews:", report["review_outcomes"])
    print("Report:", output)
    print("PASS: frozen captures replayed, model scores computed before scripted review.")


if __name__ == "__main__":
    main()
