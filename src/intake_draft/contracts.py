"""Preserve source positions before any model sees an intake."""

import hashlib
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_BYTES = 65_536
MAX_LINES = 500
MAX_LINE_CHARS = 2_000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TranscriptRequest(StrictModel):
    transcript: str

    @field_validator("transcript")
    @classmethod
    def canonicalize(cls, value: str) -> str:
        # Normalize line endings only. Preserve indentation and interior blanks.
        text = value.replace("\r\n", "\n").replace("\r", "\n")
        if text.endswith("\n"):
            text = text[:-1]  # A final newline terminates the last source line.
        if not text.strip():
            raise ValueError("transcript must contain non-whitespace text")
        if any(
            unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\t"
            for char in text
        ):
            raise ValueError("transcript contains an unsupported control or surrogate character")
        if len(text.encode("utf-8")) > MAX_BYTES:
            raise ValueError(f"transcript exceeds {MAX_BYTES} UTF-8 bytes")
        lines = text.split("\n")
        if len(lines) > MAX_LINES:
            raise ValueError(f"transcript exceeds {MAX_LINES} lines")
        if any(len(line) > MAX_LINE_CHARS for line in lines):
            raise ValueError(f"a transcript line exceeds {MAX_LINE_CHARS} characters")
        return text


class SourceLine(StrictModel):
    number: int
    text: str


class NumberedTranscript(StrictModel):
    transcript: str
    sha256: str
    lines: list[SourceLine]


def number_transcript(request: TranscriptRequest) -> NumberedTranscript:
    text = request.transcript
    return NumberedTranscript(
        transcript=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        lines=[SourceLine(number=i, text=line) for i, line in enumerate(text.split("\n"), 1)],
    )


class SearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=1_000)
    limit: int = Field(default=3, ge=1, le=40)

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
            raise ValueError("query contains an unsupported control or surrogate character")
        return value
