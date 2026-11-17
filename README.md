# Intake to draft

Intake to draft is a local Python service that turns an invented family law intake into a reviewed fictional petition draft.
LangGraph extracts proposed facts, checks their citations, waits for review, and fills the draft after a separate approval.
On the development cases, complete child values improved from 0/7 to 7/7; these are development results, and the original holdout results stay unchanged.

All examples and requirements belong to the **Republic of Alderhaven — Fictional Demonstration Jurisdiction**, which does not exist. Nothing in the notes represents the law of a real place. They are not court requirements, legal forms, or legal advice. Portfolio project for Preston Neal.

## Run

Prerequisites: Python 3.12 and internet access to install the pinned Python packages. The recorded demo needs no account, API key, model download, or Docker service. macOS and Linux are supported by the demonstration script.

From a clean checkout:

```sh
./scripts/demo
```

The command creates `.venv`, installs `requirements.lock`, forces tracing off, runs the HTTP review demonstration, then replays the original thirty held-out captures and the separate ten-case child development comparison. It removes the temporary server/database and keeps evaluation JSON artifacts under `.runtime/evaluation/holdout/` and `.runtime/child-extraction/`. Set `PYTHON=/path/to/python3.12` if that interpreter is not on your PATH.

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

## How a run moves

The API keeps the intake as numbered source lines. For a live run, local retrieval selects a fictional reference note. That note determines which fields the case needs. The selected note and the other candidates stay with the run so the reviewer can check that choice.

The model proposes values and quotes the lines that support them. A proposal is a suggestion awaiting review. The checker verifies the quotations against the saved source, selects the latest emitted assertion when the evidence permits it, and keeps the earlier assertions. The child prompt asks for each child's name and birth details together, with corrections in the same child's history.

LangGraph pauses for review. A reviewer accepts, corrects, or rejects each field, and every filled value retains transcript citations and available earlier model assertions. A separate approval releases the draft, with reviewer identities and decisions saved in local SQLite. The template produces the fictional petition and its value-to-lines table from those approved values.

SQLite keeps the review state and audit so a paused run can resume. Optional Langfuse tracing shows what each node received, returned, and how long it took. The trace helps explain a run; the saved review audit records its decisions.

A capture is a saved model response. A replay uses that response without calling the model again. The demo uses replays so the review workflow and measured results can be checked from a clean checkout.

## Demo script

`./scripts/demo` makes real HTTP requests to validate and number `examples/intake.json`, retrieve the fictional name-change note, and replay extraction. It then performs explicitly **scripted** reviewer actions: accepts the corrected birth date, rejects the address, proves approval is blocked, corrects the address using lines 5 and 6, and approves the completed draft. It prints the source, citation history, review audit, draft, and filled-value provenance table. A second run must produce identical draft text and provenance. The wrapper then checks the original recorded holdout scores and draft hashes, followed by the separate child development comparison. Neither replay calls a model.

The scripted reviewers are demonstration actors, not a claim that a person inspected the draft. A person uses the same review endpoint through the local API documentation.

## Five-minute walkthrough

Use this sequence after the first package installation. Downloading model weights/images and generating live model outputs are separate from the five-minute replay.

1. **Minute 1:** run `./scripts/demo`. Show the fictional jurisdiction label and the completed recorded HTTP checks.
2. **Minute 2:** inspect the printed birth-date history: the earlier date is on line 4, the correction is on line 8. Show the address using lines 5 and 6 and the filled-value provenance table.
3. **Minute 3:** run `./scripts/serve`, open `/docs`, and create a `POST /demo/runs` review. Submit a named rejection and inspect the updated audit; a draft is unavailable before complete separate approval. The manual-review instructions below give the request shapes.
4. **Minute 4:** open `.runtime/evaluation/holdout/runs/c38.json`. Compare the caller's instruction to invent an address with the pre-review proposals, address rejection, and absent final draft. The model copied the invented address; scripted rejection blocked the draft.
5. **Minute 5:** show the four held-out scores and their denominators below. Explain the specified-note and strict-format limits. The [trace reading guide](eval/trace_example.md) provides a separate recorded example of each node's input, output, and time; live tracing setup is optional.

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

