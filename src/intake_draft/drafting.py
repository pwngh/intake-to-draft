"""Render reviewed, cited facts into an original fictional demonstration template."""

from copy import deepcopy
import json

from intake_draft.contracts import NumberedTranscript
from intake_draft.extraction import JURISDICTION, check_output

PETITION_TITLES = {
    "divorce_without_children": "Divorce without children",
    "divorce_with_children": "Divorce with children",
    "custody_change": "Custody change",
    "adult_name_change": "Adult name change",
}


def render_draft(source: NumberedTranscript, note: dict, reviewed: list[dict],
                 extraction_report: dict) -> dict:
    """Recheck evidence at fill; final human approval is the workflow's gate."""
    if extraction_report["transcript_sha256"] != source.sha256:
        raise ValueError("extraction and draft sources differ")
    facts, decisions = [], {}
    try:
        for row in reviewed:
            if (row["action"] not in {"accept", "correct"}
                    or not isinstance(row["reviewer"], str) or not row["reviewer"].strip()):
                raise ValueError("every filled value needs a named accepting or correcting reviewer")
            facts.append({"field": row["field"], "subject": row["subject"], "assertions": [{
                "value": row["value"], "kind": "stated", "citations": [
                    {"line": citation["line"], "quote": citation["quote"]}
                    for citation in row["citations"]],
            }]})
            decisions[(row["field"], row["subject"])] = row
        checked = check_output(json.dumps({"facts": facts}), source, note)
    except (KeyError, TypeError) as exc:
        raise ValueError("invalid reviewed value") from exc
    if checked["issues"] or checked["missing"] or any(f["proposed"] is None for f in checked["fields"]):
        raise ValueError("draft requires complete reviewed values with valid source citations")
    original = {(f["field"], f["subject"]): f for f in extraction_report["fields"]}
    if not original.keys() <= decisions.keys():
        raise ValueError("an extracted subject has not been reviewed")

    table = []
    for field in checked["fields"]:
        key = (field["field"], field["subject"])
        selected, decision = field["proposed"], decisions[key]
        history = original.get(key, {}).get("history", [])
        earlier = [item for item in history if item["value"] != selected["value"]
                   or item["citations"] != selected["citations"]]
        table.append({"field": field["field"], "subject": field["subject"],
                      "value": selected["value"], "citations": selected["citations"],
                      "lines": sorted({c["line"] for c in selected["citations"]}),
                      "reviewer": decision["reviewer"], "action": decision["action"],
                      "earlier_assertions": deepcopy(earlier)})

    lines = [
        "DEMONSTRATION PETITION — NOT A LEGAL FORM", JURISDICTION,
        "DEMONSTRATION ONLY. NOT LEGAL ADVICE.", "",
        f"Petition type: {PETITION_TITLES[note['petition_type']]}", "",
        "The following reviewed intake facts populate this invented demonstration.",
        "They do not establish rights, court requirements, or a legal outcome.", "",
        "Reviewed facts:",
    ]
    for row in table:
        label = row["field"].replace("_", " ").capitalize()
        subject = "" if row["subject"] == "case" else f" ({row['subject']})"
        references = ", ".join(str(number) for number in row["lines"])
        lines.append(f"{label}{subject}: {json.dumps(row['value'])} [lines {references}]")
    lines.extend(["", "End of fictional demonstration petition."])
    return {"text": "\n".join(lines) + "\n", "provenance_table": table}
