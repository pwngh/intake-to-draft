# One observed local trace

This is a reading guide to a successful invented development run, not an accuracy evaluation. Durations are measured node execution times; review spans do not include the time a person would spend between requests. Inputs and outputs below are summaries of the actual observations.

Run `d8796993ffca410781e5a0767abc7e8f` used local Qwen3-Coder through Ollama 0.30.0 and Langfuse SDK 5.2.0/server 4.82.0. [Open the saved local trace](http://127.0.0.1:13000/project/intake-demo/traces/d8796993ffca410781e5a0767abc7e8f) after `./scripts/langfuse up`; use the generated local login described in the README. Select a node to inspect its complete input, output, and timing. Running `./scripts/live-demo --trace` exports the complete observations to `.runtime/live-demo.json`.

| Node | Observations | Seconds per observation (min–max) | Input | Output |
| --- | ---: | ---: | --- | --- |
| retrieve | 1 | 1.607000–1.607000 | The chosen-name reference query (q27). | Selected adult_name_change_chosen_name; five required fields; three candidates retained. |
| extract | 1 | 49.001000–49.001000 | The eight-line invented intake and selected fictional note. | Five proposed fields, including birth-date statements on lines 4 and 8; raw response and model metadata saved. |
| check | 1 | 0.049000–0.049000 | Raw model response, numbered source, and required fields. | No missing fields or report issues; latest emitted date is 1991-06-19; every proposal remains unapproved. |
| route | 7 | 0.000000–0.004000 | Current decisions and approval. | First routes to needs_review; after separate approval routes to drafting. |
| review | 12 | 0.000000–0.017000 | Checked proposals and current review revision. | Six interrupt/resume pairs: five scripted field acceptances and one named completeness approval. |
| fill | 1 | 0.002000–0.002000 | Cited accepted values and separate approval. | Fictional petition plus five-row provenance table; address cites lines 5 and 6; earlier date retained. |

The approver was explicitly scripted: `Scripted Live Demo Approver`. The draft SHA-256 is `4feaa058b6b2f16ff2e8535269b89dca2f4cb8a2dfbb8350ae35e74aa8e56ed6`. Tracing-off and tracing-on runs produced identical draft text in this check; future local inference is not guaranteed to repeat. [Exact model, usage, versions, and measurements](live_smoke_report.json).