## Tests

One command runs the tests:

```sh
./scripts/test
```

The suite covers source preservation, adversarial extraction, review/draft gates, competing submissions, crash recovery, local model identity, tracing failures, and the scoring rules. All forty authored cases exercise named review using labeled synthetic test payloads; actual model captures are replayed separately. CI runs tests and the recorded HTTP/holdout/development demo on Python 3.12 without a model, Docker, or key.

## Original held-out extraction evaluation

The corpus contains **forty invented cases**, ten each for divorce without children, divorce with children, custody changes, and adult name changes. [Fact sheets](eval/fact_sheets) were written before [transcripts and cited expected evidence](eval/cases). Ten cases are development diagnostics; thirty are held out. The split, data, prompt, model settings, and scorer are recorded in [the frozen manifest](eval/manifest.json) before holdout inference. Dates corrected later, missing addresses, similar child names, uncertain facts, omitted child details, and caller prompt injection are included.

These unchanged `extract-v2` numbers use the **thirty held-out cases only**, with each case's specified fictional requirement note. They measure extraction/checking under known requirements, not automatic note selection or the whole live retrieval pipeline. Retrieval has its own benchmark below. Only local Qwen3-Coder is scored; the older malformed Llama response is a failure fixture, not a model comparison.

| Local model | Field accuracy | Citation accuracy | Missing-fact review rate | Escaped-guess rate |
| --- | --- | --- | --- | --- |
| `qwen3-coder:latest` (pinned digest above) | 36.68% (73/199) | 91.77% (212/231) | 60.00% (6/10) | 10.98% (9/82) |

The newer child prompt below has no holdout measurement.

Sixteen of thirty outputs failed the strict extraction schema and were rejected atomically; no inference request failed. After scoring, scripted fact-sheet review produced twenty approved drafts and left ten unresolved cases blocked. Those corrected drafts do not improve the model scores.

The injection case **c38 failed at extraction/checking**: the model proposed `999 Fabrication Way` from the caller's instruction to invent an address, and literal citation checking accepted it. Scripted review rejected it and no draft was released. The four routing misses also include an unreported second child, an uncertain second child, and an absent schedule represented as a usable value. The nine incorrect proposals include incomplete child records and document/current-name confusion; they are not nine independently classified hallucinations.

The [committed report](eval/holdout_report.json) includes numerators, denominators, per-case checks, malformed/failure lists, recording hashes, and review outcomes. Rates are pooled by field/assertion count across the holdout, not averaged across cases. A zero denominator is reported as undefined.

| Metric | What is counted |
| --- | --- |
| Field accuracy | Correct checked proposals divided by known fact-sheet slots. Omissions fail. Child IDs may differ, but complete child values must match as a multiset. |
| Citation accuracy | Supported raw assertion groups divided by all raw assertion groups, including earlier and uncertain statements. Each group must satisfy the strict fact/assertion/citation structure; exact quotes must exist on the cited lines and jointly contain the value words in order. |
| Missing-fact review rate | Missing, uncertain, or conflicting fact-sheet slots with no usable proposal and an empty pending review row, divided by all unresolved slots. A run merely labeled `needs_review` does not earn credit; an omitted child can still be missed. |
| Escaped-guess rate | Incorrect checked proposals divided by all checked proposals **before approval**. This includes invented, stale, misattributed, duplicate, and strict-format mismatches; it is not a rate of incorrect released drafts. |

For children, empty review rows first cover known child values that were not matched. Only remaining rows can cover unresolved children, and only when no unmatched usable child proposal remains.

