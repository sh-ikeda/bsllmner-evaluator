# AGENTS.md

This repository is `bsllmner-evaluator`, a small evaluator for ontology mappings produced by `bsllmner-mk2`.

## Project Purpose

`bsllmner-mk2` extracts attribute strings from BioSample records, such as cell line, tissue, disease, drug, knockout gene, knockdown gene, or overexpressed gene, and maps them to ontology terms.

This project evaluates whether those mapped ontology terms are appropriate for the original BioSample metadata. It builds a prompt from:

- A BioSample record before ontology mapping.
- A mapped ontology term from the `bsllmner-mk2` result.
- Attribute-specific settings in `input/evaluation_config.json`.

The prompt is sent to a llama.cpp OpenAI-compatible chat completions endpoint. The model is instructed to answer only `true` or `false`.

## Main Files

- `bsllmner-evaluator.py`: Main evaluator CLI.
- `input/evaluation_config.json`: Attribute-specific ontology paths, base URIs, ontology properties to dump, and prompts.
- `scripts/select_result_to_tsv.py`: Converts `bsllmner-mk2` JSON output into a simpler TSV for evaluation.
- `scripts/select_result_v1_to_tsv.py`: Older conversion script.
- `scripts/run_eval.sh`: Helper script for generating TSVs, fetching BioSample JSON, preparing compact JSON input, and running evaluation.
- `README.md`: User-facing usage and input/output format notes.

Some local data, generated outputs, or experimental scripts may be untracked. Do not edit or add untracked files unless the user explicitly asks.

## Inputs

The evaluator expects:

1. A TSV converted from `bsllmner-mk2` output.
   - Usually two columns:
     - BioSample accession.
     - Mapped ontology term ID.
   - Example:
     ```tsv
     SAMD00008684	CVCL_0019
     ```

2. A BioSample JSON file.
   - A JSON array of compact BioSample records.
   - Each object must include `accession`.
   - Other fields are sample metadata and are passed into the prompt.

3. An evaluation config JSON.
   - Top-level keys are attribute names such as `cell_line`, `cell_type`, `disease`, `drug`, `tissue`, `knockout_gene`, `knockdown_gene`, and `overexpressed_gene`.
   - Each attribute defines:
     - `ontology_file`
     - `base_uri`
     - `props_for_dump`
     - `prompt_mapped`
     - `prompt_non_mapped`

4. A llama.cpp chat completions endpoint URL.
   - Typical URL:
     ```text
     http://localhost:11438/v1/chat/completions
     ```

## Output

The evaluator prints TSV rows to stdout. The current intended columns are:

1. BioSample accession.
2. Mapped ontology term ID.
3. Mapped ontology term label.
4. Evaluator decision, `true` or `false`.
5. Probability of the emitted first token.
6. Normalized probability within exactly matching `true` and `false` candidates, when available.

Warnings and progress messages should go to stderr.

## LLM Logprob Notes

The emitted first-token probability is not a clean confidence score for the biological judgment. It is the probability of the exact token emitted by the model/API.

llama.cpp may show candidates such as `" false"` or `" true"` in `top_logprobs`, while the final response content is normalized by `response_format` to `"false"` or `"true"`. For the normalized two-choice score, this repository intentionally considers only exact token matches:

- `true`
- `false`

Do not fold in space-prefixed, capitalized, quoted, or newline-prefixed variants unless the user explicitly asks to change the score definition.

The payload currently uses `temperature: 0`, `logprobs: True`, and the existing `response_format` shape. The `response_format` may look odd, but it has been observed to work with the current llama.cpp setup; avoid changing it casually.

## Error-Handling Philosophy

This project is still small and intentionally strict in some places.

- Malformed TSV rows can fail fast; that usually indicates an upstream conversion issue.
- Missing or invalid `config_attr` should produce a helpful error listing available attributes.
- Missing ontology terms are nuanced:
  - If all IDs are malformed due to `:` / `_` conversion issues, failing early is useful.
  - If only some terms are missing due to ontology version differences, continuing with warnings may be better.
  - Ask the user before changing this behavior.
- llama.cpp response JSON is currently assumed to match the expected structure. The user prefers failing fast if the server/model response shape changes unexpectedly.
- HTTP errors and timeouts are a known improvement area, but do not overhaul behavior without discussing it.

## Development Notes

- Prefer small, focused changes.
- Preserve existing CLI behavior unless the user asks for a format change.
- Do not modify untracked files unless explicitly requested.
- Keep generated files, local test data, and large ontology files out of commits unless the user explicitly asks.
- Use stderr for diagnostics and stdout for machine-readable TSV output.
- If adding or changing output columns, update README or tell the user that README is now stale.

## Useful Checks

Syntax-only checks that avoid creating `__pycache__`:

```sh
python -c "import ast, pathlib; ast.parse(pathlib.Path('bsllmner-evaluator.py').read_text())"
bash -n scripts/run_eval.sh
```

