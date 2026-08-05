# bsllmner-evaluator
Evaluate outputs of [bsllmner-mk2](https://github.com/dbcls/bsllmner-mk2) with LLMs

## Usage
```
python bsllmner-evaluator.py -c input/evaluation_config.json -r bsllmner-result.tsv -a attr -b biosample.json -u http://localhost:11438/v1/chat/completions
```
The llama.cpp server is assumed to be listening at the port 11438.

The `-r` input can also be a bsllmner-mk2 select-output JSON file:

```
python bsllmner-evaluator.py -c input/evaluation_config.json -r examples/select_output_sample.json -a attr -b biosample.json -u http://localhost:11438/v1/chat/completions
```

## Arguments
`-c`: Path to evaluation_config.json
`-r`: Path to the TSV file converted from bsllmner-mk2 output, or to a bsllmner-mk2 select-output JSON file.
`--evaluation_target_format`: Input format for `-r`: `auto`, `tsv`, or `json`. Default is `auto`.
`-a`: The attribute to evaluate in this run, e.g. `cell_line` or `tissue`. The attribute must be defined in `evaluation_config.json`.
`-b`: Path to the JSON (or JSON Lines, if the file extension is `.jsonl`) file of the original BioSample datasets.
`--error_category_file`: Path to the JSON file defining error categories. Default is `input/error_categories.json`.
`--bool_only`: Only run the first-pass mapping correctness judgment (`mapping_decision` and its probabilities); skip the extraction/selection category classification pass entirely. The output TSV then has only the first 7 columns, and `--error_category_file` is not read.

## Format
### BioSample JSON
```json
[
  {
    "accession": "SAMD00004141",
    "Title": "Hela_Ser2P/Ser5P/Ser7P-RNAP2_ChIPSeq",
    "sample_name": "DRS000576",
    "sample comment": "Hela cells which were cultured in Dulbecco's modified Eagle's medium (DMEM) supplemented with 10% fetal bovine serum under a humidified atmosphere with 5% CO2 at 37°C."
  },
  {
    "accession": "SAMD00008684",
    "Title": "SH-SY5Y ChIP",
    "sample_name": "DRS000579",
    "sample comment": "Source of DNA used for sequencing was ChIP samples from SH-SY5Y cells using anti-DJ-1 antibody.",
    "cell type": "SH-SY5Y cells"
  }
]
```
If the file extension is `.jsonl`, it is instead read as JSON Lines: one BioSample record (the same object shape as above) per line, equivalent to the JSON array form.
### TSV-converted bsllmner-mk2 result
```tsv
SAMD00004141	HeLa	CVCL_0030
SAMD00008684	SH-SY5Y	CVCL_0019
SAMD00009960	Ramos	CVCL_0597
```
Triples of BioSample IDs, extracted values, and mapped ontology term IDs.
### Output
A TSV with a header row. The first 7 columns are fixed:

1. `accession`
2. `extracted_value`
3. `term_id`
4. `term_label`
5. `mapping_decision` — whether this program judged the mapping (or non-mapping) correct.
6. `mapping_probability` — probability of the emitted first token.
7. `mapping_normalized_probability` — normalized probability within exactly matching `true` and `false` candidates, when available.

After that, there are 4 columns per error category defined in `input/error_categories.json` (first all `extraction` categories, then all `selection` categories, in the order they appear in that file): `{category_id}_decision`, `{category_id}_probability`, `{category_id}_normalized_probability`, `{category_id}_reason`. These columns are omitted entirely when `--bool_only` is given.

Each category is asked as an independent yes/no question ("does this category's description apply?"), so every category gets its own judgment — there is no single chosen category per stage. Both extraction and selection categories are asked whenever `mapping_decision` is `false` and `term_id` is not empty; all of their columns are empty otherwise (the categories were never asked). `probability`/`normalized_probability` follow the same definition as columns 6/7, computed for that category's `true`/`false` decision token; `reason` is one short sentence from the model.

```tsv
accession	extracted_value	term_id	term_label	mapping_decision	mapping_probability	mapping_normalized_probability	extraction_wrong_attribute_decision	extraction_wrong_attribute_probability	extraction_wrong_attribute_normalized_probability	extraction_wrong_attribute_reason	...	extraction_valid_decision	extraction_valid_probability	extraction_valid_normalized_probability	extraction_valid_reason	selection_failed_to_reject_decision	selection_failed_to_reject_probability	selection_failed_to_reject_normalized_probability	selection_failed_to_reject_reason	...
SAMD00004141	HeLa	CVCL_0030	HeLa	true	0.872	0.914											
SAMD00008684	SH-SY5Y	CVCL_0019	SH-SY5Y	false	0.468	0.731	false	0.81	0.81	The extracted value correctly matches the cell_line attribute.	...	true	0.93	0.97	The extracted value is appropriate for the evaluated attribute.	true	0.81	0.88	The candidates did not contain a term well supported by the sample metadata.	...
```
