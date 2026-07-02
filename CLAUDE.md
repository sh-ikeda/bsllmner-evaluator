# CLAUDE.md

This project was previously developed with Codex; work is now continuing with Claude Code.

## Language

Communicate with the user in Japanese (日本語). This applies to chat responses, clarifying questions, and plan/summary text — not to code, comments, or file content, which should follow the existing conventions in this repo (English).

Read these two files in full before making changes — they are the primary source of truth, not this file:

- `AGENTS.md`: project purpose, input/output formats, error-handling philosophy, and development conventions.
- `HANDOFF.md`: current evaluator flow (mapping judgment + extraction/selection error classification), most recent input/output formats, and error category definitions. **`HANDOFF.md` reflects the current state more accurately than `AGENTS.md` in places where they disagree** (e.g. output column count) — `AGENTS.md` describes an earlier version of the output format.

## Quick orientation

- Main script: `bsllmner-evaluator.py` (single-file CLI, no package structure).
- Evaluates `bsllmner-mk2` ontology mappings against original BioSample metadata via a llama.cpp OpenAI-compatible chat endpoint.
- Current flow: judge mapping true/false → if false and a term was mapped, classify extraction error → if extraction is valid, classify selection error. See `HANDOFF.md` for full detail.
- Config: `input/evaluation_config.json` (per-attribute prompts/ontology settings), `input/error_categories.json` (extraction/selection category definitions).

## Hard constraints (do not change without asking the user)

- Do not casually alter the llama.cpp request payload shape for the boolean evaluator (`temperature: 0`, `logprobs: True`, existing `response_format`) — it's a known-working configuration for the current llama.cpp setup.
- Logprob-based confidence score only ever considers exact `true`/`false` token matches — no space-prefixed/capitalized/quoted variants.
- Do not change error-handling behavior (fail-fast on malformed TSV/config, warn-and-continue on missing ontology terms) without asking first.
- Do not edit or add untracked files unless the user explicitly asks (several exist locally: examples, local input data, scratch scripts).
- If you add/change output TSV columns, update `README.md` or flag it as stale.

## Validation

No test suite exists. Useful syntax-only checks:

```sh
python -c "import ast, pathlib; ast.parse(pathlib.Path('bsllmner-evaluator.py').read_text())"
bash -n scripts/run_eval.sh
python -m json.tool input/error_categories.json
```

Full runs require a live llama.cpp endpoint and are not always exercised during edits — say so if you haven't run one.
