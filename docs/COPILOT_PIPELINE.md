# Copilot Self-healing Pipeline

`copilot/workflow_generator.py` runs an 8-layer pipeline. Each layer
emits an SSE event consumed by the frontend.

| Layer | Stage              | Purpose                                                      |
|-------|--------------------|--------------------------------------------------------------|
| 1     | `pipeline-start`   | Announce; collect prior workflows for prompt examples.       |
| 2     | `plan`             | Gemini drafts a workflow JSON.                               |
| 3     | `extract`          | Parse JSON (markdown fences / brace match fallback).         |
| 4a    | `validate-schema`  | `engine.validator.validate_dag` — pure structural checks.    |
| 4b    | `validate-semantic`| `engine.dag_runner.dry_run_workflow` — runs without I/O.    |
| 5     | `repair`           | Feeds errors back to Gemini. Retries up to 3 times.          |
| 6     | `workflow` + `message` + `complete` | Final accepted workflow streamed to UI.       |
| 7     | `error`            | Emitted when retry budget is exhausted.                      |
| 8     | (terminal)         | Producer puts `None` in the queue; SSE stream closes.        |

## Prompt design

The system prompt always includes:
* The full node catalogue (`registry.all_specs()`).
* The user request and last 6 turns of conversation.
* One example existing workflow (truncated) to anchor the model's style.

## Extending

* Add a new validation pass → insert another `await queue.put(...)` block
  before the `accept` step in `run_pipeline`.
* Bypass Gemini for tests → `_model()` returns `None` when
  `GOOGLE_API_KEY` is missing; `_generate` then returns a stub.
  