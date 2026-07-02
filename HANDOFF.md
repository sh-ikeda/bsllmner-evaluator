# Handoff Notes

This repository is `bsllmner-evaluator`, an evaluator for ontology mappings produced by `bsllmner-mk2`.

## Upstream Context

`bsllmner-mk2` normalizes BioSample experiment metadata by:

1. Extracting attribute-specific strings from irregular BioSample JSON metadata.
2. Searching ontology candidates for each extracted value.
   - Exact label/synonym and n-gram matching.
   - Fuzzy matching via text2term.
3. Selecting the final ontology term with an LLM, or abstaining when no candidate is appropriate.

The evaluator checks whether the final mapping is appropriate for the original BioSample metadata. The goal has expanded from simple true/false mapping evaluation to error classification that can guide upstream `bsllmner-mk2` improvements.

## Current Evaluator Flow

For each target mapping:

1. Judge whether the final mapping/non-mapping decision is correct.
   - Uses the existing attribute-specific `prompt_mapped` or `prompt_non_mapped` in `input/evaluation_config.json`.
   - Boolean output is still expected to be only `true` or `false`.
   - Logprob handling still considers only exact `true` and `false` tokens.

2. If the mapping decision is `true`, output the row and do no error classification.

3. If the mapping decision is `false` and the mapped term ID is empty, stop after the non-mapped true/false judgment.
   - Missing/non-mapped cases are intentionally not deeply classified for now to avoid increasing runtime too much.

4. If the mapping decision is `false` and the mapped term ID is not empty, classify the extraction first.
   - The extraction classifier chooses one category from `input/error_categories.json` under `extraction`.
   - It can return `extraction_valid`.

5. If extraction category is `extraction_valid`, classify the downstream selection error.
   - The selection classifier chooses one category from `input/error_categories.json` under `selection`.
   - If extraction is not valid, selection classification is skipped.

## Input Formats

`-r/--evaluation_target_file` supports two formats.

### TSV

TSV is now expected to have three columns:

```tsv
BioSample accession    extracted value    mapped ontology term ID
```

The older two-column TSV format is no longer accepted.

### bsllmner-mk2 JSON

The evaluator can also read a bsllmner-mk2 select-output JSON list. For mapped results, the extraction value is taken from:

```text
results[config_attr][].value
```

If `results` does not contain the evaluated attribute, this is treated as an empty final mapping. This accommodates the known upstream issue where keys such as `"drug": []` may be omitted.

## Output Columns

Current TSV output columns are:

1. BioSample accession.
2. Extracted value.
3. Mapped ontology term ID.
4. Mapped ontology term label.
5. Mapping decision, `true` or `false`.
6. Probability of the emitted first token.
7. Normalized probability within exact `true`/`false` top-logprob candidates.
8. Extraction category.
9. Extraction reason.
10. Selection category.
11. Selection reason.

Classification reason fields are one short sentence. Tabs and newlines are replaced with spaces before TSV output.

## Error Categories

`input/error_categories.json` currently has this top-level structure:

```json
{
  "extraction": [...],
  "selection": [...]
}
```

Extraction categories include:

- `extraction_valid`
- `extraction_wrong_attribute`
- `extraction_non_sample_entity`
- `extraction_abbreviation_overresolved`
- `extraction_partial_or_boundary_error`
- `extraction_unsupported_inference`
- `ambiguous_source_metadata`
- `other`

Selection categories include:

- `selection_failed_to_reject`
- `selection_label_similarity_over_context`
- `selection_partial_match_accepted`
- `selection_granularity_error`
- `ontology_gap_or_version_issue`
- `evaluator_false_negative`
- `other`

Important design decisions:

- Candidate generation can produce wrong candidates; that is expected. If such a candidate survives to the final output, the responsibility is treated as a selection problem unless extraction was already wrong.
- If extraction is already wrong, classify the error as extraction-related and do not continue to selection classification.
- `ambiguous_source_metadata` is for cases where the BioSample metadata itself is contradictory or unclear, e.g. different cell lines in `source_name` and `cell line`.
- `extraction_non_sample_entity` includes cases where a source or stem cell line is mentioned but the actual sample is a differentiated cell derived from it.
- `evaluator_false_negative` is for cases where the evaluator incorrectly judged a truly appropriate mapping as false.

## Prompt Notes

Classification prompts are JSON-output prompts with:

```json
{
  "category": "category_id",
  "reason": "One short sentence."
}
```

The parser prefers strict JSON but has a tolerant fallback that extracts a known category ID from non-exact model output.

The first-pass boolean evaluator keeps the existing llama.cpp payload shape, including:

- `temperature: 0`
- `logprobs: True`
- the current `response_format` shape

Do not casually change this payload; it was observed to work with the current llama.cpp setup.

## Recent Implementation Notes

Recent code changes added:

- JSON target input support.
- Three-column TSV input support.
- Extraction value in output TSV.
- Two-stage extraction/selection classification.
- Classification reasons.
- File-name-aware JSON parse errors.
- English comments in `bsllmner-evaluator.py` marking major pipeline steps.

## Validation Commands

Useful checks that have been used:

```sh
python -c "import ast, pathlib; ast.parse(pathlib.Path('bsllmner-evaluator.py').read_text())"
bash -n scripts/run_eval.sh
python -m json.tool input/error_categories.json
```

Full llama.cpp execution was not always run during code edits.

## Working Tree Notes

At the time this handoff file was created, tracked files appeared clean before adding this file. Several local/generated/test files were untracked, including `AGENTS.md`, example JSON files, local input data, images, and experimental scripts. Do not add or edit those unless explicitly requested.
