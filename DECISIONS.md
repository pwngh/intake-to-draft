# Decisions

- Deliver one runnable piece per PR. PR 1 provides the HTTP intake contract and reference search; the owner merges before the next piece. The initial `main` commit contains only a README stub and MIT license.
- Start clean. All project code, example people, transcripts, and note text were written here. No employer or client material, court forms, statutes, or company branding is used.
- Preserve evidence before extraction. Canonicalize only line endings and one final newline; retain interior blank lines and exact line content. Hash canonical UTF-8 text so later citations can identify the source version.
- Fail clearly on invalid intake data. Strict JSON fields reject coercion and extra keys. Canonical text is capped at 64 KiB, 500 lines, and 2,000 characters per line; error responses do not reflect input text.
- Replace the four-note TF-IDF prototype. Forty fictional notes are compared using a local MiniLM exact-cosine index and plain keyword overlap; the reference-search endpoint explicitly uses keyword search, while live workflow runs use embeddings.
- Keep tests independent of inference. The LangGraph model node replays actual captured outputs tied to prompt and source hashes; fabricated adversarial payloads in tests are labeled test inputs, not model measurements.
- Pin the installed environment. Python 3.12 is the supported interpreter; exact direct and transitive versions are in `requirements.lock`. The initial local verification used Python 3.12.14. Package hashes and offline dependency bundles are not included.
- Exercise the service through real HTTP. The demo passes an OS-bound loopback socket to Uvicorn and cleans up the child process. The descriptor-passing demonstration targets macOS and Linux.
- Use full-stop and preserve merge authority. Only task-owned branches may be pushed; the owner merges. No automatic merge, tag, package publication, visibility change, or deployment is allowed.
- Keep Council membership explicit. GPT Sol, Claude Opus, and Gemini 3.8 Flash at High are equal members. The roster and three-round cap are in global Codex instructions and project `AGENTS.md`; this overrides the skill's default model selection.
- Keep shipping credentials separate from product behavior. Claude and Antigravity use the owner's existing logins for review only. Product and tests use neither account. Claude Opus and `gemini-3.8-flash-high` passed small connectivity probes; these were not code reviews.

## Documentation checked before implementation

