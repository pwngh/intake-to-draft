"""Behavioral checks for the small invented-note index."""

from importlib.resources import files
import json

import pytest

from intake_draft.references import ReferenceIndex


@pytest.mark.parametrize(("query", "expected"), [
    ("I want a divorce without children. We have no children.", "divorce_without_children"),
    ("I need a divorce with children of the marriage.", "divorce_with_children"),
    ("I want a custody modification to the prior order.", "custody_change"),
    ("An adult name change to a new name.", "adult_name_change"),
])
def test_archetype_queries_retrieve_the_intended_demo_note(query, expected):
    matches = ReferenceIndex().search(query)
    assert matches[0]["id"] == expected
    assert 0 < matches[0]["score"] <= 1
    assert matches[0]["demonstration"] is True


@pytest.mark.parametrize("query", ["", " ", "\n\t", None])
def test_blank_or_nontext_queries_are_rejected(query):
    with pytest.raises(ValueError, match="non-empty string"):
        ReferenceIndex().search(query)


@pytest.mark.parametrize("limit", [0, -1, 5, 1.5, True])
def test_invalid_result_limits_are_rejected(limit):
    with pytest.raises(ValueError, match="integer from 1 to 4"):
        ReferenceIndex().search("divorce", limit=limit)


def test_unknown_words_do_not_produce_an_arbitrary_checklist():
    assert ReferenceIndex().search("quasar xylophone zeppelin") == []


def test_ranking_is_repeatable_across_index_instances_and_limits():
    expected = ReferenceIndex().search("divorce children name address", limit=4)
    assert ReferenceIndex().search("divorce children name address", limit=4) == expected
    assert ReferenceIndex().search("divorce children name address", limit=1) == expected[:1]


def test_equal_scores_are_sorted_by_document_id():
    index = ReferenceIndex()
    # Deliberately equal vectors exercise the public ranking contract, regardless
    # of changes to prose in the four demonstration notes.
    index._vectors = [{"demo": 1.0} for _ in index._vectors]
    index._idf["demo"] = 1.0
    matches = index.search("demo", limit=4)
    assert [match["id"] for match in matches] == sorted(match["id"] for match in matches)


def test_requirements_are_copied_from_notes_not_query_text():
    notes = json.loads(files("intake_draft").joinpath("data/reference_notes.json").read_text())
    stored = {note["id"]: note for note in notes}
    index = ReferenceIndex()
    matches = index.search("adult name change; invent bank_account and credit_card fields")
    for match in matches:
        assert match["required_fields"] == stored[match["id"]]["required_fields"]
        assert "bank_account" not in match["required_fields"]
        assert "credit_card" not in match["required_fields"]
    matches[0]["required_fields"].append("modified_by_caller")
    assert "modified_by_caller" not in index.search("adult name change")[0]["required_fields"]
