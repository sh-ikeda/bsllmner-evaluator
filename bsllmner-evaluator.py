import sys
import argparse
import json
import time
import requests
from math import exp
from owlready2 import get_ontology


def dump_owl_term(ontology, term_id, base_uri, props_for_dump):
    dump_str = ""
    ns = ontology.get_namespace(base_uri)
    term = ns[term_id]

    for prop in props_for_dump:
        values = getattr(term, prop)
        dump_str += f"  {prop}: {values}\n"

    return dump_str

def get_label(ontology, term_id, base_uri):
    ns = ontology.get_namespace(base_uri)
    term = ns[term_id]
    return term.label[0]

def load_target_tsv(tsv_file):
    mapping_result_dict = {}
    with open(tsv_file, "r") as f:
        for line in f:
            sep_line = line.strip(' \n\r').split('\t')
            if sep_line[0] in mapping_result_dict:
                mapping_result_dict[sep_line[0]].append(sep_line[1])
            else:
                mapping_result_dict[sep_line[0]] = [sep_line[1]]
    return mapping_result_dict

def build_prompt(sample, term_str, config):
    if term_str == "":
        prompt = config["prompt_non_mapped"]
    else:
        prompt = config["prompt_mapped"]
    prompt = prompt.replace("{sample}", json.dumps(sample, indent=4)).replace("{term}", term_str)
    return prompt

def eval_mappings(ontology, mapping_result_dict, biosample_json_file, url, config):
    headers = {"Content-Type": "application/json"}

    with open(biosample_json_file, "r") as f:
        samples = json.load(f)
        for sample in samples:
            bs_id = sample["accession"]
            for term_id in mapping_result_dict[bs_id]:
                if term_id == "":
                    prompt = build_prompt(sample, "", config)
                    term_label = ""
                else:
                    prompt = build_prompt(sample, dump_owl_term(ontology, term_id, config["base_uri"], config["props_for_dump"]), config)
                    term_label = get_label(ontology, term_id, config["base_uri"])

                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "chat_template_kwargs": {
                        "enable_thinking": False
                    },
                    "response_format": {
                        "type": "json_object",
                        "schema": {
                            "type": "boolean"
                        }
                    },
                    "logprobs": True
                }
                response = requests.post(url, headers=headers, json=payload)
                data = response.json()["choices"][0]
                print(bs_id, term_id, term_label, data["message"]["content"], exp(data["logprobs"]["content"][0]["logprob"]), sep="\t")

    return

def load_config(config_file):
    with open(config_file, "r") as f:
        config = json.load(f)
    return config

def main():
    parser = argparse.ArgumentParser(description='evaluate ontology mapping results')
    parser.add_argument("-r", '--evaluation_target_file', help='Path to tsv file containing evaluation target', required=True)
    parser.add_argument("-b", '--biosample_json_file', help='Path to input biosample JSON file', required=True)
    parser.add_argument("-c", '--config_file', help='Path to config file', required=True)
    parser.add_argument("-u", '--url', help='URL of llama.cpp endpoint', required=True)

    args = parser.parse_args()
    try:
        # Load ontology
        print("Loading ontology...", file=sys.stderr)
        start_time = time.time()
        config = load_config(args.config_file)
        ontology_file = config["ontology_file"]
        ontology = get_ontology(f"file://{ontology_file}").load()
        total_time = time.time() - start_time
        print(f"Ontology loaded in {total_time:.2f} seconds", file=sys.stderr)
        mapping_result_dict = load_target_tsv(args.evaluation_target_file)

        print("Performing evaluation...", file=sys.stderr)
        start_time = time.time()
        eval_mappings(ontology, mapping_result_dict, args.biosample_json_file, args.url, config)
        total_time = time.time() - start_time
        print(f"Evaluation completed in {total_time:.2f} seconds", file=sys.stderr)
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()