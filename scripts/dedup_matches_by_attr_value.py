import argparse
import json
import sys


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Deduplicate the match list produced by "
            "find_exact_match_overridden_by_text2term.py, keeping only the first "
            "sample encountered for each (attr, value) pair."
        )
    )
    parser.add_argument(
        "matches_file", help="Path to json file output by find_exact_match_overridden_by_text2term.py"
    )
    parser.add_argument("-o", "--output", help="Path to output JSON file (default: stdout)")

    args = parser.parse_args()
    with open(args.matches_file, "r") as f:
        matches = json.load(f)

    seen = set()
    deduped = []
    for match in matches:
        key = (match.get("attr"), match.get("value"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(match)

    out = open(args.output, "w") if args.output else sys.stdout
    try:
        json.dump(deduped, out, indent=2, ensure_ascii=False)
        out.write("\n")
    finally:
        if args.output:
            out.close()
    return


if __name__ == "__main__":
    main()
