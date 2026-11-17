# Intake to draft

A local Python service turns a recorded extraction from an invented family law intake into a reviewed fictional petition draft through LangGraph.
A reviewer accepts, corrects, or rejects each field, and every filled value retains transcript citations and earlier statements.
A separate approval releases the draft, with reviewer identities and decisions saved in local SQLite.

All examples and requirements belong to the **Republic of Alderhaven — Fictional Demonstration Jurisdiction**, which does not exist. Nothing in the notes represents the law of a real place. They are not court requirements, legal forms, or legal advice. Portfolio project for Preston Neal.

## Run

Prerequisites: Python 3.12 and internet access to install the pinned Python packages. No account, API key, model download, or Docker service is needed for this slice. macOS and Linux are supported by the demonstration script.

From a clean checkout:

```sh
./scripts/demo
```

The command creates `.venv`, installs `requirements.lock`, starts a temporary server and review database on an available loopback port, runs the demonstration, and removes the temporary server/database afterward. Set `PYTHON=/path/to/python3.12` if that interpreter is not on your PATH.

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
| `GET /runs/{run_id}` | Returns the entire numbered source, immutable extraction report, review queue, audit, and approval. |
| `POST /runs/{run_id}/review` | Applies a named accept/correct/reject decision or a separate final approval at the expected revision. |
| `GET /runs/{run_id}/draft` | Returns the fictional petition, provenance table, and approver; returns 409 before approval. |

## Demo script

`./scripts/demo` makes real HTTP requests to validate and number `examples/intake.json`, retrieve the fictional name-change note, and replay extraction. It then performs explicitly **scripted** reviewer actions: accepts the corrected birth date, rejects the address, proves approval is blocked, corrects the address using lines 5 and 6, and approves the completed draft. It prints the source, citation history, review audit, draft, and filled-value provenance table. A second run must produce identical draft text and provenance. Success ends with `PASS: human review gate, cited fictional draft, persistent audit, and repeatability.`

The scripted reviewers are demonstration actors, not a claim that a person inspected the draft. A person uses the same review endpoint through the local API documentation.

## Manual review

1. In `/docs`, execute `POST /demo/runs`; copy the returned `run_id`. Read `source.lines`, every `review_queue` entry, and the earlier assertions. All fields require review because quotation matching cannot establish meaning or completeness.
2. Submit field decisions to `POST /runs/{run_id}/review`, using the current `revision` as `expected_revision`. For example, the first birth-date decision can be:

```json
{"action":"accept","reviewer":"Example Reviewer","expected_revision":0,"field":"birth_date"}
```

`accept` selects the stored model proposal, including the later corrected date; it cannot supply a replacement value. `reject` requires a reason and blocks that field. A correction must quote this transcript, for example:

```json
{"action":"correct","reviewer":"Example Reviewer","expected_revision":1,"field":"petitioner_address","value":"18 Example Lane Sampletown","citations":[{"line":5,"quote":"18 Example Lane"},{"line":6,"quote":"Sampletown"}],"reason":"Confirmed both address fragments."}
```

3. Accept or correct every remaining field and emitted child subject. Reload the run after each action and use its new revision; stale submissions return 409. A genuinely absent fact cannot be supplied without transcript evidence. Reject it and obtain a revised intake; adding new source material is outside this recorded slice. An omitted child whose evidence is already present can be added by a cited `correct` action with a new `child-N` subject.
4. Read the entire transcript again for omissions and misattribution, then submit `action: "approve"`, your reviewer name, the current `expected_revision`, and `confirmed_complete: true`, with no field or value. Field acceptance alone does not release a draft. `GET /runs/{run_id}/draft` now returns the petition and its provenance table, including earlier model assertions. Approved runs are sealed; start a new run to revise one.

Each accepted decision records its server-assigned revision and UTC time, reviewer, action, reason, and before/after value. Rejected field decisions are recorded too; invalid or stale API submissions do not become review events. Approval records the transcript and draft hashes. Restarting the service preserves paused reviews and completed drafts; this is a persistent local audit, not a tamper-proof log.


Source lines preserve indentation, tabs, trailing spaces, and interior blank lines. CRLF and CR become LF; one terminal newline is a terminator rather than another source line. Limits apply to the canonical text: 65,536 UTF-8 bytes, 500 lines, and 2,000 characters per line. Unsupported controls and invalid Unicode surrogates are rejected. Validation errors omit the submitted transcript.

## Tests and measurements

One command runs the tests:

```sh
./scripts/test
```

The suite covers the HTTP contract, source-line preservation, deterministic retrieval, and adversarial extraction, plus review/draft gates: uncited corrections, missing facts, unresolved siblings, reviewer attribution, stale and competing submissions, restart/resume, interrupted filling, and template injection. It checks all four fictional petition-type headings and byte-identical draft text for repeated source and review choices. CI runs that command and the HTTP demo on Python 3.12.

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

A value can cite multiple lines. Citations must quote existing source text in order, including within a line; the value's words must appear in order across those quotations, allowing punctuation changes. The checker chooses the latest *emitted* assertion by source position and retains earlier ones. Same-line contradictions, overlapping evidence for different values, and a latest uncertain statement have no selected proposal. `missing` lists required fields that are absent or have any emitted subject without a usable proposal; one resolved child cannot hide an unresolved sibling. Field histories and issues distinguish absent, unsupported, conflicting, and uncertain evidence. Malformed schemas are rejected without repairing or guessing facts.

Location checks do not prove meaning or completeness. A model can quote a negated value or omit a later correction. The extraction report therefore remains an immutable unapproved proposal record. The review workflow exposes the entire source, requires a cited accept/correct decision for every field and emitted subject, and checks citations again at fill. A separate named approval confirms completeness; it does not turn human judgment into a measured accuracy guarantee. Caller text is placed only in the untrusted user-data message; it cannot supply tools, prompt rules, or approval actions.

## Not done

Only the captured name-change intake can start through the demo API; adversarial and other petition-type inputs are exercised in tests. Review and fill are implemented, but supplemental intake evidence, authenticated identity, and production operation are not. PR 3 adds live local-model adapters and optional self-hosted Langfuse; the demo must still pass with tracing off. PR 4 adds forty transcripts written from exact fact sheets, with ten development cases and thirty held-out cases, including caller prompt injection and draft-approver records. Only the thirty held-out cases will determine the four reported model metrics.

The same transcript and selected values produce byte-identical petition text. Different human choices can change the draft; reviewer changes affect provenance, and run IDs, audit times, and approval metadata intentionally differ outside the text.

With two more days, the next work is the live local adapter and optional local Langfuse traces, keeping this recorded demo runnable without either service. See [DECISIONS.md](DECISIONS.md) for the choices and split.
