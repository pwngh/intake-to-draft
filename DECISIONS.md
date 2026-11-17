# Decisions

- Deliver one runnable piece per PR. PR 1 provides the HTTP intake contract and reference search; the owner merges before the next piece. The initial `main` commit contains only a README stub and MIT license.
- Start clean. All project code, example people, transcripts, and note text were written here. No employer or client material, court forms, statutes, or company branding is used.
- Preserve evidence before extraction. Canonicalize only line endings and one final newline; retain interior blank lines and exact line content. Hash canonical UTF-8 text so later citations can identify the source version.
- Fail clearly on invalid intake data. Strict JSON fields reject coercion and extra keys. Canonical text is capped at 64 KiB, 500 lines, and 2,000 characters per line; error responses do not reflect input text.
- Use four TF-IDF vectors in memory. This is genuine lexical vector retrieval with cosine ranking, suitable for four invented notes; it is not semantic retrieval. Positive-score matches are candidates only, with stable score/ID ordering and stored requirements.
- Keep the first slice model-free. No extraction fixture is presented as an LLM. Model evaluation scores remain unmeasured until local inference and the forty-case dataset exist.
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

The documentation describes checkpointed interrupts and compatible SDK/server generations. LangGraph and Langfuse are not dependencies of this first slice; select and pin compatible exact versions when they are introduced, then verify actual behavior rather than relying on these notes.

## Pull request sequence

1. HTTP intake validation, preserved source lines, and invented reference search. Current piece.
2. LangGraph extraction/check/review/fill path, persistent reviewer actions, original demonstration template, and provenance. Council belongs on this core logic PR.
3. Forty invented cases and recorded local-model evaluation metrics, including reproducibility and guessing failures.
4. Local Langfuse composition and readable per-node traces; verified clean-checkout end-to-end demo.

Each piece needs passing checks, Sol-loop review, and a full-stop handoff. No subsequent piece is described as finished before it runs.

## Shipping tooling

TStack's nine installed skills were verified against [upstream revision 11e37a74d0a6868c121cd0910ab2b3bd9873b92a](https://github.com/t3dotgg/tstack/tree/11e37a74d0a6868c121cd0910ab2b3bd9873b92a/skills). `full-send` is present only as a dependency of `full-stop`; its merge permission is not authorized.

GitHub CLI is authenticated as `pwngh`. Antigravity is invoked by its installed path because this process's PATH did not include it. The account exposes `gemini-3.8-flash-high`; the owner explicitly selected it as a full Council member. No model account or API key was created for the project.
