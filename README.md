# Intake to draft

A local Python service replays model extraction from invented family law intakes through a LangGraph extract-and-check graph.
Each proposed value carries quoted source lines and an assertion history that retains earlier statements when a caller makes a correction.
This slice stops at proposals requiring human verification; review actions and draft filling follow in the split core-workflow PR.

All examples and requirements belong to the **Republic of Alderhaven — Fictional Demonstration Jurisdiction**, which does not exist. Nothing in the notes represents the law of a real place. They are not court requirements, legal forms, or legal advice. Portfolio project for Preston Neal.

## Run

Prerequisites: Python 3.12 and internet access to install the pinned Python packages. No account, API key, model download, or Docker service is needed for this slice. macOS and Linux are supported by the demonstration script.

From a clean checkout:

```sh
./scripts/demo
```

The command creates `.venv`, installs `requirements.lock`, starts a temporary server on an available loopback port, runs the demonstration, and stops the server. Set `PYTHON=/path/to/python3.12` if that interpreter is not on your PATH.

To keep the service running:

```sh
./scripts/serve
```

Open [the local API documentation](http://127.0.0.1:8000/docs). The service binds to `127.0.0.1`; it has no authentication, persistence, or production deployment configuration.

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Identifies the demonstration and current implementation stage. |
| `POST /intakes/validate` | Accepts `{"transcript": "..."}`; returns canonical text, SHA-256, and one-based numbered lines. |
| `POST /references/search` | Returns candidate fictional notes using the explicitly labeled keyword baseline; no model is loaded. |
| `GET /demo/extraction` | Replays the captured local-model response through LangGraph; returns checked proposals and a provenance table, never a draft. |

## Demo script

`./scripts/demo` makes real HTTP requests to validate `examples/intake.json`, repeats the request and compares the complete responses, retrieves the adult name change note, and verifies that blank input is rejected. It prints the numbered source lines, transcript digest, and candidate field list. It then replays the extraction twice, verifies the corrected birth date and the two-line address, and prints the provenance table including the earlier birth date. Success ends with `PASS: recorded LangGraph extraction, citation history, and repeatability.`

Source lines preserve indentation, tabs, trailing spaces, and interior blank lines. CRLF and CR become LF; one terminal newline is a terminator rather than another source line. Limits apply to the canonical text: 65,536 UTF-8 bytes, 500 lines, and 2,000 characters per line. Unsupported controls and invalid Unicode surrogates are rejected. Validation errors omit the submitted transcript.

## Tests and measurements

One command runs the tests:

```sh
./scripts/test
```

The suite covers the HTTP contract, source-line preservation, deterministic retrieval, and adversarial extraction: missing or fabricated citations, malformed output, unsupported values, corrections, similar child subjects, caller instructions, and mismatched recordings. CI runs that command and the HTTP demo on Python 3.12.

| Retrieval method | Right note in top three | Local model / index |
| --- | --- | --- |
| Embeddings | 28/30 (93.3%) | `sentence-transformers/all-MiniLM-L6-v2`; in-memory exact cosine over 384-dimensional normalized vectors. |
| Plain keyword search | 20/30 (66.7%) | Unique keyword overlap after removing listed function words; ties by note ID. |

There are 40 fictional notes, ten per petition type, and 30 labeled paraphrased queries. Notes and labels were fixed before scoring; [the report](eval/retrieval_report.json) includes per-query ranks, hashes, model revision, and package versions. Embeddings performed better on this small authored set; this does not establish general intake quality. These 30 retrieval queries are separate from the planned 30 held-out extraction cases. The default recorded-output service uses the keyword baseline; live embedding use comes with the local adapters.

To reproduce the embedding comparison, after running the demo:

```sh
.venv/bin/python -m pip install --no-build-isolation '.[retrieval]'
.venv/bin/python scripts/evaluate_retrieval.py --download
```

The download fetches public, hash-checked files at model revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Encoding runs locally on CPU using ONNX Runtime 1.32.0, tokenizers 0.23.3, and NumPy 2.5.5. Rerun without `--download` using the cached files to work offline. No account or inference key is needed.

The successful recording is from local `qwen3-coder:latest`, digest `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca`; its raw output, prompt/source hashes, options, and returned usage are preserved. An actual malformed Llama 3.2 response is retained as a failure fixture. Tests replay these outputs without loading either model. This is not an extraction accuracy evaluation: field accuracy, citation accuracy, missing-fact review routing, and escaped-guess rates remain **unmeasured** until the held-out cases exist.

## Citation limits

A value can cite multiple lines. Citations must quote existing source text; the value's words must appear in order across those quotations, allowing punctuation changes. The checker chooses the latest *emitted* assertion by source position and retains earlier ones; same-line contradictions have no selected proposal. Missing fields remain missing, and malformed schemas are rejected without repairing or guessing facts.

Location checks do not prove meaning or completeness. A model can quote a negated value or omit a later correction. Every proposal therefore remains `needs_review`, with `approved: false`; there is no draft path in this slice. The next review step must expose the entire source and require human verification before any value reaches a draft. Caller text is placed only in the untrusted user-data message; it cannot supply tools, prompt rules, or approval actions.

## Not done

Persistent accept/correct/reject actions, reviewer attribution, the fictional petition template, and draft filling are next in PR 2b. PR 3 adds live local-model adapters and optional self-hosted Langfuse; the demo must still pass with tracing off. PR 4 adds forty transcripts written from exact fact sheets, with ten development cases and thirty held-out cases, including caller prompt injection and draft-approver records. Only the thirty held-out cases will determine the four reported model metrics.

With two more days, the next work is the persistent review gate and fill step, tested against the attack questions used for Council. No draft is produced yet. See [DECISIONS.md](DECISIONS.md) for the choices and split.
