import argparse
import json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('select_result_file', help='Path to json file output by bsllmner-mk2-select')
    parser.add_argument('attr', help='Attribute to be extracted')

    args = parser.parse_args()
    attr = args.attr
    with open(args.select_result_file, "r") as f:
        samples = json.load(f)
        for sample in samples:
            results = sample["results"]
            mapped_id = ""
            mapped_label = ""
            if attr in results:
                for extracted_str in results[attr]:
                    if "term_id" in results[attr][extracted_str]:
                        mapped_id = results[attr][extracted_str]["term_id"]
                        mapped_label = results[attr][extracted_str]["label"]
                    print(sample["accession"], extracted_str, mapped_id, mapped_label, sep="\t")
                if not results[attr]:
                    print(sample["accession"], sample["extract_output"][attr], "", "", sep="\t")
            else:
                print(sample["accession"], "", "", "", sep="\t")
    return

if __name__ == "__main__":
    main()