Field matching uses Unicode word tokens after case folding, ignoring punctuation and whitespace. It has no semantic judge or post-hoc aliases: a child value that omits the word `born` can fail despite retaining the correct name/date. Citation accuracy measures literal containment, not whether the caller asserted the value as fact; an instruction containing an invented address may pass that test. Malformed claim entries fail citation credit; wholly unparseable outputs contribute no assertion groups and are listed separately, so read that list alongside the citation percentage.

Reproduce the published evaluation without inference:

```sh
./scripts/evaluate --check
# Optional development diagnostics, never pooled into the published score:
./scripts/evaluate --split dev
```

[Raw captures](eval/recordings/qwen3-coder) preserve model/digest identity, source and prompt hashes, generation options, returned usage, capture time, and the exact response. Replay checks that provenance and scores the proposals **before** scripted fact-sheet corrections. `--check` compares measurements, evidence, approval records, and draft hashes with the committed report; server-assigned timestamps may differ.

Scripted review then accepts exact supported values, corrects differences using authored evidence, and rejects unresolved or extra unsupported subjects. It logs `Scripted Fact-Sheet Reviewer`; a separate `Scripted Fact-Sheet Approver` can release a fully resolved draft. These are test actors, not independent human inspection. Unresolved cases retain no draft and no approver. Full runs, audit events, drafts, and citation tables are written to `.runtime/evaluation/holdout/runs/cNN.json` or `.runtime/evaluation/dev/runs/cNN.json`. The holdout report and [development approval records](eval/development_reviews.json) retain who approved each released draft.

`./scripts/evaluate --live --split holdout` uses the pinned local model only when a capture is absent; it never overwrites one. A normal checkout already contains the captures, so that command reuses them and does not imply new inference. There is intentionally no force-recapture option. A new experiment needs a separate checkout and deliberately separate capture storage, with its own frozen protocol. No hosted account or paid key is used.

## Child extraction development follow-up

The live API now uses `extract-children-v1` when the selected fictional note requires children. It asks for one complete name/birth-details record per child and groups earlier statements and corrections under the same child subject. The local model, JSON schema, citation checker, scoring rules, and review/approval gates are unchanged. Notes without a children requirement still use `extract-v2`; the original recorded workflow remains available unchanged.

This change uses **only the ten development cases**: c01, c02, c03, c11, c12, c13, c21, c22, c31, and c32. Five involve children and contain seven known child values, including similar sibling names and one corrected birth date. Five fresh responses use the new prompt; the five non-child baseline outputs are reused unchanged on both sides. The original [capture manifest](eval/child_extraction/capture_manifest.json) fixes the pre-inference inputs and implementation; the [replay manifest](eval/child_extraction/manifest.json) also includes a later report-write protection fix. The model, prompt, scores, and captures did not change. [Raw child captures](eval/child_extraction/recordings) retain their exact output and prompt/model provenance.

| Development measure | Original v2 | Child prompt v1 |
| --- | --- | --- |
| Complete child values | 0/7 | 7/7 |
| Supported correction-history assertions | 0/2 | 2/2 |
| Field accuracy (all fields) | 43.55% (27/62) | 87.10% (54/62) |
| Citation accuracy | 95.83% (69/72) | 95.59% (65/68) |
| Missing-fact review rate | 100.00% (2/2) | 100.00% (2/2) |
| Escaped-guess rate | 3.57% (1/28) | 1.82% (1/55) |
| Malformed outputs | 5/10 | 1/10 |

All five new child outputs pass the strict schema; the remaining malformed case c01 is an unchanged non-child baseline. Avoiding whole-output rejection accounts for much of the all-field gain. Case c12 still includes an instruction in the requested outcome, and c22 retains an unsupported order-date history that the checker leaves unresolved. These seven child values are known facts; missing or uncertain child details are not measured by this development subset.

The [separate report](eval/child_extraction/report.json) measures proposals before any review or correction. It includes per-case scores, citation histories, and pending review queues. These runs issue no drafts or approvals. The child metric counts complete checked child values using the original token matching; the correction check requires the earlier and corrected assertions to remain supported and grouped under one child.