Read on November 17, 2026:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Ollama chat API](https://docs.ollama.com/api/chat) and [local model inventory](https://docs.ollama.com/api/tags)
- [Langfuse SDK overview](https://langfuse.com/docs/observability/sdk/overview)
- [Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
- [Langfuse headless initialization](https://langfuse.com/self-hosting/administration/headless-initialization)
- [Langfuse health and readiness](https://langfuse.com/self-hosting/configuration/health-readiness-endpoints)

The documentation describes checkpointed interrupts and compatible SDK/server generations. LangGraph 1.2.22 is pinned and exercised by recorded and live paths. Langfuse SDK 5.2.0 requires server 4.59.0 or newer; server 4.82.0 is pinned by image digest and was checked through local health and authenticated project APIs.

## Pull request sequence

1. HTTP intake validation and initial reference search. Merged by the owner.
2. Core workflow, split at the requested review-size boundary: extraction/citations and retrieval first (PR 2a), then routing, review, and fill (PR 2b). Both are merged by the owner. Council reviews the extraction slice with the five attack questions; the remaining gates need review on their actual implementation, not an inherited approval.
3. Live local model adapter and self-hosted Langfuse, with tracing optional. Merged by the owner. No hosted account requirement is acceptable.
4. Forty fact-sheet-derived cases: ten development and thirty held out. Report four metrics on the thirty only, record draft approvers, and finish the five-minute demo.

Each piece needs passing checks, Sol-loop review, and a full-stop handoff. No subsequent piece is described as finished before it runs.

## Shipping tooling

TStack's nine installed skills were verified against [upstream revision 11e37a74d0a6868c121cd0910ab2b3bd9873b92a](https://github.com/t3dotgg/tstack/tree/11e37a74d0a6868c121cd0910ab2b3bd9873b92a/skills). `full-send` is present only as a dependency of `full-stop`; its merge permission is not authorized.

GitHub CLI is authenticated as `pwngh`. Antigravity is invoked by its installed path because this process's PATH did not include it. The account exposes `gemini-3.8-flash-high`; the owner explicitly selected it as a full Council member. No model account or API key was created for the project.

## Extraction and retrieval choices

- Keep PR 1's numbered source unchanged. Assertion histories are a separate layer keyed by transcript SHA-256, field, and subject; multiple citations can support one value, and child subjects stay separate.
- Select the latest emitted assertion in code, never by model-supplied approval. Preserve earlier values and their source text. Conflicting assertions on the same last line remain unresolved; malformed or unknown fields cause atomic rejection.
- Require human semantic verification for every proposal. Exact source quotes and ordered value-word coverage cannot detect every negation or omitted correction. The extraction layer produces proposals; only the later review gate can approve them.
- Preserve real recording failures. Llama 3.2 returned malformed responses on two prompt attempts; the second raw failure is retained. The selected successful-path recording uses the already-installed local Qwen3-Coder model, with its full digest, generation options, and returned usage recorded. This disclosed choice is not a model-quality comparison.
- Freeze the recording's prompt version and source hash. A changed transcript or prompt cannot silently reuse a captured response. No environment-driven LangSmith export is enabled during replay.
- Use the Republic of Alderhaven, an explicitly fictional jurisdiction, in every requirement note and extraction result. The template carries the same label.
- Label 30 retrieval queries before scoring the 40 notes. These authored queries are a narrow retrieval benchmark, separate from the 30-case extraction holdout. No labels or note text were tuned after scoring.
- Use MiniLM revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 with local CPU ONNX inference and an exhaustive in-memory cosine index; forty vectors do not need a database. Public model assets are hash-checked, then usable offline.
- Compare against plain keyword overlap with explicit function-word removal. Raw token overlap initially undercounted the baseline; the corrected result is 20/30, compared with embeddings at 28/30. Report both and keep the two embedding misses visible in the artifact.
- Split before adding review/fill. Extraction, its attack tests, the notes, and benchmark consume most of the roughly 1,200-line PR budget; adding persistent review and a template here would make the review too broad. No extra packaging or transport features were added.
- Reject reordered or overlapping quotes within a source line. Deduplicate identical assertions, and expose evidence validity in the citation table so rejected evidence cannot look like an ordinary earlier statement.
- Leave a latest uncertain statement unresolved, without falling back to an older value. If different assertions' evidence ranges overlap, source position alone cannot establish the latest statement; leave that field unresolved too.
- Keep `missing` as required fields without a usable proposal. The accompanying field history and issues explain why; adding a second list of unresolved fields would duplicate that information.
- Declare LangSmith directly because replay imports its tracing-off context. Its exact version was already in the installed lock file; the lock was produced by `pip freeze --exclude-editable` before optional retrieval packages were installed.
- Check requirement coverage across every emitted subject. If either child's evidence is unresolved, `children` remains missing even when the sibling has a usable proposal; completely omitted subjects still require human detection.

## Human review and drafting

- Use actual LangGraph interrupts and SQLite checkpoints for `extract → check → route → review → route → fill`. Re-read the [interrupt](https://docs.langchain.com/oss/python/langgraph/interrupts) and [checkpoint](https://reference.langchain.com/python/langgraph/checkpoints) documentation on November 17, 2026; pin `langgraph-checkpoint-sqlite==3.1.3` alongside LangGraph 1.2.22. The optional SQLite vector-store dependency is upstream packaging; this workflow does not use it for retrieval.
- Keep checkpoint state to JSON-compatible values and restrict the serializer's module allowlist. The immutable extraction report and separate decision log preserve model history across restarts.
- Route every field to a person, including apparently supported proposals. Accept selects the stored proposal; correction requires quoted transcript evidence and a reason; rejection removes the usable decision and blocks required coverage. Missing source facts need a revised intake, not an uncited override.
- Preserve every emitted child subject and permit a reviewer to add an omitted child when its transcript evidence exists. The final reviewer must inspect the whole source for omissions and misattribution; lexical checks cannot certify completeness.
- Require a separate final approval at the current revision, recording approver identity and the transcript/draft hashes. Seal approved runs so later edits cannot silently invalidate an already issued draft.
- Serialize local revision checks and graph resumes with a file lock across processes. Reject stale revisions. Generate event times outside the resumable node, append audit updates only after resume, and recover an unfinished fill from its checkpoint without repeating the approval event.
- Recover pending graph tasks, including committed node writes awaiting their next checkpoint. A worker-exit regression kills the process after review, route, and fill writes; checking only the next-node list missed those durable writes and could lose the following review submission.
- Use the local API documentation for manual review. Demo decisions are explicitly scripted; reviewer identities are self-declared because this loopback demonstration has no authentication. The SQLite owner can modify the database, so the log is persistent rather than tamper-proof.
- Write an original plain-text fictional petition with a value-to-lines table. Quote values as data so embedded newlines or template-looking text cannot create new document sections. Revalidate evidence at fill and preserve earlier assertions in the output table.
- Exclude run IDs, timestamps, and identities from petition text. Identical source and selected values produce identical text; provenance and audit metadata separately record who reviewed and approved it.
- Council was completed on PR 2a. This slice receives its own Sol-loop review of the actual human/draft gates; the earlier council approval does not cover new behavior.

## Local model and tracing

- Reuse the explicitly selected, installed Qwen3-Coder model; verify its full digest before calling Ollama. Never pull, substitute a model, use a recorded fallback, or accept a remote/cloud model silently. Missing embeddings stop retrieval; model failures leave required fields unresolved for review.
- Add retrieval before extraction only for live runs. Save the three candidates and selected local note with the run; required fields come from the stored note, not model-supplied instructions. Review resumes use the checkpoint without repeating retrieval or inference.
- Treat first-choice retrieval as tentative. The existing q24 query placed a former-name note above the general name-change note; the live example uses the already labeled, situation-specific q27 query. Labels and benchmark results are unchanged. Reviewers inspect the note and restart with a better query if needed; this PR does not add note editing.
- Use temperature 0 and seed 17, but do not promise inference reproducibility across hardware or runtimes. Save raw output, prompt/source hashes, model digest, options, and returned usage. Deterministic rendering applies to the same saved source, note, and reviewed values.
- Keep the default demo and tests independent of live inference and Docker. The recorded HTTP demo explicitly forces tracing off; the separate live smoke script checks only its development example, with clearly scripted reviewer and approver identities. The four holdout metrics are measured separately in PR 4.
- Self-host Langfuse 4.82.0 with SDK 5.2.0 and six digest-pinned multi-platform images. Use upstream Compose as a small starting point, preserve its license, and omit unused services. A checkout-specific project name avoids touching unrelated containers; only the web port is published on loopback.
- Generate local demo login/project credentials through documented headless initialization. These are local accounts and keys, not external signup. Keep credentials in ignored mode-0600 files, reuse them on restart, disable telemetry/signup, and preserve volumes on shutdown.
- Export explicit node observations with a dedicated local OpenTelemetry provider, disabled environment proxies/redirects, and LangSmith off. Tracing is best effort: failures warn without rerunning the application call or changing its result. Crashes/outages can lose observations; the trace is not the durable review audit.
- Verify actual node observations through the local Langfuse API in the traced smoke test. The report records one development demonstration, not field/citation/routing/guess-rate measurements on unseen cases.
- During local verification, Colima 0.10.3 failed automatic SSH forwarding for port 13000 although all containers were healthy. Repaired only that missing forward with `ssh -F ~/.colima/_lima/colima/ssh.config -T -O forward -L 127.0.0.1:13000:127.0.0.1:13000 lima-colima`; no VM restart, global configuration change, or Colima transport feature was added to the project.

- Bound the request-side flush wait to two seconds with one in-flight export. The installed OpenTelemetry batch processor ignored its own timeout argument; a three-second local collector test verified that the caller returns before eventual delivery. Background exports have a ten-second deadline.
- Release the local model after each request with Ollama `keep_alive: 0`. Leaving the roughly 19.5 GB loaded model beside Docker on a 32 GB laptop caused database and storage stalls; releasing it trades reload time for memory available during review and trace export.
- Preserve the already validated HTTP transcript when starting a live run; repeating the terminal-newline normalization would remove a real final blank line. Bound citation line numbers and returned usage before checkpoint serialization; the citation bound is a runtime validator so frozen recording prompts remain unchanged.
- Reject inherited OTLP credential headers when tracing is requested, disable implicit SDK media uploads for text-only observations, and reject redirects during authenticated local stack verification.

## Forty-case evaluation

- Author fact sheets before transcripts. Use one invented case per existing fictional requirement note: ten per petition type, with ten development cases and thirty held out. Freeze inputs, gold evidence, scoring rules, and prompt before the holdout capture.
- Evaluate extraction with the case's specified fictional note. This isolates the four model metrics from retrieval, which retains its separate thirty-query benchmark. No fact sheets or gold evidence enter model messages.
- Use recorded local outputs for repeatable, keyless evaluation. Live capture is explicit, uses the same pinned local adapter, and never replaces an existing capture or silently changes models.
- Keep literal containment separate from factual truth. Citation accuracy counts raw assertion groups, including earlier statements; an instruction quoting an invented value can have a literal citation while still failing fact accuracy and routing. Unparseable whole outputs have no citation groups and are listed separately.
- Use strict word-token equality for model facts, ignoring punctuation/case but not adding semantic aliases. It is deliberately format-sensitive, including child-record words such as “born”; it is not a legal or semantic quality judgment. Scripted draft review requires exact authored values so the scoring normalization cannot remove a requested name's hyphen.
- Reserve empty child review rows for omitted known children before crediting an unresolved sibling. A single generic child placeholder does not establish that every child was surfaced for review.
- Score before scripted fact-sheet corrections. Every released evaluation draft records “Scripted Fact-Sheet Approver”; unresolved facts and unsupported extra subjects remain blocked. These are simulated reviewer actions, not claims that a person inspected the drafts.
- Capture under a local file lock and atomically publish complete records without replacement. Report output is confined to ignored runtime files, and checking compares the committed baseline before writing.
- Fix evaluator defects found during development before the holdout. Keep the local model, extraction prompt, transcripts, and expected facts unchanged; report rejected and inaccurate outputs rather than tuning against the thirty test cases.

- Preserve the first thirty holdout responses unchanged. Sixteen fail the extraction schema; the injection case passes the lexical checker with an invented address. Publish these failures without tuning the prompt or scorer after capture.
- Make the default demo replay and compare the full holdout report after the HTTP review example. It needs neither inference nor Docker; the five-minute walkthrough starts after package installation.
- Keep post-review success separate from model quality. Scripted evidence-based corrections produce twenty holdout drafts with named test approvers; ten unresolved cases remain blocked. This is regression evidence, not an independent human evaluation.

## Development-only child extraction follow-up

- Tune only the ten existing development cases. The five child-bearing cases expose split name/date facts, duplicate subjects, case-level children, and lost correction history. Do not inspect or recapture the thirty holdout cases for this change.
- Add `extract-children-v1` as a prompt supplement for notes requiring children. Require complete cited child values, one stable subject per child, and earlier/corrected assertions grouped together. Keep the original strict schema/checker and unmodified model responses; no JSON repair or fact-sheet answers enter inference.
- Preserve the original evaluation implementation and all its frozen files. The API and live smoke script select the new adapter; archived recorded runs keep the original v2 path. The new adapter delegates transport, digest verification, schema, options, and failure behavior to the existing local adapter.
- Compare all ten development cases, with five new child captures and the same five non-child captures on both sides. Reusing those outputs reflects the conditional prompt change and avoids presenting unchanged cases as new inference. This is development feedback, not a new holdout score.
- Re-read [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs) and [chat](https://docs.ollama.com/api/chat) on November 17, 2026. Keep the installed Ollama 0.30.0, pinned Qwen digest, generation settings, and existing JSON schema unchanged; only the child-specific system guidance changes.

- Retain the first five new responses. Complete child values improve from 0/7 to 7/7 and both assertions of the corrected child date are supported in one subject. The remaining requested-outcome error and unsupported order-date history stay visible. Do not infer general accuracy or missing-child robustness from these seven known child values.
- Extend the one-command demo with the separate development replay. Keep the original holdout replay on v2 and keep its report byte-identical; no new holdout score is computed.
