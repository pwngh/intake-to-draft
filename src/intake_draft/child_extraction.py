"""Versioned child prompting; the frozen v2 checker and model adapter stay intact."""

import json

from intake_draft.extraction import PROMPT_VERSION, prompt_hash
from intake_draft.local_model import LocalModel

CHILD_PROMPT_VERSION = "extract-children-v1"
CHILD_INSTRUCTIONS = """
For the requested children field, a fact describes ONE CHILD, not one attribute.
Emit exactly one fact per distinct child, with field children and subject child-1,
child-2, etc. in first-mention order. Never use subject case for children. Never
split a child's name and birth date into separate facts or separate assertions.
Each assertion value must include that child's name AND stated birth details,
copied together from the source (including the word born when present). Cite all
fragments if they span lines. Keep similarly named siblings separate.
Keep corrections for the SAME child inside that fact's assertions array, retaining
the earlier complete value and the later complete corrected value. Keep the same
subject ID. If birth details are missing or uncertain, retain only supported text
as an uncertain assertion; do not invent details or present a name alone as a
complete confirmed child record. Omit children when not requested. Never invent
child_1 fields, empty values, or no-children placeholders.
Synthetic example, NOT the supplied intake:
1: Ari Wisp born 2010-03-04.
2: Arin Wisp born 2012-05-06.
3: Correction: Ari Wisp born 2010-03-14.
Children facts for that example:
{"facts":[{"field":"children","subject":"child-1","assertions":[{"value":"Ari Wisp born 2010-03-04","kind":"stated","citations":[{"line":1,"quote":"Ari Wisp born 2010-03-04"}]},{"value":"Ari Wisp born 2010-03-14","kind":"correction","citations":[{"line":3,"quote":"Ari Wisp born 2010-03-14"}]}]},{"field":"children","subject":"child-2","assertions":[{"value":"Arin Wisp born 2012-05-06","kind":"stated","citations":[{"line":2,"quote":"Arin Wisp born 2012-05-06"}]}]}]}
Extract the actual supplied intake, not this example. Preserve the other requested
fields under the original rules. Return one fact per (field, subject), with all
that fact's assertions grouped together. No tools, review decisions, or approvals.
""".strip()


def child_messages(messages: list[dict]) -> list[dict]:
    """Select by trusted required fields, never by words in the transcript."""
    required = json.loads(messages[1]["content"])["required_fields"]
    if "children" not in required:
        return messages
    return [{**messages[0], "content": messages[0]["content"] + "\n\n" + CHILD_INSTRUCTIONS},
            *messages[1:]]


class ChildLocalModel(LocalModel):
    def __call__(self, messages: list[dict], source_sha256: str) -> str:
        prepared = child_messages(messages)
        raw = super().__call__(prepared, source_sha256)
        if prepared is not messages:
            self.last_result["prompt_version"] = CHILD_PROMPT_VERSION
        return raw  # The same strict checker receives the exact response, without repair.


class RecordedChildModel:
    """Explicit offline replay of the versioned prompt; never an inference fallback."""

    def __init__(self, record: dict):
        self.record = record
        self.last_result = {}

    def __call__(self, messages: list[dict], source_sha256: str) -> str:
        self.last_result = {}
        prepared = child_messages(messages)
        version = CHILD_PROMPT_VERSION if prepared is not messages else PROMPT_VERSION
        if (self.record["prompt_version"] != version
                or self.record["prompt_sha256"] != prompt_hash(prepared)
                or self.record["transcript_sha256"] != source_sha256):
            raise ValueError("recording does not match this child prompt and transcript")
        self.last_result = dict(self.record)
        return self.record["raw_output"]
