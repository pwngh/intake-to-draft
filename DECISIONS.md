# Decisions

- Deliver one runnable piece per PR. PR 1 provides the HTTP intake contract and reference search; the owner merges before the next piece. The initial `main` commit contains only a README stub and MIT license.
- Start clean. All project code, example people, transcripts, and note text were written here. No employer or client material, court forms, statutes, or company branding is used.
- Preserve evidence before extraction. Canonicalize only line endings and one final newline; retain interior blank lines and exact line content. Hash canonical UTF-8 text so later citations can identify the source version.
- Fail clearly on invalid intake data. Strict JSON fields reject coercion and extra keys. Canonical text is capped at 64 KiB, 500 lines, and 2,000 characters per line; error responses do not reflect input text.
- Replace the four-note TF-IDF prototype. Forty fictional notes are compared using a local MiniLM exact-cosine index and plain keyword overlap; the recorded-output service explicitly uses keyword search until live adapters arrive.
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
- [Langfuse SDK overview](https://langfuse.com/docs/observability/sdk/overview)
- [Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)

The documentation describes checkpointed interrupts and compatible SDK/server generations. LangGraph 1.2.22 is now pinned and exercised by the recorded extract/check path. Langfuse will be pinned with a compatible server version in PR 3; reading its docs does not prove a local deployment works.

## Pull request sequence

1. HTTP intake validation and initial reference search. Merged by the owner.
2. Core workflow, split at the requested review-size boundary: extraction/citations and retrieval first (PR 2a), then routing, review, and fill (PR 2b, current piece). Council reviews the extraction slice with the five attack questions; the remaining gates need review on their actual implementation, not an inherited approval.
3. Live local model adapter and self-hosted Langfuse, with tracing optional. No hosted account requirement is acceptable.
4. Forty fact-sheet-derived cases: ten development and thirty held out. Report four metrics on the thirty only, record draft approvers, and finish the five-minute demo.

Each piece needs passing checks, Sol-loop review, and a full-stop handoff. No subsequent piece is described as finished before it runs.

## Shipping tooling

TStack's nine installed skills were verified against [upstream revision 11e37a74d0a6868c121cd0910ab2b3bd9873b92a](https://github.com/t3dotgg/tstack/tree/11e37a74d0a6868c121cd0910ab2b3bd9873b92a/skills). `full-send` is present only as a dependency of `full-stop`; its merge permission is not authorized.

GitHub CLI is authenticated as `pwngh`. Antigravity is invoked by its installed path because this process's PATH did not include it. The account exposes `gemini-3.8-flash-high`; the owner explicitly selected it as a full Council member. No model account or API key was created for the project.

## Extraction and retrieval choices

- Keep PR 1's numbered source unchanged. Assertion histories are a separate layer keyed by transcript SHA-256, field, and subject; multiple citations can support one value, and child subjects stay separate.
- Select the latest emitted assertion in code, never by model-supplied approval. Preserve earlier values and their source text. Conflicting assertions on the same last line remain unresolved; malformed or unknown fields cause atomic rejection.
- Require human semantic verification for every proposal. Exact source quotes and ordered value-word coverage cannot detect every negation or omitted correction. This slice produces no draft and never marks a proposal approved.
- Preserve real recording failures. Llama 3.2 returned malformed responses on two prompt attempts; the second raw failure is retained. The selected successful-path recording uses the already-installed local Qwen3-Coder model, with its full digest, generation options, and returned usage recorded. This disclosed choice is not a model-quality comparison.
- Freeze the recording's prompt version and source hash. A changed transcript or prompt cannot silently reuse a captured response. No environment-driven LangSmith export is enabled during replay.
- Use the Republic of Alderhaven, an explicitly fictional jurisdiction, in every requirement note and extraction result. The subsequent template must carry the same label.
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
