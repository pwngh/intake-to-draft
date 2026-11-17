# Working agreements

This project uses invented examples only. Do not import employer or client material, real court forms, statutes, or legal advice.

Work in small runnable pull requests. Use full-stop, never full-send. Push only task-owned branches after scanning the complete tree and history. The owner merges; never merge, enable auto-merge, tag, publish packages, or change visibility.

Council runs once on the core workflow pull request; skip it for housekeeping. Use these three equal members at High reasoning effort:

- GPT Sol (resolve and record the exact Sol model).
- Claude Opus (resolve and record the exact Opus model).
- Gemini 3.8 Flash at High (`gemini-3.8-flash-high`, Antigravity). It is a full member, not described as a flagship.

Give all three members the same review scope and include every member's findings in the agreement gate. Show actual model names, reasoning effort, round numbers, and returned scores in the PR's Council table; write `no score` when none was returned. Never invent identity, usage, scores, or agreement. Council has a maximum of three complete rounds; if agreement is missing after round three, stop and report open findings, disagreements, and evidence. Do not start a fourth round. If a selected model cannot be reached, report the failure and stop at a local branch without substituting.

Run `./scripts/test` for checks and `./scripts/demo` for the current demonstration. README claims must match observed tests or measurements. Pin dependencies, keep outputs deterministic where feasible, and record limitations plainly in DECISIONS.md.
