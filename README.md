# Intake to draft

A local Python service turns an invented family law intake into a reviewed fictional petition draft through LangGraph, using local inference or recorded model output.
A reviewer accepts, corrects, or rejects each field, and every filled value retains transcript citations and earlier statements.
A separate approval releases the draft, with reviewer identities and decisions saved in local SQLite.

All examples and requirements belong to the **Republic of Alderhaven — Fictional Demonstration Jurisdiction**, which does not exist. Nothing in the notes represents the law of a real place. They are not court requirements, legal forms, or legal advice. Portfolio project for Preston Neal.

## Run

Prerequisites: Python 3.12 and internet access to install the pinned Python packages. The recorded demo needs no account, API key, model download, or Docker service. macOS and Linux are supported by the demonstration script.

From a clean checkout:

```sh
./scripts/demo
```

The command creates `.venv`, installs `requirements.lock`, forces tracing off, starts a temporary server and review database on an available loopback port, runs the demonstration, and removes the temporary server/database afterward. Set `PYTHON=/path/to/python3.12` if that interpreter is not on your PATH.

To keep the service running:

```sh
./scripts/serve
```

Open [the local API documentation](http://127.0.0.1:8000/docs). The service binds to `127.0.0.1` and stores review checkpoints in `.runtime/review.sqlite`. Set `INTAKE_REVIEW_DB` to choose another local path. It has no authentication or production deployment configuration; reviewer identities are self-declared, and the database owner can edit the audit records.

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Identifies the demonstration and current implementation stage. |
| `POST /intakes/validate` | Accepts `{"transcript": "..."}`; returns canonical text, SHA-256, and one-based numbered lines. |
| `POST /references/search` | Returns candidate fictional notes using the explicitly labeled keyword baseline; no model is loaded. |
| `GET /demo/extraction` | Replays extraction only; returns the original checked proposals and citation history. |
| `POST /demo/runs` | Starts the recorded name-change workflow and pauses for review. |
| `POST /runs` | Accepts `{"transcript":"...","query":"..."}`; retrieves local embedding candidates, calls the pinned local model, and pauses for review. |
| `GET /runs/{run_id}` | Returns the entire numbered source, immutable extraction report, review queue, audit, and approval. |
| `POST /runs/{run_id}/review` | Applies a named accept/correct/reject decision or a separate final approval at the expected revision. |
| `GET /runs/{run_id}/draft` | Returns the fictional petition, provenance table, and approver; returns 409 before approval. |

## Demo script

`./scripts/demo` makes real HTTP requests to validate and number `examples/intake.json`, retrieve the fictional name-change note, and replay extraction. It then performs explicitly **scripted** reviewer actions: accepts the corrected birth date, rejects the address, proves approval is blocked, corrects the address using lines 5 and 6, and approves the completed draft. It prints the source, citation history, review audit, draft, and filled-value provenance table. A second run must produce identical draft text and provenance. Success ends with `PASS: human review gate, cited fictional draft, persistent audit, and repeatability.`

The scripted reviewers are demonstration actors, not a claim that a person inspected the draft. A person uses the same review endpoint through the local API documentation.

## Local model and tracing

The live path requires Ollama running at `http://127.0.0.1:11434` with the already installed `qwen3-coder:latest` digest `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca`. The adapter verifies that digest before each extraction; it does not pull a model or substitute another model. `INTAKE_OLLAMA_URL` may select another loopback origin. The installed weights occupy about 18.6 GB; allow memory for inference alongside Docker. Requests use `keep_alive: 0` to release model memory afterward; subsequent runs pay the reload cost. A fresh Ollama installation can fetch the public model with `ollama pull qwen3-coder:latest`; if that tag changes, the digest check refuses it. No hosted adapter is included.

```sh
./scripts/live-demo
# Optional: also start and verify self-hosted tracing.
./scripts/live-demo --trace
```

The wrapper installs the pinned optional retrieval packages and downloads public, hash-checked MiniLM files when absent. It uses the same invented name-change transcript and scripted reviewer/approver identities, checks proposed values against that example's expected values, and saves evidence to `.runtime/live-demo.json`. Review pauses and approvals persist in `.runtime/live-review.sqlite`. Run responses identify `mode: "local"` or `mode: "recorded"`; both use the same review and approval endpoints. This is a development smoke test, not the held-out evaluation; see [its recorded evidence](eval/live_smoke_report.json) and [trace reading guide](eval/trace_example.md).

Live retrieval saves three candidates but tentatively uses the first note to choose required fields. Read the selected `note` and candidates before accepting any field. The broad labeled query q24 ranked a former-name note first even though the intended general note was in the top three; the live demo uses the existing, more specific q27 query for a personally chosen name. The benchmark labels are unchanged. If the selected note is wrong, start a new run with a better query; the review API cannot change a run's note.

Tracing uses Langfuse Python SDK **5.2.0** and self-hosted server **4.82.0**. Docker and either `docker compose` or `docker-compose` are required only for the stack:

```sh
./scripts/langfuse up
INTAKE_TRACING=langfuse ./scripts/serve
# After inspection:
./scripts/langfuse down
```

`up` generates a **local demo login**, organization, project, and API credentials automatically. There is no external signup, cloud account, license, or external key. Open [local Langfuse](http://127.0.0.1:13000/project/intake-demo/traces) and use `LANGFUSE_LOGIN_EMAIL` and `LANGFUSE_LOGIN_PASSWORD` from `.runtime/langfuse.env`. The SDK reads `.runtime/langfuse-client.json`; `INTAKE_LANGFUSE_CONFIG` can select another file, whose URL must remain loopback. Both generated credential files are ignored by Git and mode `0600`.

The six container images are pinned by digest. Only web port `127.0.0.1:13000` is published; the databases remain internal, and telemetry and public signup are disabled. `./scripts/langfuse status` reports this checkout's stack; `down` preserves its data volumes. Allow time and disk space for the first image downloads; this is a local demonstration, not production infrastructure.

With tracing enabled, each executed graph node records its input, output, and duration under the run's trace ID, including review pauses and resumes. `--trace` reads the observations back and checks for retrieve, extract, check, route, review, and fill. Export is best effort: an outage or process crash can leave missing observations, and export warnings do not repeat a node or change a review decision. LangSmith export is disabled. `INTAKE_TRACING=off` is the default; explicitly enabled tracing fails clearly for missing/invalid local configuration, conflicting SDK disable flags, or inherited OTLP credential headers. Implicit media uploads are disabled; transcript URI strings remain text. Each request waits at most two seconds for its flush, apart from scheduling overhead.

## Manual review

1. In `/docs`, execute `POST /demo/runs`, or `POST /runs` with your invented transcript and reference query after preparing the live dependencies; copy the returned `run_id`. Check the selected fictional `note` first. Read `source.lines`, every `review_queue` entry, and the earlier assertions. All fields require review because quotation matching cannot establish meaning or completeness.
2. Submit field decisions to `POST /runs/{run_id}/review`, using the current `revision` as `expected_revision`. For example, the first birth-date decision can be:

```json
{"action":"accept","reviewer":"Example Reviewer","expected_revision":0,"field":"birth_date"}
```

`accept` selects the stored model proposal, including the later corrected date; it cannot supply a replacement value. `reject` requires a reason and blocks that field. A correction must quote this transcript, for example:

```json
{"action":"correct","reviewer":"Example Reviewer","expected_revision":1,"field":"petitioner_address","value":"18 Example Lane Sampletown","citations":[{"line":5,"quote":"18 Example Lane"},{"line":6,"quote":"Sampletown"}],"reason":"Confirmed both address fragments."}
```

3. Accept or correct every remaining field and emitted child subject. Reload the run after each action and use its new revision; stale submissions return 409. A genuinely absent fact cannot be supplied without transcript evidence. Reject it and obtain a revised intake; adding new source material to an existing run is not supported. An omitted child whose evidence is already present can be added by a cited `correct` action with a new `child-N` subject.
4. Read the entire transcript again for omissions and misattribution, then submit `action: "approve"`, your reviewer name, the current `expected_revision`, and `confirmed_complete: true`, with no field or value. Field acceptance alone does not release a draft. `GET /runs/{run_id}/draft` now returns the petition and its provenance table, including earlier model assertions. Approved runs are sealed; start a new run to revise one.

Each accepted decision records its server-assigned revision and UTC time, reviewer, action, reason, and before/after value. Rejected field decisions are recorded too; invalid or stale API submissions do not become review events. Approval records the transcript and draft hashes. Restarting the service preserves paused reviews and completed drafts; this is a persistent local audit, not a tamper-proof log.


Source lines preserve indentation, tabs, trailing spaces, and interior blank lines. CRLF and CR become LF; one terminal newline is a terminator rather than another source line. Limits apply to the canonical text: 65,536 UTF-8 bytes, 500 lines, and 2,000 characters per line. Unsupported controls and invalid Unicode surrogates are rejected. Validation errors omit the submitted transcript.

## Tests and measurements

One command runs the tests:

```sh
./scripts/test
```

The suite covers the HTTP contract, source-line preservation, deterministic retrieval, and adversarial extraction, plus review/draft gates: uncited corrections, missing facts, unresolved siblings, reviewer attribution, stale and competing submissions, restart/resume, interrupted filling, and template injection. It also checks local model identity, malformed responses, dependency failures, tracing failures, and resume without repeating inference. It checks all four fictional petition-type headings and byte-identical draft text for repeated source and review choices. CI runs that command and the HTTP demo on Python 3.12.

| Retrieval method | Right note in top three | Local model / index |
| --- | --- | --- |
| Embeddings | 28/30 (93.3%) | `sentence-transformers/all-MiniLM-L6-v2`; in-memory exact cosine over 384-dimensional normalized vectors. |
| Plain keyword search | 20/30 (66.7%) | Unique keyword overlap after removing listed function words; ties by note ID. |

There are 40 fictional notes, ten per petition type, and 30 labeled paraphrased queries. Notes and labels were fixed before scoring; [the report](eval/retrieval_report.json) includes per-query ranks, hashes, model revision, and package versions. Embeddings performed better on this small authored set; this does not establish general intake quality. These 30 retrieval queries are separate from the planned 30 held-out extraction cases. The reference-search endpoint uses the keyword baseline; live runs use the local embedding index. A top-three retrieval score does not measure automatic first-choice accuracy.

To reproduce the embedding comparison, after running the demo:

```sh
.venv/bin/python -m pip install --no-build-isolation '.[retrieval]'
.venv/bin/python scripts/evaluate_retrieval.py --download
```

The download fetches public, hash-checked files at model revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Encoding runs locally on CPU using ONNX Runtime 1.32.0, tokenizers 0.23.3, and NumPy 2.5.5. Rerun without `--download` using the cached files to work offline. No account or inference key is needed.

The successful recording is from local `qwen3-coder:latest`, digest `06c1097efce0431c2045fe7b2e5108366e43bee1b4603a7aded8f21689e90bca`; its raw output, prompt/source hashes, options, and returned usage are preserved. An actual malformed Llama 3.2 response is retained as a failure fixture. Tests replay these outputs without loading either model. This is not an extraction accuracy evaluation: field accuracy, citation accuracy, missing-fact review routing, and escaped-guess rates remain **unmeasured** until the held-out cases exist.

## Citation limits

A value can cite multiple lines. Citations must quote existing source text in order, including within a line; the value's words must appear in order across those quotations, allowing punctuation changes. The checker chooses the latest *emitted* assertion by source position and retains earlier ones. Same-line contradictions, overlapping evidence for different values, and a latest uncertain statement have no selected proposal. `missing` lists required fields that are absent or have any emitted subject without a usable proposal; one resolved child cannot hide an unresolved sibling. Field histories and issues distinguish absent, unsupported, conflicting, and uncertain evidence. Malformed schemas are rejected without repairing or guessing facts.

Location checks do not prove meaning or completeness. A model can quote a negated value or omit a later correction. The extraction report therefore remains an immutable unapproved proposal record. The review workflow exposes the entire source, requires a cited accept/correct decision for every field and emitted subject, and checks citations again at fill. A separate named approval confirms completeness; it does not turn human judgment into a measured accuracy guarantee. Caller text is placed only in the untrusted user-data message; it cannot supply tools, prompt rules, or approval actions.

## Not done

Arbitrary invented transcripts can start through the live API, but only one development intake has a live smoke demonstration. Supplemental intake evidence, authenticated identity, hosted inference, and production operation are not implemented. PR 4 adds forty transcripts written from exact fact sheets, with ten development cases and thirty held-out cases, including caller prompt injection and draft-approver records. Only the thirty held-out cases will determine the four reported model metrics.

The same saved transcript, selected note, and reviewed values produce byte-identical petition text. Live extraction uses seed 17 and temperature 0, but repeated inference can vary across hardware or runtimes; identical live drafts are not guaranteed. Different human choices can also change the draft; reviewer changes affect provenance, and run IDs, audit times, and approval metadata intentionally differ outside the text.

With two more days, the next work is fact-sheet-derived development cases, freezing the thirty-case holdout, and a scoring harness for the four model metrics. See [DECISIONS.md](DECISIONS.md) for the choices and split.
