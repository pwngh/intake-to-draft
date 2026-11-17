"""Exercise the local HTTP boundary, including its safe error responses."""

import json

import pytest
from fastapi.testclient import TestClient

from intake_draft.api import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_identifies_the_limited_demonstration_stage(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "demonstration": True,
        "stage": "intake-contract",
    }


def test_validation_returns_stable_numbered_source_without_guessing_facts(client):
    payload = {"transcript": "Caller: My name is Morgan Vale.\r\n\r\nCaller: I do not know the date.\r\n"}
    first = client.post("/intakes/validate", json=payload)
    second = client.post("/intakes/validate", json=payload)

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["lines"] == [
        {"number": 1, "text": "Caller: My name is Morgan Vale."},
        {"number": 2, "text": ""},
        {"number": 3, "text": "Caller: I do not know the date."},
    ]
    assert set(first.json()) == {"transcript", "sha256", "lines"}


@pytest.mark.parametrize("bad_character", ["\x00", "\x1b", "\x85", "\ud800"])
def test_unsupported_characters_return_422_without_echoing_intake(client, bad_character):
    # Send JSON escapes so a surrogate reaches the API rather than failing in
    # the HTTP client's UTF-8 encoder.
    body = json.dumps({"transcript": "Caller: PrivateTestMarker" + bad_character})
    response = client.post("/intakes/validate", content=body, headers={"content-type": "application/json"})

    assert response.status_code == 422
    assert "PrivateTestMarker" not in response.text
    assert all(set(error) == {"loc", "msg", "type"} for error in response.json()["detail"])


@pytest.mark.parametrize("payload", [
    {},
    {"transcript": 123},
    {"transcript": "Caller: Hello.", "approved": True},
    ["Caller: Hello."],
])
def test_invalid_request_shapes_are_client_errors(client, payload):
    assert client.post("/intakes/validate", json=payload).status_code == 422


def test_reference_search_returns_invented_requirements_and_repeatable_ranking(client):
    payload = {"query": "An adult name change to a new name.", "limit": 1}
    response = client.post("/references/search", json=payload)

    assert response.status_code == 200
    assert response.json() == client.post("/references/search", json=payload).json()
    assert response.json()["demonstration"] is True
    match, = response.json()["matches"]
    assert match["petition_type"] == "adult_name_change"
    assert match["demonstration"] is True
    assert "requested_name" in match["required_fields"]
    assert 0 < match["score"] <= 1


def test_unknown_search_terms_do_not_return_a_checklist(client):
    response = client.post("/references/search", json={"query": "quasar xylophone zeppelin"})
    assert response.status_code == 200
    assert response.json() == {"demonstration": True, "backend": "keyword", "matches": []}


@pytest.mark.parametrize("payload", [
    {},
    {"query": "   "},
    {"query": "divorce", "limit": True},
    {"query": "divorce", "limit": "1"},
    {"query": "divorce", "limit": 41},
    {"query": "divorce", "model": "untrusted-model"},
])
def test_search_rejects_invalid_or_unsupported_options(client, payload):
    assert client.post("/references/search", json=payload).status_code == 422


def test_invalid_search_text_is_not_reflected_in_errors(client):
    body = json.dumps({"query": "PrivateQueryMarker\ud800"})
    response = client.post("/references/search", content=body, headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert "PrivateQueryMarker" not in response.text


def test_recorded_graph_exposes_latest_and_earlier_evidence_without_approving(client):
    report = client.get("/demo/extraction").json()
    assert report == client.get("/demo/extraction").json()
    assert report["status"] == "needs_review" and not report["approved"]
    birth = [row for row in report["provenance_table"] if row["field"] == "birth_date"]
    assert [(row["value"], row["lines"], row["selection"]) for row in birth] == [
        ("1991-06-18", [4], "earlier_or_unresolved"), ("1991-06-19", [8], "proposed")]
    address, = [row for row in report["provenance_table"] if row["field"] == "petitioner_address"]
    assert address["lines"] == [5, 6] and address["selection"] == "proposed"
