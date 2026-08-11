import argparse
import csv
import json
import sys


def load_ids(tsv_file):
    ids = set()
    with open(tsv_file, "r", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row:
                continue
            ids.add(row[0])
    return ids


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Extract entries from bsllmner-mk2 select-output JSON file(s) '
            '(as passed to bsllmner-evaluator\'s -r) whose "extract.accession" '
            "value is listed in a TSV file's first column"
        )
    )
    parser.add_argument("tsv_file", help="Path to TSV file; 1st column holds accession IDs")
    parser.add_argument("mk2_output_files", nargs="+", help="Path(s) to bsllmner-mk2 select-output JSON file(s)")
    parser.add_argument("-o", "--output", help="Path to output JSON file (default: stdout)")

    args = parser.parse_args()
    ids = load_ids(args.tsv_file)

    # bsllmner-mk2 select-output JSON is either a bare list of entries or a dict
    # with an "entries" key (mirrors select_result_to_tsv.py's handling).
    is_dict_shaped = None
    extra_keys = {}
    filtered_entries = []
    for mk2_output_file in args.mk2_output_files:
        with open(mk2_output_file, "r") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if is_dict_shaped is None:
                is_dict_shaped = True
                extra_keys = {k: v for k, v in data.items() if k != "entries"}
            entries = data["entries"]
        else:
            if is_dict_shaped is None:
                is_dict_shaped = False
            entries = data
        for entry in entries:
            if entry.get("extract", {}).get("accession") in ids:
                filtered_entries.append(entry)

    result = {**extra_keys, "entries": filtered_entries} if is_dict_shaped else filtered_entries
    out = open(args.output, "w") if args.output else sys.stdout
    try:
        json.dump(result, out, indent=2, ensure_ascii=False)
        out.write("\n")
    finally:
        if args.output:
            out.close()
    return


if __name__ == "__main__":
    main()
