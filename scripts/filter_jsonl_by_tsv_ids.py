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
        description="Extract JSON Lines whose \"accession\" value is listed in a TSV file's first column"
    )
    parser.add_argument("tsv_file", help="Path to TSV file; 1st column holds accession IDs")
    parser.add_argument("jsonl_files", nargs="+", help="Path(s) to JSON Lines file(s) to filter")
    parser.add_argument("-o", "--output", help="Path to output file (default: stdout)")

    args = parser.parse_args()
    ids = load_ids(args.tsv_file)

    out = open(args.output, "w") if args.output else sys.stdout
    try:
        for jsonl_file in args.jsonl_files:
            with open(jsonl_file, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    record = json.loads(stripped)
                    if record.get("accession") in ids:
                        out.write(line if line.endswith("\n") else line + "\n")
    finally:
        if args.output:
            out.close()
    return


if __name__ == "__main__":
    main()
