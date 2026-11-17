"""Source fidelity and input boundaries for later citation checking."""

import pytest
from pydantic import ValidationError

from intake_draft.contracts import TranscriptRequest, number_transcript


def numbered(text: str):
    return number_transcript(TranscriptRequest(transcript=text))


def test_line_endings_produce_the_same_canonical_source_and_digest():
    lf = "Caller: My name is Robin Vale.\nCaller: I want to discuss a name change.\n"
    expected = numbered(lf)

    assert numbered(lf.replace("\n", "\r\n")) == expected
    assert numbered(lf.replace("\n", "\r")) == expected
    assert numbered(lf.removesuffix("\n")) == expected
    assert numbered(lf.replace("Robin Vale", "Robin Vail")).sha256 != expected.sha256


def test_blank_lines_and_whitespace_keep_their_original_source_positions():
    result = numbered("\n  Caller:\tMy name is Élodie Vale.  \n\nCaller: Thank you.\n\n")

    assert [(line.number, line.text) for line in result.lines] == [
        (1, ""),
        (2, "  Caller:\tMy name is Élodie Vale.  "),
        (3, ""),
        (4, "Caller: Thank you."),
        (5, ""),
    ]
    assert "\n".join(line.text for line in result.lines) == result.transcript
    assert type(result).model_validate_json(result.model_dump_json()) == result


def test_one_terminal_newline_does_not_add_a_phantom_source_line():
    assert numbered("Caller: Hello.\n") == numbered("Caller: Hello.")
    assert len(numbered("Caller: Hello.\n\n").lines) == 2


@pytest.mark.parametrize("value", ["", " \t\n\r\n", None, 42, True, ["Caller: Hello."]])
def test_transcript_requires_nonblank_text_without_type_coercion(value):
    with pytest.raises(ValidationError):
        TranscriptRequest(transcript=value)


def test_unknown_input_fields_are_rejected():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TranscriptRequest(transcript="Caller: Hello.", approved=True)


def test_utf8_byte_limit_is_independent_of_character_count():
    prefix = "\n".join(["é" * 1_000] * 32) + "\n"
    at_limit = prefix + "x" * (65_536 - len(prefix.encode("utf-8")))

    assert len(at_limit) < 65_536
    assert len(at_limit.encode("utf-8")) == 65_536
    assert TranscriptRequest(transcript=at_limit).transcript == at_limit
    with pytest.raises(ValidationError, match="UTF-8 bytes"):
        TranscriptRequest(transcript=at_limit + "x")


def test_line_count_limit_preserves_blank_source_lines():
    at_limit = "Caller: Hello." + "\n" * 500
    assert len(numbered(at_limit).lines) == 500
    with pytest.raises(ValidationError, match="500 lines"):
        TranscriptRequest(transcript=at_limit + "\n")


def test_line_character_limit_counts_unicode_characters():
    at_limit = "é" * 2_000
    assert TranscriptRequest(transcript=at_limit).transcript == at_limit
    with pytest.raises(ValidationError, match="2000 characters"):
        TranscriptRequest(transcript=at_limit + "é")
