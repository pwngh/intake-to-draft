"""Frozen invented cases and explicitly scripted review, separate from model scoring."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.extraction import check_output, note_by_id
from intake_draft.workflow import ReviewRequest

DEV_IDS = {"c01", "c02", "c03", "c11", "c12", "c13", "c21", "c22", "c31", "c32"}
REVIEWER = "Scripted Fact-Sheet Reviewer"
APPROVER = "Scripted Fact-Sheet Approver"


def words(value):
    return re.findall(r"\w+", value.casefold())


def load_cases(root: Path):
    sheets = sum((json.loads(path.read_text()) for path in sorted((root / "eval/fact_sheets").glob("*.json"))), [])
    if len(sheets) != 40 or {sheet["id"] for sheet in sheets} != {f"c{i:02}" for i in range(1, 41)}:
        raise ValueError("evaluation requires forty unique fact sheets")
    pairs = []
    for sheet in sorted(sheets, key=lambda row: row["id"]):
        case = json.loads((root / "eval/cases" / (sheet["id"] + ".json")).read_text())
        if case["id"] != sheet["id"] or sheet["split"] != ("dev" if sheet["id"] in DEV_IDS else "holdout"):
            raise ValueError("case identity or frozen split mismatch")
        source = number_transcript(TranscriptRequest(transcript=case["transcript"]))
        note = note_by_id(sheet["note_id"])
        facts = {(row["field"], row["subject"]): row for row in sheet["facts"]}
        if len(facts) != len(sheet["facts"]) or {f[0] for f in facts} != set(note["required_fields"]):
            raise ValueError("fact sheet must cover every requirement without duplicate slots")
        if any(row["status"] not in {"known", "missing", "uncertain", "conflicting"}
               or (row["status"] == "known") != (isinstance(row["value"], str) and bool(row["value"]))
               for row in facts.values()):
            raise ValueError("invalid expected fact status/value")
        report = check_output(json.dumps({"facts": case["evidence"]}), source, note)
        fields = {(row["field"], row["subject"]): row for row in report["fields"]}
        if report["issues"] or not fields.keys() <= facts.keys():
            raise ValueError("gold evidence has invalid structure or unknown slots")
        for key, fact in facts.items():
            field = fields.get(key, {})
            if any(not item["evidence_valid"] for item in field.get("history", [])):
                raise ValueError(f"{sheet['id']} has an unsupported gold quotation")
            proposal = field.get("proposed")
            if fact["status"] == "known":
                if not proposal or words(proposal["value"]) != words(fact["value"]):
                    raise ValueError(f"{sheet['id']} gold evidence differs from its fact sheet: {key}")
            elif proposal is not None:
                raise ValueError("unresolved gold facts must not have a usable proposal")
        pairs.append((sheet, case))
    return pairs


def verify_manifest(root: Path):
    manifest = json.loads((root / "eval/manifest.json").read_text())
    for relative, expected in manifest["files"].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError(f"frozen evaluation input changed: {relative}")
    return manifest


def scripted_review(service, run, sheet, case):
    """Simulate decisions using gold facts AFTER scoring; never claim human inspection."""
    evidence = {(row["field"], row["subject"]): row["assertions"] for row in case["evidence"]}
    queue = list(run["review_queue"])
    used, assignments = set(), []
    # Match complete child identities before assigning corrections to remaining slots.
    ordered = sorted(sheet["facts"], key=lambda f: not any(
        r["field"] == f["field"] and r["proposed"] and f["value"] is not None
        and words(r["proposed"]["value"]) == words(f["value"]) for r in queue))
    for fact in ordered:
        candidates = [r for r in queue if r["field"] == fact["field"] and (r["field"], r["subject"]) not in used]
        match = next((r for r in candidates if r["proposed"] and fact["value"] is not None
                      and words(r["proposed"]["value"]) == words(fact["value"])), None)
        match = match or next((r for r in candidates if r["subject"] == fact["subject"]), None)
        match = match or (candidates[0] if candidates else None)
        if match is None:
            subject = "case"
            if fact["field"] == "children":
                subject = next(f"child-{n}" for n in range(1, 101) if ("children", f"child-{n}") not in used
                               and not any(r["subject"] == f"child-{n}" for r in queue if r["field"] == "children"))
            match = {"field": fact["field"], "subject": subject, "proposed": None}
        used.add((match["field"], match["subject"]))
        assignments.append((fact, match))

    def decide(action, **kwargs):
        nonlocal run
        run = service.submit(run["run_id"], ReviewRequest(action=action, reviewer=REVIEWER,
                             expected_revision=run["revision"], **kwargs))

    for fact, row in assignments:
        slot = {"field": row["field"], "subject": row["subject"]}
        if fact["status"] != "known":
            decide("reject", **slot, reason=f"Fact sheet marks this {fact['status']}; supplemental intake is required.")
            continue
        gold = max((a for a in evidence[(fact["field"], fact["subject"])]
                    if a["kind"] != "uncertain" and words(a["value"]) == words(fact["value"])),
                   key=lambda a: max(c["line"] for c in a["citations"]))
        proposal = row["proposed"]
        if (proposal and proposal["value"] == fact["value"]
                and {c["line"] for c in gold["citations"]} <= {c["line"] for c in proposal["citations"]}):
            decide("accept", **slot)
        else:
            decide("correct", **slot, value=fact["value"], citations=gold["citations"],
                   reason="Scripted comparison to the authored fact sheet and original transcript evidence.")
    for row in queue:
        if (row["field"], row["subject"]) not in used:
            decide("reject", field=row["field"], subject=row["subject"], reason="Extra model subject has no fact-sheet support.")
    if not any(row["needs_action"] for row in run["review_queue"]):
        run = service.submit(run["run_id"], ReviewRequest(action="approve", reviewer=APPROVER,
                             expected_revision=run["revision"], confirmed_complete=True))
    return run


def review_summary(run):
    return {"status": run["status"], "approval_kind": "scripted_fixture" if run["approval"] else None,
            "approval": run["approval"], "actions": dict(Counter(event["action"] for event in run["audit"]))}