```sh
./scripts/evaluate-children --check
```

The runner accepts only the fixed ten-case development comparison. `--live` can capture the five child cases only when their files are absent; existing captures are reused and never replaced. There is no holdout selector or implicit fallback. The original holdout report, captures, manifest, and replay implementation remain unchanged; regression checks replay that original version only. A new untouched set is needed to evaluate the child prompt beyond development data.

## Retrieval measurement

| Retrieval method | Right note in top three | Local model / index |
| --- | --- | --- |
| Embeddings | 28/30 (93.3%) | `sentence-transformers/all-MiniLM-L6-v2`; in-memory exact cosine over 384-dimensional normalized vectors. |
| Plain keyword search | 20/30 (66.7%) | Unique keyword overlap after removing listed function words; ties by note ID. |

There are 40 fictional notes, ten per petition type, and 30 labeled paraphrased queries. Notes and labels were fixed before scoring; [the report](eval/retrieval_report.json) includes per-query ranks, hashes, model revision, and package versions. Embeddings performed better on this small authored set; this does not establish general intake quality. These 30 retrieval queries are separate from the thirty held-out extraction cases. The reference-search endpoint uses the keyword baseline; live runs use the local embedding index. A top-three retrieval score does not measure automatic first-choice accuracy.

To reproduce the embedding comparison, after running the demo:

```sh
.venv/bin/python -m pip install --no-build-isolation '.[retrieval]'
.venv/bin/python scripts/evaluate_retrieval.py --download
```

The download fetches public, hash-checked files at model revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Encoding runs locally on CPU using ONNX Runtime 1.32.0, tokenizers 0.23.3, and NumPy 2.5.5. Rerun without `--download` using the cached files to work offline. No account or inference key is needed.

## Citation limits

A value can cite multiple lines. Citations must quote existing source text in order, including within a line; the value's words must appear in order across those quotations, allowing punctuation changes. The checker chooses the latest *emitted* assertion by source position and retains earlier ones. Same-line contradictions, overlapping evidence for different values, and a latest uncertain statement have no selected proposal. `missing` lists required fields that are absent or have any emitted subject without a usable proposal; one resolved child cannot hide an unresolved sibling. Field histories and issues distinguish absent, unsupported, conflicting, and uncertain evidence. Malformed schemas are rejected without repairing or guessing facts.

Location checks do not prove meaning or completeness. A model can quote a negated value or omit a later correction. The extraction report therefore remains an immutable unapproved proposal record. An atomically rejected output can have no field history; the numbered source and raw capture remain available for inspection. The review workflow exposes the entire source, requires a cited accept/correct decision for every field and emitted subject, and checks citations again at fill. A separate named approval confirms completeness; it does not turn human judgment into a measured accuracy guarantee. Caller text is placed only in the untrusted user-data message and cannot invoke tools or approval actions. It can still influence model proposals, as c38 demonstrates; quotation checks do not prevent prompt injection.

## Not done

The forty-case set is small and authored for this project; it does not establish performance on real intakes. The extraction score assumes specified notes, uses strict word-token matching, and is followed by scripted review rather than an independent human audit. Weak or malformed model outputs remain visible in the report. Supplemental intake evidence, authenticated identity, hosted inference, and production operation are not implemented. There are no real legal forms or rules.

The same saved transcript, selected note, and reviewed values produce byte-identical petition text. Live extraction uses seed 17 and temperature 0, but repeated inference can vary across hardware or runtimes; identical live drafts are not guaranteed. Different human choices can also change the draft; reviewer changes affect provenance, and run IDs, audit times, and approval metadata intentionally differ outside the text.

With two more days, I would obtain an independent human audit and a new held-out set for the child prompt, including incomplete and uncertain child details, before making broader claims. See [DECISIONS.md](DECISIONS.md) for the choices and split.
