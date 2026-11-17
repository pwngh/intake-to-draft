# Intake to draft

A local Python service prepares invented family law intake transcripts for a demonstration drafting workflow.
It preserves numbered source lines and searches four invented requirement notes using TF-IDF vectors and cosine similarity.
This is the first runnable piece: extraction, human review, petition drafts, and model traces are not implemented yet.

All example names, addresses, transcripts, and requirements were written for this project. They are not court requirements, legal forms, or legal advice. Portfolio project for Preston Neal.

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
| `POST /references/search` | Accepts `{"query": "adult name change", "limit": 1}`; returns candidate notes and their stored field lists. |

## Demo script

`./scripts/demo` makes real HTTP requests to validate `examples/intake.json`, repeats the request and compares the complete responses, retrieves the adult name change note, and verifies that blank input is rejected. It prints the numbered source lines, transcript digest, and candidate field list. Success ends with `PASS: HTTP validation, reference retrieval, and repeatability.`

Source lines preserve indentation, tabs, trailing spaces, and interior blank lines. CRLF and CR become LF; one terminal newline is a terminator rather than another source line. Limits apply to the canonical text: 65,536 UTF-8 bytes, 500 lines, and 2,000 characters per line. Unsupported controls and invalid Unicode surrogates are rejected. Validation errors omit the submitted transcript.

## Tests and measurements

One command runs the tests:

```sh
./scripts/test
```

The suite covers the HTTP contract, strict input validation and size limits, line preservation and repeatability, four reference searches, deterministic ranking, unknown vocabulary, and stored-field provenance. CI runs that command and the HTTP demo on Python 3.12.

| Measurement | Observed result | Scope |
| --- | --- | --- |
| Reference retrieval top result | 4 / 4 | Four explicit archetype queries in `tests/test_references.py`; a smoke check, not an evaluation of general intake understanding. |
| Repeated demo intake | Identical text, lines, and SHA-256 | Two HTTP requests in `scripts/demo.py`. |
| Unknown-vocabulary retrieval | No matches | Tested query: `quasar xylophone zeppelin`. |

No model has run on an intake yet. Field accuracy, citation accuracy, missing-fact review routing, and escaped-guess rates are **not measured**. The planned forty-case evaluation must report those four rates with denominators for each model; this PR makes no extraction-quality claim.

## Not done

LangGraph extraction and validation, persistent field-by-field human review with reviewer attribution, draft rendering with source mappings, the forty-case dataset, local model inference, and self-hosted Langfuse are the next pieces. No draft is produced by this version. Requirements returned by retrieval are candidate invented checklists; the service does not automatically decide a petition type.

TF-IDF uses shared words, not semantic embeddings. It does not understand negation or distinguish uncertain facts from corrections. There is no evidence yet for accuracy on free-form intake transcripts or for end-to-end draft reproducibility.

With two more days, the next work would be the checkpointed LangGraph review path and a local-model extraction evaluation, beginning with corrected dates, missing addresses, uncertain facts, and children with similar names. See [DECISIONS.md](DECISIONS.md) for the PR sequence and documentation sources.
