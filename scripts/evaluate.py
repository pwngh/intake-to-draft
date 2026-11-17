"""Replay frozen local captures; --live explicitly captures the selected split once."""

import argparse
from collections import Counter
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
        # Exclusive creation makes resumed captures reuse, never overwrite, prior results.
        with path.open("x") as handle:
            handle.write(json.dumps(record, indent=2) + "\n")
    record = json.loads(path.read_text())
    if (record["case_id"] != sheet["id"] or record["note_id"] != sheet["note_id"]
            or record["transcript"] != case["transcript"] or record["model"] != DEFAULT_MODEL
            or record["model_digest"] != DEFAULT_DIGEST or record["options"] != OPTIONS
            or record.get("keep_alive") != 0):
        raise ValueError(f"capture identity/settings differ: {path.name}")
    RecordedModel(record)(messages, source.sha256)  # Verify prompt/source hashes even when replaying.
    return record, hashlib.sha256(path.read_bytes()).hexdigest()


def stable_result(report):
    """Compare measurements and draft hashes; run IDs and server timestamps intentionally vary."""
    return {"model": report["model"], "manifest_sha256": report["manifest_sha256"],
            "recording_sha256": report["recording_sha256"], "scores": report["scores"],
            "case_results": [{"id": row["id"], "metrics": row["metrics"],
                              "status": row["review"]["status"],
                              "draft_sha256": (row["review"]["approval"] or {}).get("draft_sha256"),
                              "review_actions": row["review"]["actions"]}
                             for row in report["case_results"]]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "holdout"), default="holdout")
    parser.add_argument("--live", action="store_true", help="Capture absent outputs using the pinned local model; never overwrite.")
    parser.add_argument("--check", action="store_true", help="Compare replay to the committed report.")
    parser.add_argument("--output", type=Path, help="Default: ignored .runtime/evaluation/<split>/report.json")
    args = parser.parse_args()
    if args.live and args.check:
        parser.error("capture and committed-report checking are separate operations")
    manifest = verify_manifest(ROOT)
    pairs = [(s, c) for s, c in load_cases(ROOT) if s["split"] == args.split]
    output = args.output or ROOT / ".runtime/evaluation" / args.split / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
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
    output.write_text(json.dumps(report, indent=2) + "\n")
    if args.check:
        expected = json.loads((ROOT / "eval" / (args.split + "_report.json")).read_text())
        if stable_result(report) != stable_result(expected):
            raise ValueError("replay differs from the committed measurements or draft hashes")
    print(f"\n{args.split}: {len(rows)} cases; {DEFAULT_MODEL}")
    for name, metric in report["scores"]["metrics"].items():
        rate = "undefined (zero denominator)" if metric["rate"] is None else f"{100 * metric['rate']:.2f}%"
        print(f"{name}: {metric['numerator']}/{metric['denominator']} = {rate}")
    print("Drafts/reviews:", report["review_outcomes"])
    print("Report:", output)
    print("PASS: frozen captures replayed, model scores computed before scripted review.")


if __name__ == "__main__":
    main()
