"""Local adapter contract tests; MockTransport never loads a model or needs a key."""

import json

import httpx
import pytest

from intake_draft.extraction import ModelOutput, prompt_hash
from intake_draft.local_model import (
    DEFAULT_DIGEST, DEFAULT_MODEL, MAX_OUTPUT_BYTES, MAX_RESPONSE_BYTES, OPTIONS,
    LocalModel, ModelResponseError, ModelUnavailable,
)

MESSAGES = [{"role": "system", "content": "Extract evidence."}, {"role": "user", "content": "Invented intake."}]


def adapter(*, entry=None, response=None, chat=None, **kwargs):
    requests = []
    entry = {"name": DEFAULT_MODEL, "model": DEFAULT_MODEL, "digest": DEFAULT_DIGEST} if entry is None else entry
    response = {"model": DEFAULT_MODEL, "done": True, "done_reason": "stop",
                "message": {"role": "assistant", "content": '{"facts":[]}'},
                "prompt_eval_count": 10, "eval_count": 4, "total_duration": 100} if response is None else response
    def handle(request):
        requests.append(request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [entry]})
        return chat(request) if chat else httpx.Response(200, json=response)
    return LocalModel(transport=httpx.MockTransport(handle), **kwargs), requests


def test_verified_local_inference_sends_schema_and_records_returned_metadata():
    model, requests = adapter()
    assert model(MESSAGES, "source-hash") == '{"facts":[]}'
    assert [request.url.path for request in requests] == ["/api/tags", "/api/chat"]
    body = json.loads(requests[1].content)
    assert body == {"model": DEFAULT_MODEL, "messages": MESSAGES, "stream": False, "keep_alive": 0,
                    "format": ModelOutput.model_json_schema(), "options": OPTIONS}
    assert model.last_result["model_digest"] == DEFAULT_DIGEST
    assert model.last_result["prompt_sha256"] == prompt_hash(MESSAGES)
    assert model.last_result["transcript_sha256"] == "source-hash"
    assert model.last_result["usage"] == {"prompt_eval_count": 10, "eval_count": 4, "total_duration": 100}


@pytest.mark.parametrize("entry", [
    {"name": "different", "digest": DEFAULT_DIGEST},
    {"name": DEFAULT_MODEL, "digest": "0" * 64},
    {"name": DEFAULT_MODEL, "digest": DEFAULT_DIGEST, "remote_model": "remote"},
    {"name": DEFAULT_MODEL, "digest": DEFAULT_DIGEST, "remote_host": "https://example.invalid"},
])
def test_missing_changed_or_remote_models_never_receive_the_transcript(entry):
    model, requests = adapter(entry=entry)
    with pytest.raises(ModelUnavailable):
        model(MESSAGES, "source-hash")
    assert len(requests) == 1 and requests[0].method == "GET"
    assert model.last_result == {}


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1.example.com",
    "http://user:password@localhost:11434", "http://localhost/path", "http://localhost?target=cloud",
    "http://localhost#fragment", "ftp://localhost", "not-a-url"])
def test_nonlocal_or_ambiguous_urls_are_rejected_without_network(url):
    with pytest.raises(ModelUnavailable):
        LocalModel(base_url=url)


def test_loopback_ipv6_is_allowed_but_cloud_model_names_are_not():
    assert LocalModel(base_url="http://[::1]:11434/").base_url == "http://[::1]:11434"
    with pytest.raises(ModelUnavailable):
        LocalModel(model="qwen:cloud")


@pytest.mark.parametrize("change", [
    {"model": "other-model"}, {"done": False}, {"done_reason": "length"},
    {"message": {"role": "assistant", "content": 42}},
    {"message": {"role": "assistant", "content": "{}", "tool_calls": [{"name": "run"}]}},
    {"message": {"role": "user", "content": "{}"}}, {"eval_count": True}, {"eval_count": 10**80},
])
def test_unfinished_or_unexpected_envelopes_fail_without_repair(change):
    response = {"model": DEFAULT_MODEL, "done": True, "done_reason": "stop",
                "message": {"role": "assistant", "content": "{}"}, **change}
    model, _ = adapter(response=response)
    with pytest.raises(ModelResponseError):
        model(MESSAGES, "source-hash")
    assert model.last_result == {}


def test_malformed_model_content_is_returned_unchanged_for_the_extraction_checker():
    raw = '{"facts":'
    model, _ = adapter(response={"model": DEFAULT_MODEL, "done": True, "done_reason": "stop",
                                  "message": {"role": "assistant", "content": raw}})
    assert model(MESSAGES, "source-hash") == raw


@pytest.mark.parametrize("content", [b"not-json PrivateMarker", b"x" * (MAX_RESPONSE_BYTES + 1),
                                      b"[" * 2000 + b"0" + b"]" * 2000])
def test_invalid_or_oversized_service_envelopes_are_bounded_and_not_echoed(content):
    model, _ = adapter(chat=lambda request: httpx.Response(200, content=content))
    with pytest.raises(ModelResponseError) as error:
        model(MESSAGES, "source-hash")
    assert "PrivateMarker" not in str(error.value)


def test_timeout_and_redirects_never_fall_back_or_follow_external_locations():
    def timeout(request):
        raise httpx.ReadTimeout("PrivateMarker", request=request)
    for chat in (timeout, lambda request: httpx.Response(307, headers={"location": "https://example.invalid"})):
        model, requests = adapter(chat=chat)
        with pytest.raises(ModelUnavailable) as error:
            model(MESSAGES, "source-hash")
        assert len(requests) == 2 and "PrivateMarker" not in str(error.value)


def test_http_client_explicitly_disables_environment_proxies_and_redirects(monkeypatch):
    real_client, seen = httpx.Client, {}
    def client(**kwargs):
        seen.update(kwargs)
        return real_client(**kwargs)
    monkeypatch.setattr(httpx, "Client", client)
    model, _ = adapter(timeout=12)
    model(MESSAGES, "source-hash")
    assert seen["trust_env"] is False and seen["follow_redirects"] is False
    assert seen["timeout"].read == 12 and seen["headers"]["Accept-Encoding"] == "identity"


def test_output_limit_and_failed_retry_cannot_leave_stale_success_metadata():
    model, _ = adapter()
    model(MESSAGES, "source-hash")
    assert model.last_result
    model.expected_digest = "0" * 64
    with pytest.raises(ModelUnavailable):
        model(MESSAGES, "source-hash")
    assert model.last_result == {}
    too_large, _ = adapter(response={"model": DEFAULT_MODEL, "done": True, "done_reason": "stop",
        "message": {"role": "assistant", "content": "x" * (MAX_OUTPUT_BYTES + 1)}})
    with pytest.raises(ModelResponseError):
        too_large(MESSAGES, "source-hash")
