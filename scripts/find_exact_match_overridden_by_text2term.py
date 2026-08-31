import argparse
import json
import sys


def find_matches(entry):
    accession = entry.get("extract", {}).get("accession")
    search_results = entry.get("search_results") or {}
    text2term_results = entry.get("text2term_results") or {}
    results = entry.get("results") or {}

    matches = []
    for attr, by_value in search_results.items():
        for value, candidates in by_value.items():
            exact_ids = {c["term_id"] for c in candidates if c.get("exact_match") and "term_id" in c}
            if len(exact_ids) <= 1:
                continue
            all_ids = {c["term_id"] for c in candidates if "term_id" in c}
            overridden = [
                chosen
                for chosen in results.get(attr, [])
                if chosen.get("value") == value and chosen.get("term_id") not in all_ids
            ]
            if overridden:
                matches.append(
                    {
                        "accession": accession,
                        "attr": attr,
                        "value": value,
                        "search_results": candidates,
                        "text2term_results": text2term_results.get(attr, {}).get(value, []),
                        "results": overridden,
                    }
                )
    return matches


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract accession/value pairs from bsllmner-mk2 select-output JSON where, "
            "for some attribute, multiple distinct terms exact-matched in search_results, "
            "but the term adopted into results is not among those search_results "
            "candidates at all (i.e. it was picked via text2term rather than any of the "
            "exact-matched candidates). Only the accession, extracted value, and the "
            "search_results/text2term_results/results data for that attribute/value are "
            "kept; unrelated attributes are omitted."
        )
    )
    parser.add_argument("select_result_file", help="Path to json file output by bsllmner-mk2-select")
    parser.add_argument("-o", "--output", help="Path to output JSON file (default: stdout)")

    args = parser.parse_args()
    with open(args.select_result_file, "r") as f:
        data = json.load(f)

    # bsllmner-mk2 select-output JSON is either a bare list of entries or a dict
    # with an "entries" key (mirrors select_result_to_tsv.py's handling).
    entries = data["entries"] if isinstance(data, dict) else data

    matched = []
    for entry in entries:
        matched.extend(find_matches(entry))

    out = open(args.output, "w") if args.output else sys.stdout
    try:
        json.dump(matched, out, indent=2, ensure_ascii=False)
        out.write("\n")
    finally:
        if args.output:
            out.close()
    return


if __name__ == "__main__":
    main()
