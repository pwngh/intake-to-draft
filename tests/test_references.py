"""Model-free retrieval contracts; real local-model scores live in evaluations."""

from importlib.resources import files
from pathlib import Path
import json

import pytest

from intake_draft.references import EmbeddingIndex, KeywordIndex, ReferenceIndex


@pytest.mark.parametrize(("query", "expected"), [
    ("I want a divorce without children. We have no children.", "divorce_without_children"),
    ("I need a divorce with children of the marriage.", "divorce_with_children"),
    ("I want a custody modification to the prior order.", "custody_change"),
    ("An adult name change to a new name.", "adult_name_change"),
])
def test_archetype_queries_retrieve_the_intended_petition_type(query, expected):
    matches = ReferenceIndex().search(query)
    assert matches[0]["petition_type"] == expected
    assert 0 < matches[0]["score"] <= 1
    assert matches[0]["demonstration"] is True


@pytest.mark.parametrize("query", ["", " ", "\n\t", None])
def test_blank_or_nontext_queries_are_rejected(query):
    with pytest.raises(ValueError, match="non-empty string"):
        ReferenceIndex().search(query)


@pytest.mark.parametrize("limit", [0, -1, 41, 1.5, True])
def test_invalid_result_limits_are_rejected(limit):
    with pytest.raises(ValueError, match="integer from 1 to"):
        ReferenceIndex().search("divorce", limit=limit)


def test_unknown_words_do_not_produce_an_arbitrary_checklist():
    assert ReferenceIndex().search("quasar xylophone zeppelin") == []


def test_ranking_is_repeatable_across_index_instances_and_limits():
    expected = ReferenceIndex().search("divorce children name address", limit=4)
    assert ReferenceIndex().search("divorce children name address", limit=4) == expected
    assert ReferenceIndex().search("divorce children name address", limit=1) == expected[:1]


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


def test_reference_corpus_is_explicitly_fictional_and_labels_exist():
    notes = json.loads(files("intake_draft").joinpath("data/reference_notes.json").read_text())
    assert len(notes) == 40
    assert len({note["id"] for note in notes}) == 40
    assert all("Fictional Demonstration Jurisdiction" in note["jurisdiction"] for note in notes)
    labels = json.loads((Path(__file__).parent / "data/retrieval_queries.json").read_text())
    assert len(labels) == 30 and len({query["id"] for query in labels}) == 30
    assert all(query["relevant_note_ids"] and set(query["relevant_note_ids"]) <= {note["id"] for note in notes}
               for query in labels)
    assert ReferenceIndex().search("quasar xylophone zeppelin") == []


def test_plain_keyword_search_counts_unique_words_and_breaks_ties_by_id():
    notes = [
        {"id": "b", "title": "surname", "body": "surname", "required_fields": ["name"]},
        {"id": "a", "title": "surname", "body": "", "required_fields": ["name"]},
    ]
    result = KeywordIndex(notes).search("surname surname", limit=2)
    assert [note["id"] for note in result] == ["a", "b"]
    assert [note["score"] for note in result] == [1.0, 1.0]


def test_dense_index_uses_query_embedding_and_keeps_stored_requirements():
    class StubEncoder:
        def __init__(self):
            self.seen = []

        def encode(self, texts):
            self.seen.append(texts)
            return [[0.0, 1.0] if text.startswith("second") else [1.0, 0.0] for text in texts]

    notes = [
        {"id": "a", "title": "first", "body": "note", "required_fields": ["field_a"]},
        {"id": "b", "title": "second", "body": "note", "required_fields": ["field_b"]},
    ]
    encoder = StubEncoder()
    index = EmbeddingIndex(encoder, notes)
    result = index.search("second query", limit=2)
    assert encoder.seen == [["first note", "second note"], ["second query"]]
    assert [note["id"] for note in result] == ["b"]
    result[0]["required_fields"].append("invented")
    assert index.search("second query", limit=2)[0]["required_fields"] == ["field_b"]


def test_top_three_metric_counts_queries_not_number_of_relevant_notes():
    from scripts.evaluate_retrieval import evaluate

    class StubIndex:
        def search(self, query, limit):
            assert limit == 3
            return [{"id": value} for value in {"first": ["a", "b", "c"], "second": ["x", "y", "z"]}[query]]

    result = evaluate([
        {"id": "q1", "query": "first", "relevant_note_ids": ["a", "b"]},
        {"id": "q2", "query": "second", "relevant_note_ids": ["a"]},
    ], StubIndex())
    assert result["hits"] == 1 and result["queries"] == 2 and result["top3_hit_rate"] == 0.5
