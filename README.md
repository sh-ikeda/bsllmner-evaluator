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
`-b`: Path to the JSON file of the original BioSample datasets.
`--error_category_file`: Path to the JSON file defining error categories. Default is `input/error_categories.json`.

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
### TSV-converted bsllmner-mk2 result
```tsv
SAMD00004141	HeLa	CVCL_0030
SAMD00008684	SH-SY5Y	CVCL_0019
SAMD00009960	Ramos	CVCL_0597
```
Triples of BioSample IDs, extracted values, and mapped ontology term IDs.
### Output
```tsv
SAMD00004141	HeLa	CVCL_0030	HeLa	true	0.872	0.914
SAMD00008684	SH-SY5Y	CVCL_0019	SH-SY5Y	false	0.468	0.731	selection_failed_to_reject	The candidates did not contain a term well supported by the sample metadata.
SAMD00009960	Ramos	CVCL_0597	Ramos	true	0.699	0.842
```
- BioSample ID
- Extracted value
- Mapped ontology term ID
- Mapped ontology term label
- Decision of this program. Whether the mapping is correct or not.
- Probability of the emitted first token.
- Normalized probability within exactly matching `true` and `false` candidates, when available.
- Error category ID. This is emitted only when the decision is `false`.
- Error category reason. This is emitted only when the decision is `false`.
