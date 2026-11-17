"""Local reference retrieval; matches are fictional demonstration checklists."""

from importlib.resources import files
import json
import re


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _load_notes() -> list[dict]:
    return json.loads(files("intake_draft").joinpath("data/reference_notes.json").read_text(encoding="utf-8"))


# The semantic experiment is optional: ordinary service tests do not load it.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
EMBEDDING_INDEX = "in-memory exact cosine (L2-normalized 384-dimensional vectors)"


STOPWORDS = set("a an and are as at be been but by for from had has have i in is it its me my "
                "of on or our that the their them they this to was we were what when where which "
                "who will with would you your".split())


class KeywordIndex:
    """Unique keyword overlap, excluding function words; no weights or stemming."""

    def __init__(self, notes: list[dict] | None = None) -> None:
        self._notes = notes if notes is not None else _load_notes()
        self._terms = [set(_tokens(note["title"] + " " + note["body"])) - STOPWORDS for note in self._notes]

    def search(self, query: str, limit: int = 3) -> list[dict]:
        _validate_search(query, limit, len(self._notes))
        terms = set(_tokens(query)) - STOPWORDS
        scores = [len(terms & document) / max(1, len(terms)) for document in self._terms]
        return _rank(self._notes, scores, limit)


def _validate_search(query: str, limit: int, count: int) -> None:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if type(limit) is not int or not 1 <= limit <= count:
        raise ValueError(f"limit must be an integer from 1 to {count}")


def _rank(notes: list[dict], scores: list[float], limit: int) -> list[dict]:
    matches = [{**note, "required_fields": list(note["required_fields"]), "score": float(score)}
               for note, score in zip(notes, scores, strict=True) if score > 0]
    return sorted(matches, key=lambda match: (-match["score"], match["id"]))[:limit]


class LocalMiniLM:
    """CPU inference from pinned local ONNX/tokenizer files; never downloads."""

    def __init__(self, model_dir) -> None:
        from pathlib import Path
        import onnxruntime as ort
        from tokenizers import Tokenizer

        directory = Path(model_dir)
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(directory / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def encode(self, texts: list[str]) -> list[list[float]]:
        import numpy as np

        vectors = []
        for start in range(0, len(texts), 16):
            tokens = self.tokenizer.encode_batch(texts[start:start + 16])
            inputs = {
                "input_ids": np.array([item.ids for item in tokens], dtype=np.int64),
                "attention_mask": np.array([item.attention_mask for item in tokens], dtype=np.int64),
                "token_type_ids": np.array([item.type_ids for item in tokens], dtype=np.int64),
            }
            hidden = self.session.run(None, inputs)[0]
            mask = inputs["attention_mask"][..., None]
            pooled = (hidden * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1)
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12)
            vectors.extend(pooled.tolist())
        return vectors


class EmbeddingIndex:
    """Exhaustive cosine search; encoder injection keeps tests model-free."""

    def __init__(self, encoder, notes: list[dict] | None = None) -> None:
        self._notes = notes if notes is not None else _load_notes()
        self._encoder = encoder
        self._vectors = encoder.encode([note["title"] + " " + note["body"] for note in self._notes])

    def search(self, query: str, limit: int = 3) -> list[dict]:
        _validate_search(query, limit, len(self._notes))
        query_vector, = self._encoder.encode([query])
        scores = [sum(a * b for a, b in zip(query_vector, vector, strict=True))
                  for vector in self._vectors]
        return _rank(self._notes, scores, limit)


# The recorded-output demo stays model-free; PR3 will make live adapters explicit.
ReferenceIndex = KeywordIndex
