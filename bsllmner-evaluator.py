import sys
import argparse
import re
import json
import time
import requests
from math import exp
from owlready2 import get_ontology


def dump_owl_term(ontology, term_id):
    props_for_dump = ["label", "hasRelatedSynonym", "inSubset", "comment"]
    dump_str = ""
    ns = ontology.get_namespace("http://purl.obolibrary.org/obo/Cellosaurus#")
    term = ns[term_id]

    # props = term.get_properties(term)
    # for prop in props:
    #     prop_name = prop.python_name
    #     if prop_name in props_for_dump:
    #         dump_str += f"{prop_name}: {prop[term]}\n"
    for prop in props_for_dump:
        values = getattr(term, prop)
        dump_str += f"{prop}: {values}\n"

    return dump_str

def get_label(ontology, term_id):
    ns = ontology.get_namespace("http://purl.obolibrary.org/obo/Cellosaurus#")
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

def build_prompt(sample, term_str):
    prompt = f"""Here is metadata of a sample that was used for a biological experiment.
{sample}

Is the statement below is correct? Output only true or false in lowercase.
"""
    if term_str == "":
        prompt += "Statement:\nThis sample does not mention the specific cell line name that represents the sample itself."
    else:
        prompt += f"""Statement:
The sample is a cell line below.
{term_str}
"""
    return prompt

def eval_mappings(ontology, mapping_result_dict, biosample_json_file, url):
    with open(biosample_json_file, "r") as f:
        samples = json.load(f)
        for sample in samples:
            bs_id = sample["accession"]
            for term_id in mapping_result_dict[bs_id]:
                if term_id == "":
                    prompt = build_prompt(sample, "")
                    term_label = ""
                else:
                    prompt = build_prompt(sample, dump_owl_term(ontology, term_id))
                    term_label = get_label(ontology, term_id)
                # print(prompt)
                headers = {
                    "Content-Type": "application/json"
                }

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

def main():
    parser = argparse.ArgumentParser(description='evaluate ontology mapping results')
    parser.add_argument('owl_file', help='Path to ontology OWL file')
    parser.add_argument('evaluation_target_file', help='Path to tsv file containing evaluation target')
    parser.add_argument('biosample_json_file', help='Path to input biosample JSON file')
    parser.add_argument('url', help='URL of llama.cpp endpoint')

    args = parser.parse_args()
    try:
        # Load ontology
        print("Loading ontology...", file=sys.stderr)
        start_time = time.time()
        ontology = get_ontology(f"file://{args.owl_file}").load()
        total_time = time.time() - start_time
        print(f"Ontology loaded in {total_time:.2f} seconds", file=sys.stderr)
        # term_id = "CVCL_3526"
        # print(dump_owl_term(ontology, term_id))
        mapping_result_dict = load_target_tsv(args.evaluation_target_file)

        print("Performing evaluation...", file=sys.stderr)
        start_time = time.time()
        eval_mappings(ontology, mapping_result_dict, args.biosample_json_file, args.url)
        total_time = time.time() - start_time
        print(f"Evaluation completed in {total_time:.2f} seconds", file=sys.stderr)
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()