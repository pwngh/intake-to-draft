# Decisions

- Start clean. The repository began empty, with an original README stub and MIT license on `main`; no employer or client files were used.
- Stop locally on unavailable review models. Claude authentication and a live `opus` connectivity check now pass; the CLI reported `claude-opus-4-8` for the requested response. No Gemini CLI or configured Gemini credentials were found, so the third Council provider remains unavailable. No account was created, no key requested, and no review model substituted.
- Use the upstream TStack skills. All nine installed skill directories match every file in [t3dotgg/tstack at 11e37a74d0a6868c121cd0910ab2b3bd9873b92a](https://github.com/t3dotgg/tstack/tree/11e37a74d0a6868c121cd0910ab2b3bd9873b92a/skills). The installer encountered existing destinations; a separate pinned download verified their contents without overwriting them.
- Keep merge authority with the owner. `full-send` is installed because `full-stop` imports its workflow, but only the `full-stop` workflow is authorized. No remote repository, push, pull request, or merge has occurred.
- Do not invent measurements. No application, tests, evaluation scores, or runtime dependency pins exist yet. Pin dependencies when implementation starts and record only measured results.

## Available shipping skills

`babysit-pr`, `council`, `file-pr`, `full-send`, `full-stop`, `leaving-pr-comments`, `modernize`, `sol-loop`, and `takeover` are installed in `/Users/user/.codex/skills`.

GitHub CLI is authenticated as `pwngh`; Python 3 and Docker executables are present. Docker runtime health has not been tested. Native subagents offer Sol, but the required Council review spans three providers. No Council or Sol review has been performed.

Claude Code 2.1.160 completed a one-turn connectivity check with `--model opus --effort high`; the prompt contained no project files and tools were disabled. This confirms connectivity, not a code review. Gemini's documented setup is `npm install -g @google/gemini-cli`, then `gemini` and browser sign-in with an existing Google account. That route requires no API key; access to the required Gemini review model must still be checked after sign-in. See the official [installation](https://geminicli.com/docs/get-started/installation/) and [authentication](https://geminicli.com/docs/get-started/authentication/) guides.

## Documentation read before implementation

Reviewed on November 17, 2026:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Langfuse SDK overview](https://langfuse.com/docs/observability/sdk/overview)
- [Langfuse Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)

The implementation must select compatible SDK/server versions explicitly. Reading current documentation is not evidence that a deployment or demo works.

## Intended pull request sequence

1. Runnable service skeleton, invented reference notes, and schema validation.
2. LangGraph workflow, field-level human review, provenance, and draft rendering; run Council on this core logic.
3. Forty invented cases, model adapters, reproducibility checks, and recorded evaluation results.
4. Local Langfuse composition, readable traces, and a verified clean-checkout demo.

Each piece needs its own passing checks and `full-stop` handoff. The owner merges. This sequence is planned, not implemented.
