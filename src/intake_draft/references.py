"""Small, deterministic TF-IDF index over invented demonstration notes.

This is lexical vector retrieval, not a semantic embedding model. A match is a
candidate checklist for the demo; similarity does not establish legal needs.
"""

from collections import Counter
from importlib.resources import files
import json
from math import log, sqrt
import re


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _normalize(vector: dict[str, float]) -> dict[str, float]:
    length = sqrt(sum(weight * weight for weight in vector.values()))
    return {token: weight / length for token, weight in vector.items()} if length else {}


class ReferenceIndex:
    """An in-memory cosine index; four documents do not need a database."""

    def __init__(self) -> None:
        resource = files("intake_draft").joinpath("data/reference_notes.json")
        self._notes = json.loads(resource.read_text(encoding="utf-8"))
        counts = [Counter(_tokens(note["title"] + " " + note["body"])) for note in self._notes]
        document_frequency = Counter(token for count in counts for token in count)
        self._idf = {
            token: log((1 + len(counts)) / (1 + frequency)) + 1
            for token, frequency in document_frequency.items()
        }
        self._vectors = [self._vector(count) for count in counts]

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        # Sublinear term frequency prevents repeated words dominating a query.
        return _normalize({
            token: (1 + log(count)) * self._idf[token]
            for token, count in counts.items()
            if token in self._idf
        })

    def search(self, query: str, limit: int = 3) -> list[dict]:
        """Return positive-score candidates, sorted by cosine score then ID.

        Blank input is an error. An out-of-vocabulary query has no candidates.
        Returned field lists are copies of stored requirements, never generated.
        """
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if type(limit) is not int or not 1 <= limit <= len(self._notes):
            raise ValueError(f"limit must be an integer from 1 to {len(self._notes)}")
        query_vector = self._vector(Counter(_tokens(query)))
        matches = []
        for note, vector in zip(self._notes, self._vectors):
            score = sum(weight * vector.get(token, 0.0) for token, weight in query_vector.items())
            if score > 0:
                matches.append({
                    **note,
                    "required_fields": list(note["required_fields"]),
                    "score": score,
                })
        return sorted(matches, key=lambda match: (-match["score"], match["id"]))[:limit]
