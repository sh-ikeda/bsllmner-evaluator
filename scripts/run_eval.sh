#!/usr/bin/bash
set -eux

SCRIPT_DIR=$(cd $(dirname $0) && pwd)
SELECT_RESULT_JSON=$1
shift
PREFIX=$1
shift
BS_JSON_DIR=$1
shift
if [ ! -d "$BS_JSON_DIR" ]; then
    echo "Error: Directory '$BS_JSON_DIR' does not exist."  >&2
    exit 1
fi

for attr in "$@"; do
    python $SCRIPT_DIR/select_result_to_tsv.py $SELECT_RESULT_JSON $attr > ${PREFIX}_result_${attr}.tsv
    awk -F "\t" '$3&&!a[$2 $3 $4]++' ${PREFIX}_result_${attr}.tsv > ${PREFIX}_result_${attr}_uniq.tsv
    awk -F "\t" -vOFS="\t" '$3&&!a[$2 $3 $4]++{print $1,gensub(":","_","g",$3),$2}' ${PREFIX}_result_${attr}.tsv > ${PREFIX}_result_${attr}_uniq_pairs.tsv
    wc -l ${PREFIX}_result_${attr}_uniq_pairs.tsv >&2
    cut -f 1 ${PREFIX}_result_${attr}_uniq_pairs.tsv | while read id; do wget -q -nc -P $BS_JSON_DIR/$attr https://ddbj.nig.ac.jp/search/entry/biosample/$id.json || true ; done
    awk -F "\t" -v dir=$BS_JSON_DIR/$attr '{print dir "/" $1 ".json"}' ${PREFIX}_result_${attr}_uniq_pairs.tsv | xargs file 2>/dev/null | grep -v "cannot open" | cut -d: -f1 | xargs jq '.properties.BioSample | {accession} + ({"Title": .Description.Title}) + ({"Description": .Description.Comment?.Paragraph?}| del(.Description | select(. == null))) + ([.Attributes.Attribute? // []] | flatten | map({key: .attribute_name, value: .content}) | from_entries)' | jq -s > ${PREFIX}-results-check-${attr}.llmin.json
    python $SCRIPT_DIR/../bsllmner-evaluator.py -c $SCRIPT_DIR/../input/evaluation_config.json -r ${PREFIX}_result_${attr}_uniq_pairs.tsv -a $attr -b ${PREFIX}-results-check-${attr}.llmin.json -u http://localhost:11438/v1/chat/completions > eval_result_${PREFIX}_${attr}.tsv
done