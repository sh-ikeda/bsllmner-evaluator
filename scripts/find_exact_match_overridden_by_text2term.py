import argparse
import json
import sys


def entry_matches(entry):
    search_results = entry.get("search_results") or {}
    results = entry.get("results") or {}

    for attr, by_value in search_results.items():
        for value, candidates in by_value.items():
            exact_ids = {c["term_id"] for c in candidates if c.get("exact_match") and "term_id" in c}
            if len(exact_ids) <= 1:
                continue
            all_ids = {c["term_id"] for c in candidates if "term_id" in c}
            for chosen in results.get(attr, []):
                if chosen.get("value") != value:
                    continue
                if chosen.get("term_id") not in all_ids:
                    return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract entries from bsllmner-mk2 select-output JSON where, for some "
            "attribute/value, multiple distinct terms exact-matched in search_results, "
            "but the term adopted into results is not among those search_results "
            "candidates at all (i.e. it was picked via text2term rather than any of the "
            "exact-matched candidates)."
        )
    )
    parser.add_argument("select_result_file", help="Path to json file output by bsllmner-mk2-select")
    parser.add_argument("-o", "--output", help="Path to output JSON file (default: stdout)")

    args = parser.parse_args()
    with open(args.select_result_file, "r") as f:
        data = json.load(f)

    # bsllmner-mk2 select-output JSON is either a bare list of entries or a dict
    # with an "entries" key (mirrors select_result_to_tsv.py's handling).
    is_dict_shaped = isinstance(data, dict)
    entries = data["entries"] if is_dict_shaped else data

    matched = [entry for entry in entries if entry_matches(entry)]

    result = {"entries": matched} if is_dict_shaped else matched
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
