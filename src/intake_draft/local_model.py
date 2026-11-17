"""Pinned local Ollama inference; the extraction checker still distrusts its output."""

import ipaddress
import json
import math
import re

import httpx

from intake_draft.extraction import ModelOutput, PROMPT_VERSION, prompt_hash

DEFAULT_MODEL = "qwen3-coder:latest"
DEFAULT_DIGEST = "06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca"
OPTIONS = {"seed": 17, "temperature": 0, "num_ctx": 8192, "num_predict": 4096}
MAX_RESPONSE_BYTES = 262_144
MAX_OUTPUT_BYTES = 131_072
USAGE_FIELDS = ("prompt_eval_count", "eval_count", "total_duration", "load_duration",
                "prompt_eval_duration", "eval_duration")


class ModelUnavailable(ValueError):
    """The selected local model cannot be reached or verified; never substitute."""


class ModelResponseError(ValueError):
    """The local service returned an unusable envelope, without repairing it."""


def _local_url(value: str) -> str:
    try:
        url = httpx.URL(value)
        local = url.host == "localhost"
        if not local:
            local = ipaddress.ip_address(url.host).is_loopback
        if (not local or url.scheme not in {"http", "https"} or url.username or url.password
                or url.path not in {"", "/"} or url.query or url.fragment):
            raise ValueError
    except (ValueError, httpx.InvalidURL):
        raise ModelUnavailable("model service must use a loopback HTTP(S) URL without credentials or a path") from None
    return str(url).rstrip("/")


class LocalModel:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = DEFAULT_MODEL,
                 expected_digest: str = DEFAULT_DIGEST, timeout: float = 180,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = _local_url(base_url)
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model)
                or "cloud" in model.casefold() or not re.fullmatch(r"[0-9a-f]{64}", expected_digest)):
            raise ModelUnavailable("an explicit local model name and SHA-256 digest are required")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("model timeout must be positive and finite")
        self.model, self.expected_digest = model, expected_digest
        self.timeout, self.transport = timeout, transport
        self.last_result: dict = {}

    @staticmethod
    def _json(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
        try:
            with client.stream(method, path, **kwargs) as response:
                if response.status_code != 200:
                    raise ModelUnavailable("local model service rejected the request; no fallback was attempted")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ModelResponseError("unexpected compressed model response")
                body = bytearray()
                for chunk in response.iter_bytes(chunk_size=16_384):
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ModelResponseError("model service response exceeds the size limit")
                    body.extend(chunk)
        except httpx.RequestError:
            raise ModelUnavailable("local model service is unavailable or timed out; no fallback was attempted") from None
        try:
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError
        except (ValueError, UnicodeError, RecursionError):
            raise ModelResponseError("model service returned an invalid JSON envelope") from None
        return result

    def __call__(self, messages: list[dict], source_sha256: str) -> str:
        self.last_result = {}
        with httpx.Client(base_url=self.base_url, transport=self.transport, trust_env=False,
                          follow_redirects=False, timeout=httpx.Timeout(self.timeout, connect=min(5, self.timeout)),
                          headers={"Accept-Encoding": "identity"}) as client:
            tags = self._json(client, "GET", "/api/tags")
            models = tags.get("models")
            if not isinstance(models, list):
                raise ModelResponseError("model service returned an invalid model list")
            matches = [entry for entry in models if isinstance(entry, dict) and entry.get("name") == self.model]
            if (len(matches) != 1 or matches[0].get("digest") != self.expected_digest
                    or any(key in matches[0] for key in ("remote_model", "remote_host"))):
                raise ModelUnavailable("selected local model is absent, remote, or has a different digest")
            result = self._json(client, "POST", "/api/chat", json={
                "model": self.model, "messages": messages, "stream": False, "keep_alive": 0,
                "format": ModelOutput.model_json_schema(), "options": dict(OPTIONS),
            })
        message = result.get("message")
        if (result.get("model") != self.model or result.get("done") is not True
                or result.get("done_reason") != "stop" or not isinstance(message, dict)
                or message.get("role") != "assistant" or not isinstance(message.get("content"), str)
                or message.get("tool_calls") not in (None, [])):
            raise ModelResponseError("model service returned an incomplete or unexpected chat response")
        raw = message["content"]
        try:
            if len(raw.encode("utf-8")) > MAX_OUTPUT_BYTES:
                raise ValueError
        except (ValueError, UnicodeError):
            raise ModelResponseError("model output exceeds the size limit or has invalid Unicode") from None
        usage = {key: result[key] for key in USAGE_FIELDS if key in result}
        if any(type(value) is not int or value < 0 for value in usage.values()):
            raise ModelResponseError("model service returned invalid usage metadata")
        self.last_result = {"model": self.model, "model_digest": self.expected_digest,
                            "prompt_version": PROMPT_VERSION, "prompt_sha256": prompt_hash(messages),
                            "transcript_sha256": source_sha256, "options": dict(OPTIONS),
                            "raw_output": raw, "usage": usage, "keep_alive": 0}
        return raw  # No JSON repair: malformed model content belongs to check_output.
