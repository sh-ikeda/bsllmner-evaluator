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
            sample_id = sample["extract"]["accession"]
            mapped_id = ""
            mapped_label = ""
            if attr in results:
                for mapped_term in results[attr]:
                    if "term_id" in mapped_term:
                        mapped_id = mapped_term["term_id"]
                        mapped_label = mapped_term["label"]
                        extracted_str = mapped_term["value"]
                    print(sample_id, extracted_str, mapped_id, mapped_label, sep="\t")
                if not results[attr]:
                    print(sample_id, "", "", "", sep="\t")
            else:
                print(sample_id, sample["extract"]["extracted"][attr], "", "", sep="\t")
    return

if __name__ == "__main__":
    main()