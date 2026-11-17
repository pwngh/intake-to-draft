"""Compare local MiniLM exact-cosine retrieval with plain keyword overlap.

Optional dependencies: onnxruntime==1.32.0, tokenizers==0.23.3, numpy==2.5.5.
No inference request leaves the machine. --download fetches public model files.
"""

import argparse
import hashlib
from importlib.metadata import version
from importlib.resources import files
import json
from pathlib import Path
import urllib.request

from intake_draft.references import (
    EMBEDDING_INDEX, EMBEDDING_MODEL, EMBEDDING_REVISION,
    EmbeddingIndex, KeywordIndex, LocalMiniLM, STOPWORDS,
)

ROOT = Path(__file__).resolve().parent.parent
MODEL_FILES = {
    "model.onnx": ("onnx/model.onnx", "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"),
    "tokenizer.json": ("tokenizer.json", "be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(queries: list[dict], index) -> dict:
    results = []
    for item in queries:
        retrieved = [note["id"] for note in index.search(item["query"], limit=3)]
        results.append({"id": item["id"], "relevant_note_ids": item["relevant_note_ids"], "retrieved": retrieved,
                        "hit": bool(set(retrieved) & set(item["relevant_note_ids"]))})
    hits = sum(item["hit"] for item in results)
    return {"hits": hits, "queries": len(results), "top3_hit_rate": hits / len(results), "results": results}


def write_report(report: dict, path: Path) -> None:
    # Keep each query result on one line so reviewers can compare ranks and labels.
    lines = ["{"]
    for key, value in report.items():
        if key not in {"embedding", "keyword"}:
            lines.append(f"  {json.dumps(key)}: {json.dumps(value)},")
        else:
            summary = {k: v for k, v in value.items() if k != "results"}
            lines.append(f"  {json.dumps(key)}: " + json.dumps(summary)[:-1] + ', "results": [')
            lines.extend("    " + json.dumps(row) + ("," if i < len(value["results"]) - 1 else "")
                         for i, row in enumerate(value["results"]))
            lines.append("  ]},")
    lines[-1] = lines[-1].removesuffix(",")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines + ["}", ""]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=ROOT / ".runtime/minilm")
    parser.add_argument("--queries", type=Path, default=ROOT / "tests/data/retrieval_queries.json")
    parser.add_argument("--output", type=Path, default=ROOT / "eval/retrieval_report.json")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    for local_name, (remote_name, expected) in MODEL_FILES.items():
        path = args.model_dir / local_name
        if not path.exists() and args.download:
            args.model_dir.mkdir(parents=True, exist_ok=True)
            url = f"https://huggingface.co/{EMBEDDING_MODEL}/resolve/{EMBEDDING_REVISION}/{remote_name}"
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
        if not path.exists():
            parser.error(f"missing {path}; run once with --download to fetch the pinned public model")
        if expected and sha256(path) != expected:
            parser.error(f"model file hash mismatch: {path}")
    note_bytes = files("intake_draft").joinpath("data/reference_notes.json").read_bytes()
    notes = json.loads(note_bytes)
    queries = json.loads(args.queries.read_text())
    known = {note["id"] for note in notes}
    if len(queries) != 30 or any(not set(q["relevant_note_ids"]) <= known for q in queries):
        parser.error("expected 30 queries with labels drawn from the note IDs")
    report = {
        "metric": "fraction of labeled queries with at least one relevant note in top three",
        "corpus_count": len(notes), "notes_sha256": hashlib.sha256(note_bytes).hexdigest(),
        "queries_sha256": sha256(args.queries),
        "embedding_model": EMBEDDING_MODEL, "embedding_revision": EMBEDDING_REVISION,
        "embedding_index": EMBEDDING_INDEX, "keyword_method": "unique keyword overlap minus listed function words; ties by note ID",
        "keyword_stopwords": sorted(STOPWORDS),
        "model_files_sha256": {name: sha256(args.model_dir / name) for name in MODEL_FILES},
        "packages": {name: version(name) for name in ("onnxruntime", "tokenizers", "numpy")},
        "embedding": evaluate(queries, EmbeddingIndex(LocalMiniLM(args.model_dir), notes)),
        "keyword": evaluate(queries, KeywordIndex(notes)),
    }
    write_report(report, args.output)
    for method in ("embedding", "keyword"):
        result = report[method]
        print(f"{method}: {result['hits']}/{result['queries']} = {result['top3_hit_rate']:.1%} top-three hit rate")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
