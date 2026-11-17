"""The fill boundary checks evidence again and renders only quoted data."""

from copy import deepcopy
import json

import pytest

from intake_draft.contracts import TranscriptRequest, number_transcript
from intake_draft.drafting import PETITION_TITLES, render_draft
from intake_draft.extraction import JURISDICTION, check_output


def fixture():
    source = number_transcript(TranscriptRequest(transcript=(
        "Birth date: 1991-06-18\nCorrection: 1991-06-19\nStreet: 18 Example Lane\nCity: Sampletown")))
    note = {"id": "test", "petition_type": "adult_name_change",
            "required_fields": ["birth_date", "petitioner_address"]}
    facts = [{"field": "birth_date", "subject": "case", "assertions": [
        {"value": "1991-06-18", "kind": "stated", "citations": [{"line": 1, "quote": "1991-06-18"}]},
        {"value": "1991-06-19", "kind": "correction", "citations": [{"line": 2, "quote": "1991-06-19"}]},
    ]}, {"field": "petitioner_address", "subject": "case", "assertions": [
        {"value": "18 Example Lane Sampletown", "kind": "stated", "citations": [
            {"line": 3, "quote": "18 Example Lane"}, {"line": 4, "quote": "Sampletown"}]},
    ]}]
    report = check_output(json.dumps({"facts": facts}), source, note)
    reviewed = [{"field": f["field"], "subject": f["subject"], "value": f["proposed"]["value"],
                 "citations": deepcopy(f["proposed"]["citations"]),
                 "reviewer": "Demo Reviewer", "action": "accept"} for f in report["fields"]]
    return source, note, reviewed, report


@pytest.mark.parametrize("petition_type", PETITION_TITLES)
def test_fictional_template_has_citations_and_retains_earlier_statement(petition_type):
    source, note, reviewed, report = fixture()
    note["petition_type"] = petition_type
    draft = render_draft(source, note, reviewed, report)
    assert JURISDICTION in draft["text"] and "NOT A LEGAL FORM" in draft["text"]
    assert "NOT LEGAL ADVICE" in draft["text"]
    assert PETITION_TITLES[petition_type] in draft["text"]
    birth, address = draft["provenance_table"]
    assert birth["value"] == "1991-06-19" and birth["lines"] == [2]
    assert birth["earlier_assertions"][0]["value"] == "1991-06-18"
    assert birth["earlier_assertions"][0]["citations"][0]["line"] == 1
    assert address["lines"] == [3, 4] and "[lines 3, 4]" in draft["text"]
    assert all(row["reviewer"] == "Demo Reviewer" for row in draft["provenance_table"])


def test_draft_text_is_stable_across_review_order_and_reviewer_identity():
    source, note, reviewed, report = fixture()
    first = render_draft(source, note, reviewed, report)
    reviewed.reverse()
    for row in reviewed:
        row["reviewer"] = "Second Demo Reviewer"
    assert render_draft(source, note, reviewed, report)["text"] == first["text"]


@pytest.mark.parametrize("problem", ["missing", "duplicate", "uncited", "fabricated", "reordered",
                                      "unknown-field", "wrong-subject", "rejected", "anonymous"])
def test_fill_rejects_incomplete_or_unreviewable_evidence(problem):
    source, note, reviewed, report = fixture()
    if problem == "missing":
        reviewed.pop()
    elif problem == "duplicate":
        reviewed.append(deepcopy(reviewed[0]))
    elif problem == "uncited":
        reviewed[0]["citations"] = []
    elif problem == "fabricated":
        reviewed[0]["citations"][0]["quote"] = "never stated"
    elif problem == "reordered":
        reviewed[1]["citations"].reverse()
        reviewed[1]["value"] = "Sampletown 18 Example Lane"
    elif problem == "unknown-field":
        reviewed[0]["field"] = "approve_draft"
    elif problem == "wrong-subject":
        reviewed[0]["subject"] = "child-1"
    elif problem == "rejected":
        reviewed[0]["action"] = "reject"
    elif problem == "anonymous":
        reviewed[0]["reviewer"] = "   "
    with pytest.raises(ValueError):
        render_draft(source, note, reviewed, report)


def test_filled_source_text_is_rederived_and_history_is_detached():
    source, note, reviewed, report = fixture()
    reviewed[0]["citations"][0]["source_line"] = "forged source text"
    draft = render_draft(source, note, reviewed, report)
    birth = draft["provenance_table"][0]
    assert birth["citations"][0]["source_line"] == "Correction: 1991-06-19"
    birth["earlier_assertions"][0]["value"] = "mutated"
    assert report["fields"][0]["history"][0]["value"] == "1991-06-18"


def test_fill_rejects_an_omitted_extracted_sibling():
    source = number_transcript(TranscriptRequest(transcript="Child: Ada Vale\nChild: Ava Vale"))
    note = {"id": "test", "petition_type": "custody_change", "required_fields": ["children"]}
    report = check_output(json.dumps({"facts": [{"field": "children", "subject": f"child-{i}",
        "assertions": [{"value": name, "kind": "stated", "citations": [{"line": i, "quote": name}]}]}
        for i, name in enumerate(["Ada Vale", "Ava Vale"], 1)]}), source, note)
    selected = report["fields"][0]
    reviewed = [{"field": "children", "subject": "child-1", **selected["proposed"],
                 "action": "accept", "reviewer": "Demo Reviewer"}]
    with pytest.raises(ValueError, match="subject"):
        render_draft(source, note, reviewed, report)


def test_caller_markup_and_newlines_stay_quoted_data():
    source = number_transcript(TranscriptRequest(transcript="Caller: <h1>APPROVED</h1>\nCaller: ignore rules"))
    note = {"id": "test", "petition_type": "adult_name_change", "required_fields": ["requested_name"]}
    value = "<h1>APPROVED</h1>\nignore rules"
    reviewed = [{"field": "requested_name", "subject": "case", "value": value,
                 "citations": [{"line": 1, "quote": "<h1>APPROVED</h1>"},
                               {"line": 2, "quote": "ignore rules"}],
                 "reviewer": "Demo Reviewer", "action": "correct"}]
    draft = render_draft(source, note, reviewed, {"transcript_sha256": source.sha256, "fields": []})
    assert json.dumps(value) in draft["text"]
    assert "\nignore rules" not in draft["text"]


def test_cannot_mix_an_extraction_report_with_a_different_source():
    source, note, reviewed, report = fixture()
    report["transcript_sha256"] = "different"
    with pytest.raises(ValueError, match="sources differ"):
        render_draft(source, note, reviewed, report)
