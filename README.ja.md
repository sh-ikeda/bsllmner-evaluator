# bsllmner-evaluator
[bsllmner-mk2](https://github.com/dbcls/bsllmner-mk2) の出力を LLM で評価するツール

[English](README.md)

## 必要環境
Python 3 と `requirements.txt` のパッケージ:
```
pip install -r requirements.txt
```

## 使い方
```
python bsllmner-evaluator.py -c input/evaluation_config.json -r bsllmner-result.tsv -a attr -b biosample.json -u http://localhost:11438/v1/chat/completions
```
llama.cpp サーバーがポート 11438 で待ち受けていることを想定しています。

`-r` には bsllmner-mk2 の select 出力 JSON ファイルも指定できます:

```
python bsllmner-evaluator.py -c input/evaluation_config.json -r examples/select_output_sample.json -a attr -b biosample.json -u http://localhost:11438/v1/chat/completions
```

## 引数
`-c`: evaluation_config.json のパス
`-r`: bsllmner-mk2 の出力から変換した TSV ファイル、または bsllmner-mk2 の select 出力 JSON ファイルのパス。
`--evaluation_target_format`: `-r` の入力形式。`auto`、`tsv`、`json` のいずれか。デフォルトは `auto`。
`-a`: この実行で評価する属性（例: `cell_line`、`tissue`）。`evaluation_config.json` に定義されている必要があります。
`-b`: 元の BioSample データの JSON ファイル（拡張子が `.jsonl` の場合は JSON Lines）のパス。
`--error_category_file`: エラーカテゴリを定義した JSON ファイルのパス。デフォルトは `input/error_categories.json`。
`-u`: llama.cpp の `/v1/chat/completions` エンドポイントの URL。
`-v`: 行ごと・カテゴリごとの進捗を標準エラー出力に表示します。
`--bool_only`: 1 段目のマッピング正否判定（`mapping_decision` とその確率）だけを行い、extraction/selection のカテゴリ分類は一切行いません。このとき出力 TSV は最初の 7 列のみとなり、`--error_category_file` は読み込まれません。

## フォーマット
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
拡張子が `.jsonl` の場合は JSON Lines として読み込みます。1 行に 1 つの BioSample レコード（上と同じ形のオブジェクト）を書く形式で、内容は JSON 配列の形式と同等です。
### TSV に変換した bsllmner-mk2 の結果
```tsv
SAMD00004141	HeLa	CVCL_0030
SAMD00008684	SH-SY5Y	CVCL_0019
SAMD00009960	Ramos	CVCL_0597
```
BioSample ID、抽出された値、マッピングされたオントロジー項目 ID の 3 つ組です。項目 ID の人間向けラベルを 4 列目に書いても受け付けますが、使用はされません。
### 出力
ヘッダー行付きの TSV です。最初の 7 列は固定です:

1. `accession`
2. `extracted_value`
3. `term_id`
4. `term_label`
5. `mapping_decision` — マッピング（またはマッピングしなかったこと）が正しいと本プログラムが判定したかどうか。
6. `mapping_probability` — 出力された最初のトークンの確率。
7. `mapping_normalized_probability` — 完全一致する `true` と `false` の候補の中で正規化した確率（算出できた場合）。

その後に、`input/error_categories.json` で定義されたエラーカテゴリごとに 4 列が続きます（まず `extraction` の全カテゴリ、次に `selection` の全カテゴリを、ファイル内の順に並べます）: `{category_id}_decision`、`{category_id}_probability`、`{category_id}_normalized_probability`、`{category_id}_reason`。`--bool_only` を指定した場合、これらの列はすべて省略されます。

各カテゴリは独立した yes/no の質問（「このカテゴリの説明は当てはまるか？」）として問い合わせるため、すべてのカテゴリがそれぞれ判定を持ちます。段階ごとにカテゴリを 1 つだけ選ぶ形ではありません。extraction カテゴリは、`mapping_decision` が `false` で、かつ `term_id` が空でない場合に問い合わせます。それ以外の場合は（カテゴリを問い合わせていないので）列はすべて空になります。selection カテゴリも同じ条件で問い合わせますが、もう 1 つ条件があります。JSON 入力では、bsllmner-mk2 がオントロジー検索/text2term の完全一致（Stage 2）で解決した値は LLM による選択ステップ（Stage 3）に到達していないため、その値については selection カテゴリを問い合わせません。これは select 出力 JSON の `select_timings` フィールドから判定します（そこに値がなければ、その値について Stage 3 は呼ばれていません）。TSV 入力にはこうしたパイプラインの詳細が含まれないため、selection カテゴリは extraction と同じ条件で常に問い合わせます。`probability`/`normalized_probability` は 6/7 列目と同じ定義で、そのカテゴリの `true`/`false` の判定トークンについて計算したものです。`reason` はモデルによる短い 1 文の説明です。

selection カテゴリのうち `selection_failed_to_reject` と `selection_better_candidate_available` の 2 つは、さらに、その値について bsllmner-mk2 の Stage 3 選択ステップが実際に選ぶ対象とした候補リストに基づいて判定します。評価器は select 出力 JSON の `search_results` と `text2term_results` フィールドからこのリストを再構成し（bsllmner-mk2 自身の候補マージと同様に、マージして term_id で重複を除きます）、プロンプトに含めます。これにより、モデルが「どんな候補があり得たか」を推測するのではなく、「このリストの中に正しい候補があったか」を判定させます。候補リストを再構成できない場合（パイプラインの詳細を含まない TSV 入力や、search/text2term の結果が記録されていない JSON の値）は、この 2 カテゴリは問い合わせず、列は空のままになります。もう 1 つの selection カテゴリ（`selection_valid`）はこれまでどおり問い合わせます。

```tsv
accession	extracted_value	term_id	term_label	mapping_decision	mapping_probability	mapping_normalized_probability	extraction_type_mismatch_decision	extraction_type_mismatch_probability	extraction_type_mismatch_normalized_probability	extraction_type_mismatch_reason	...	extraction_valid_decision	extraction_valid_probability	extraction_valid_normalized_probability	extraction_valid_reason	selection_failed_to_reject_decision	selection_failed_to_reject_probability	selection_failed_to_reject_normalized_probability	selection_failed_to_reject_reason	...
SAMD00004141	HeLa	CVCL_0030	HeLa	true	0.872	0.914											
SAMD00008684	SH-SY5Y	CVCL_0019	SH-SY5Y	false	0.468	0.731	false	0.81	0.81	The extracted value correctly matches the cell_line attribute.	...	true	0.93	0.97	The extracted value is appropriate for the evaluated attribute.	true	0.81	0.88	The candidates did not contain a term well supported by the sample metadata.	...
```

## スクリプト
`scripts/` 以下の補助スクリプトです。引数は各スクリプトを `-h` 付きで実行すると確認できます（`run_eval.sh` を除く）。

- `run_eval.sh SELECT_RESULT_JSON PREFIX BS_JSON_DIR ATTR...`: 一括実行用のパイプライン。属性ごとに、bsllmner-mk2 の select 出力 JSON を評価対象の TSV に変換し、DDBJ Search から BioSample JSON を `BS_JSON_DIR/ATTR/` に取得して上記の BioSample JSON 形式に変換したうえで、`http://localhost:11438/v1/chat/completions` に対して評価器を実行します。`wget` と `jq` が必要です。
- `select_result_to_tsv.py`: bsllmner-mk2 の select 出力 JSON を、1 つの属性について accession、抽出された値、項目 ID、項目ラベルの TSV に変換します。
- `select_result_v1_to_tsv.py`: 上と同じ処理を、旧形式（v1）の select 出力 JSON に対して行います。
- `filter_mk2_output_by_tsv_ids.py`: bsllmner-mk2 の select 出力 JSON ファイルから、accession が TSV の 1 列目に含まれるエントリを抽出します。
- `filter_jsonl_by_tsv_ids.py`: JSON Lines ファイルから、accession が TSV の 1 列目に含まれる BioSample レコードを抽出し、各レコードをトップレベルの `Description`/`Attributes`/`Ids`/`accession` の形に正規化します。
- `find_exact_match_overridden_by_text2term.py`: bsllmner-mk2 の select 出力 JSON から、`search_results` で複数の項目が完全一致したにもかかわらず、採用された項目が text2term 由来だった属性値を見つけます。
- `dedup_matches_by_attr_value.py`: `find_exact_match_overridden_by_text2term.py` の出力から重複を除き、（属性, 値）の組ごとに最初のサンプルだけを残します。
