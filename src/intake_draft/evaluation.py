"""Frozen, offline scoring of pre-review proposals against authored fact sheets."""

from collections import Counter
import json
import re

SCORING_VERSION = "1"
DEFINITIONS = {
    "field_accuracy": "Correct checked proposals / known fact-sheet slots; omissions fail. Child IDs are ignored, but full name/date values must match as a multiset.",
    "citation_accuracy": "Supported raw assertion groups / all raw assertion groups, including earlier and uncertain claims. Exact quotes must exist on their cited lines and jointly contain the value words in order. This measures literal containment, not whether the caller asserted the value as a fact. Malformed claim entries count as failures; unparseable whole outputs have zero groups and are listed separately.",
    "missing_fact_review_rate": "Unresolved fact-sheet slots with no usable proposal and an empty pending review row / all unresolved slots. Reserve empty child rows for unmatched known children first; remaining rows can cover unresolved children only when no unmatched usable child proposal exists.",
    "escaped_guess_rate": "Incorrect checked proposals / all checked proposals, including invented, stale, misattributed, and duplicate values. This is before mandatory human approval, not a rate of incorrect released drafts.",
    "normalization": "Unicode word tokens after case folding; punctuation and whitespace are ignored. No semantic model judge or post-hoc aliases.",
}
METRICS = tuple(key for key in DEFINITIONS if key != "normalization")


def tokens(value):
    return tuple(re.findall(r"\w+", value.casefold())) if isinstance(value, str) else ()


def _slot(field, subject):
    return field, "any-child" if field == "children" else subject


def _claims(raw):
    try:
        output = json.loads(raw)
    except (TypeError, ValueError, RecursionError):
        return [], True
    if not isinstance(output, dict) or not isinstance(output.get("facts"), list):
        return [], True
    claims, malformed = [], set(output) != {"facts"}
    for fact in output["facts"]:
        if not isinstance(fact, dict):
            claims.append((None, None, None))
            malformed = True
            continue
        malformed |= set(fact) != {"field", "subject", "assertions"}
        assertions = fact.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            assertions, malformed = [None], True
        for assertion in assertions:
            malformed |= not isinstance(assertion, dict)
            claims.append((fact.get("field"), fact.get("subject"), assertion))
    return claims, malformed


def _citation_supported(assertion, lines):
    if not isinstance(assertion, dict):
        return False
    value = tokens(assertion.get("value"))
    citations = assertion.get("citations")
    if not value or not isinstance(citations, list) or not citations:
        return False
    positions, quoted_words, end_by_line = [], [], {}
    for citation in citations:
        if not isinstance(citation, dict):
            return False
        line, quote = citation.get("line"), citation.get("quote")
        if type(line) is not int or not 1 <= line <= len(lines) or not isinstance(quote, str) or not quote.strip():
            return False
        start = lines[line - 1].find(quote, end_by_line.get(line, 0))
        words = tokens(quote)
        if start < 0 or not set(words).intersection(value):
            return False
        end_by_line[line] = start + len(quote)
        positions.append(line)
        quoted_words.extend(words)
    if positions != sorted(positions):
        return False
    cursor = 0
    for word in quoted_words:
        if cursor < len(value) and word == value[cursor]:
            cursor += 1
    if cursor != len(value):
        return False
    return True


def _metric(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "rate": numerator / denominator if denominator else None}


def score_case(sheet, case, raw, run):
    """Score the immutable extraction report and queue BEFORE review actions."""
    facts = sheet["facts"]
    known = [fact for fact in facts if fact["status"] == "known"]
    truth = Counter((*_slot(f["field"], f["subject"]), tokens(f["value"])) for f in known)
    available = truth.copy()
    proposal_checks = []
    for row in run["report"]["fields"]:
        if row["proposed"] is None:
            continue
        value = row["proposed"]["value"]
        key = (*_slot(row["field"], row["subject"]), tokens(value))
        correct = available[key] > 0
        if correct:
            available[key] -= 1
        proposal_checks.append({"field": row["field"], "subject": row["subject"],
                                "value": value, "matches_current_fact": correct})
    correct = sum(row["matches_current_fact"] for row in proposal_checks)
    queue = run["review_queue"]
    empty_children = sum(row["field"] == "children" and row["proposed"] is None
                         and row["needs_action"] is True for row in queue)
    known_child_deficits = sum(count for key, count in available.items() if key[0] == "children")
    empty_children = max(0, empty_children - known_child_deficits)
    unsafe_child = any(row["field"] == "children" and not row["matches_current_fact"] for row in proposal_checks)
    missing_checks = []
    for fact in facts:
        if fact["status"] == "known":
            continue
        field, subject = fact["field"], fact["subject"]
        if field == "children":
            routed = not unsafe_child and empty_children > 0
            empty_children -= int(routed)
        else:
            proposed = any(row["field"] == field and row["subject"] == subject for row in proposal_checks)
            routed = not proposed and any(row["field"] == field and row["subject"] == subject
                and row["proposed"] is None and row["needs_action"] is True for row in queue)
        missing_checks.append({"field": field, "subject": subject, "status": fact["status"], "routed_empty": routed})
    claims, malformed = _claims(raw)
    # Match the source convention independently: canonicalize endings, remove one terminator.
    text = case["transcript"].replace("\r\n", "\n").replace("\r", "\n")
    lines = text.removesuffix("\n").split("\n")
    citation_checks = [{"field": field if isinstance(field, str) else None,
        "subject": subject if isinstance(subject, str) else None,
        "value": assertion.get("value") if isinstance(assertion, dict) and isinstance(assertion.get("value"), str) else None,
        "supported": _citation_supported(assertion, lines)}
        for field, subject, assertion in claims]
    malformed |= "malformed_model_output" in run["report"].get("issues", [])
    return {"id": sheet["id"], "split": sheet["split"], "note_id": sheet["note_id"],
        "malformed_output": malformed, "model_step_failed": "model_step_failed" in run["report"].get("issues", []),
        "metrics": {
            "field_accuracy": _metric(correct, len(known)),
            "citation_accuracy": _metric(sum(c["supported"] for c in citation_checks), len(citation_checks)),
            "missing_fact_review_rate": _metric(sum(c["routed_empty"] for c in missing_checks), len(missing_checks)),
            "escaped_guess_rate": _metric(len(proposal_checks) - correct, len(proposal_checks))},
        "proposal_checks": proposal_checks, "citation_checks": citation_checks, "missing_checks": missing_checks}


def aggregate(rows):
    """Micro-average one explicitly labeled split; never pool development and holdout."""
    rows = list(rows)
    splits = {row["split"] for row in rows}
    if len(splits) > 1 or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("aggregate requires unique cases from one split")
    return {"scoring_version": SCORING_VERSION, "split": next(iter(splits), None), "case_count": len(rows),
        "case_ids": [row["id"] for row in rows], "definitions": DEFINITIONS,
        "malformed_cases": [row["id"] for row in rows if row["malformed_output"]],
        "model_failure_cases": [row["id"] for row in rows if row["model_step_failed"]],
        "metrics": {name: _metric(sum(row["metrics"][name]["numerator"] for row in rows),
                                  sum(row["metrics"][name]["denominator"] for row in rows)) for name in METRICS}}
