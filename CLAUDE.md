# CLAUDE.md

This project was previously developed with Codex; work now continues with Claude Code only.

## Language

Communicate with the user in Japanese (日本語). This applies to chat responses, clarifying questions, and plan/summary text — not to code, comments, or file content, which should follow the existing conventions in this repo (English).

## Hard constraints (do not change without asking the user)

- The first-pass mapping judgment's payload (`post_bool_prompt` in `bsllmner-evaluator.py`: `temperature: 0`, `logprobs: True`, its `response_format`) is a known-working llama.cpp configuration — don't alter it casually. This protection does not extend to the newer per-category classification payload (`post_category_prompt`), which has already been redesigned twice in one session and is fine to keep iterating on.
- Logprob-based confidence scores only ever consider exact `true`/`false` token matches (stripping incidental leading whitespace when the token sits inside a JSON object, as in `post_category_prompt`) — no capitalized/quoted/newline-prefixed variants.
- Don't change error-handling behavior (fail-fast on malformed TSV/config, warn-and-continue on missing ontology terms) without asking first.
- Don't edit or add untracked files unless the user explicitly asks (several exist locally: examples, local input data, scratch scripts).
- If you add/change output TSV columns, update `README.md`, or flag it as stale if you can't.

## Validation

No test suite exists. Useful syntax-only checks:

```sh
python -c "import ast, pathlib; ast.parse(pathlib.Path('bsllmner-evaluator.py').read_text())"
bash -n scripts/run_eval.sh
python -m json.tool input/error_categories.json
```

Full runs require a live llama.cpp endpoint and are not always exercised during edits — say so if you haven't run one.
