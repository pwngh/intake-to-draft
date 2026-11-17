"""Compare the fixed ten development cases; --live captures five child cases once."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace

from intake_draft.child_extraction import CHILD_PROMPT_VERSION, ChildLocalModel, RecordedChildModel
from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.evaluation import aggregate, score_case, tokens
from intake_draft.evaluation_run import verify_manifest
from intake_draft.extraction import RecordedModel, messages_for, note_by_id
from intake_draft.local_model import DEFAULT_DIGEST, DEFAULT_MODEL, OPTIONS
from intake_draft.workflow import ReviewService

ROOT = Path(__file__).resolve().parent.parent
DEV_IDS = ("c01", "c02", "c03", "c11", "c12", "c13", "c21", "c22", "c31", "c32")
CHILD_IDS = ("c11", "c12", "c13", "c21", "c22")
SCOPE = "development-only child extraction"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_dev_cases():
    # Shared sheets may be parsed, but filter before examining facts or opening cases.
    sheets = [sheet for path in sorted((ROOT / "eval/fact_sheets").glob("*.json"))
              for sheet in json.loads(path.read_text()) if sheet["id"] in DEV_IDS]
    if len(sheets) != len(DEV_IDS) or {sheet["id"] for sheet in sheets} != set(DEV_IDS):
        raise ValueError("the fixed ten development fact sheets are required")
    pairs = []
    for sheet in sorted(sheets, key=lambda item: item["id"]):
        if sheet["split"] != "dev":
            raise ValueError("development split mismatch")
        case = json.loads((ROOT / "eval/cases" / (sheet["id"] + ".json")).read_text())
        if case["id"] != sheet["id"] or ((sheet["id"] in CHILD_IDS)
                != ("children" in note_by_id(sheet["note_id"])["required_fields"])):
            raise ValueError("development case identity or child requirement mismatch")
        pairs.append((sheet, case))
    return pairs


def verify_child_manifest():
    verify_manifest(ROOT)  # Existing corpus is hashed only, never loaded or rescored here.
    path = ROOT / "eval/child_extraction/manifest.json"
    manifest = json.loads(path.read_text())
    required = {"src/intake_draft/child_extraction.py", "scripts/evaluate_children.py", "scripts/evaluate-children"}
    required.update(f"eval/{directory}/{case_id}.json" for directory in ("cases", "recordings/qwen3-coder")
                    for case_id in DEV_IDS)
    required.update(str(p.relative_to(ROOT)) for p in (ROOT / "eval/fact_sheets").glob("*.json"))
    if (manifest.get("schema_version") != 1 or manifest.get("scope") != SCOPE
            or manifest.get("dev_case_ids") != list(DEV_IDS) or manifest.get("child_case_ids") != list(CHILD_IDS)
            or manifest.get("prompt_version") != CHILD_PROMPT_VERSION
            or manifest.get("baseline_manifest_sha256") != sha256(ROOT / "eval/manifest.json")
            or not required <= manifest.get("files", {}).keys()):
        raise ValueError("child manifest identity or required files differ")
    for relative, expected in manifest["files"].items():
        if not (ROOT / relative).resolve().is_relative_to(ROOT.resolve()) or sha256(ROOT / relative) != expected:
            raise ValueError(f"frozen child evaluation input changed: {relative}")
    return sha256(path)


def recording_for(sheet, case, *, child=False, live=False):
    case_id = sheet["id"]
    if case_id not in DEV_IDS or (child and case_id not in CHILD_IDS) or (live and not child):
        raise ValueError("capture/replay is restricted to the fixed development cases")
    runtime = ROOT / ".runtime/child-extraction"
    runtime.mkdir(parents=True, exist_ok=True)
    path = ROOT / ("eval/child_extraction/recordings" if child else "eval/recordings/qwen3-coder") / (case_id + ".json")
    source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
    messages = messages_for(source, note_by_id(sheet["note_id"]))
    with (runtime / "capture.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not path.exists():
            if not live:
                raise ValueError(f"missing capture {case_id}; only explicit --live captures child development cases")
            print(f"Capturing {case_id} once with {DEFAULT_MODEL}", flush=True)
            model = ChildLocalModel()
            model(messages, source.sha256)
            record = {"case_id": case_id, "captured_at": datetime.now(timezone.utc).isoformat(),
                      "transcript": case["transcript"], "note_id": sheet["note_id"], **model.last_result}
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", dir=runtime, delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(json.dumps(record, indent=2) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, path)  # Atomic publication; never replace retained raw output.
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        record = json.loads(path.read_text())
        if (record["case_id"] != case_id or record["note_id"] != sheet["note_id"]
                or record["transcript"] != case["transcript"] or record["model"] != DEFAULT_MODEL
                or record["model_digest"] != DEFAULT_DIGEST or record["options"] != OPTIONS
                or record.get("keep_alive") != 0):
            raise ValueError(f"capture identity/settings differ: {case_id}")
        (RecordedChildModel if child else RecordedModel)(record)(messages, source.sha256)
        return record, sha256(path)


def metric(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def correction_checks(case, report):
    def key(assertion):
        return (tokens(assertion["value"]), assertion["kind"],
                tuple(citation["line"] for citation in assertion["citations"]))
    emitted = [row for row in report["fields"] if row["field"] == "children"]
    checks = []
    for fact in case["evidence"]:
        if fact["field"] != "children" or not any(a["kind"] == "correction" for a in fact["assertions"]):
            continue
        expected = Counter(key(a) for a in fact["assertions"])
        supported = lambda row: Counter(key(a) for a in row["history"] if a["evidence_valid"])
        match = max(emitted, key=lambda row: sum((supported(row) & expected).values()), default=None)
        available = supported(match) if match else Counter()
        assertions = []
        for assertion in fact["assertions"]:
            preserved = available[key(assertion)] > 0
            available[key(assertion)] -= int(preserved)
            assertions.append({**assertion, "preserved": preserved})
        checks.append({"case_id": case["id"], "gold_subject": fact["subject"],
                       "emitted_subject": match["subject"] if match else None,
                       "group_preserved": all(a["preserved"] for a in assertions), "assertions": assertions})
        if match is not None:
            emitted.remove(match)
    return checks


def snapshot(sheet, case, record, run):
    if (run["status"] != "needs_review" or run["approval"] is not None or run["draft"] is not None
            or run["audit"] or "model_step_failed" in run["report"]["issues"]):
        raise ValueError("comparison requires complete pre-review runs without model failures")
    return {"score": score_case(sheet, case, record["raw_output"], run),
            "report": run["report"], "review_queue": run["review_queue"],
            "correction_history": correction_checks(case, run["report"])}


def summarize(rows, side, child_slots):
    scores = [row[side]["score"] for row in rows]
    correct = sum(p["matches_current_fact"] for score in scores for p in score["proposal_checks"]
                  if p["field"] == "children")
    checks = [check for row in rows for check in row[side]["correction_history"]]
    assertions = [assertion for check in checks for assertion in check["assertions"]]
    return {"scores": aggregate(scores), "child_field_accuracy": metric(correct, child_slots),
            "correction_history": {**metric(sum(a["preserved"] for a in assertions), len(assertions)),
                                   "checks": checks}}


def compare(live=False):
    manifest_sha = verify_child_manifest()
    pairs, rows = load_dev_cases(), []
    hashes = {"baseline": {}, "candidate": {}}
    runtime = ROOT / ".runtime/child-extraction"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runs-", dir=runtime) as directory:
        baseline_service = ReviewService(Path(directory) / "baseline.sqlite")
        for sheet, case in pairs:
            case_id = sheet["id"]
            baseline, hashes["baseline"][case_id] = recording_for(sheet, case)
            before = snapshot(sheet, case, baseline, baseline_service.create(baseline))
            if case_id in CHILD_IDS:
                candidate, hashes["candidate"][case_id] = recording_for(sheet, case, child=True, live=live)
                index = SimpleNamespace(search=lambda query, limit, note_id=sheet["note_id"]: [{"id": note_id, "score": 1.0}])
                service = ReviewService(Path(directory) / (case_id + ".sqlite"),
                    model_factory=lambda **settings: RecordedChildModel(candidate), index_factory=lambda: index)
                run = service.create_live(TranscriptRequest(transcript=case["transcript"]), sheet["note_id"])
                after = snapshot(sheet, case, candidate, run)
            else:
                hashes["candidate"][case_id] = hashes["baseline"][case_id]
                after = before
            rows.append({"id": case_id, "candidate_source": "child_capture" if case_id in CHILD_IDS
                         else "unchanged_baseline_capture", "before": before, "after": after})
    child_slots = sum(f["field"] == "children" and f["status"] == "known" for sheet, _ in pairs for f in sheet["facts"])
    return {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "scope": SCOPE,
            "model": {"name": DEFAULT_MODEL, "digest": DEFAULT_DIGEST, "options": OPTIONS},
            "prompt_version": CHILD_PROMPT_VERSION, "manifest_sha256": manifest_sha,
            "baseline_manifest_sha256": sha256(ROOT / "eval/manifest.json"),
            "evaluation_basis": "Pre-review proposals through the unchanged ReviewService graph; specified note, not retrieval quality; no scripted review or approval.",
            "nonchild_reuse": {"case_ids": [i for i in DEV_IDS if i not in CHILD_IDS],
                               "description": "Five nonchild outputs are reused unchanged from legacy baseline captures; no candidate inference."},
            "recording_sha256": hashes, "before": summarize(rows, "before", child_slots),
            "after": summarize(rows, "after", child_slots), "case_results": rows}


def check_and_write(report, check=False):
    if check:
        expected = json.loads((ROOT / "eval/child_extraction/report.json").read_text())
        stable = lambda value: {key: item for key, item in value.items() if key != "generated_at"}
        if stable(report) != stable(expected):
            raise ValueError("replay differs from the committed child report measurements or evidence")
    output = ROOT / ".runtime/child-extraction/report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Capture missing child development outputs once; never overwrite.")
    parser.add_argument("--check", action="store_true", help="Compare the complete replay against the committed child report.")
    args = parser.parse_args()
    if args.live and args.check:
        parser.error("capture and committed-report checking are separate operations")
    report = compare(args.live)
    output = check_and_write(report, args.check)
    for side in ("before", "after"):
        print(side, json.dumps(report[side]["scores"]["metrics"], sort_keys=True))
        print("child_field_accuracy", json.dumps(report[side]["child_field_accuracy"]))
    print("PASS: fixed ten development cases; five nonchild captures reused unchanged. Report:", output)


if __name__ == "__main__":
    main()
