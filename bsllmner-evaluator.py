import sys
import argparse
import json
import time
import requests
from math import exp
from owlready2 import get_ontology
from pathlib import Path


class UserInputError(Exception):
    pass


def load_json_file(json_file, description):
    # Attach the file role and path to JSON parse errors so CLI failures are actionable.
    try:
        with open(json_file, "r") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise UserInputError(f"Failed to parse {description} JSON '{json_file}': {e}") from e


def dump_owl_term(ontology, term_id, base_uri, props_for_dump):
    # Keep ontology evidence compact; this string is inserted into the mapping prompt.
    dump_str = ""
    ns = ontology.get_namespace(base_uri)
    term = ns[term_id]

    for prop in props_for_dump:
        try:
            values = getattr(term, prop)
        except AttributeError as e:
            print(f"Error: {term}: {prop} is not found in the ontology ({e})", file=sys.stderr)
            continue
        dump_str += f"  {prop}: {values}\n"

    return dump_str

def get_label(ontology, term_id, base_uri):
    ns = ontology.get_namespace(base_uri)
    term = ns[term_id]
    return term.label[0]

def ontology_local_id(term_id):
    return term_id.replace(":", "_", 1)

def load_target_tsv(tsv_file):
    # TSV targets are already flattened: accession, extracted value, final mapped term ID.
    mapping_result_dict = {}
    with open(tsv_file, "r") as f:
        for line_number, line in enumerate(f, start=1):
            sep_line = line.strip(' \n\r').split('\t')
            if len(sep_line) != 3:
                raise UserInputError(
                    f"Malformed evaluation target TSV '{tsv_file}' line {line_number}: "
                    "expected 3 columns: BioSample accession, extracted value, mapped ontology term ID"
                )
            accession, extracted_value, term_id = sep_line
            target = {
                "term_id": term_id,
                "term_label": "",
                "extracted_value": extracted_value,
                "pipeline_record": None
            }
            if sep_line[0] in mapping_result_dict:
                mapping_result_dict[accession].append(target)
            else:
                mapping_result_dict[accession] = [target]
    return mapping_result_dict

def load_target_json(json_file, config_attr):
    # bsllmner-mk2 JSON preserves intermediate pipeline state for later error analysis.
    records = load_json_file(json_file, "evaluation target")

    mapping_result_dict = {}
    for record in records:
        accession = record["extract"]["accession"]
        results = record.get("results", {})
        attr_results = results.get(config_attr)
        entries = []

        if attr_results:
            for mapped_term in attr_results:
                entries.append({
                    "term_id": mapped_term.get("term_id", ""),
                    "term_label": mapped_term.get("label", ""),
                    "extracted_value": mapped_term.get("value", ""),
                    "pipeline_record": record
                })
        else:
            extracted = record.get("extract", {}).get("extracted")
            extracted_value = ""
            if isinstance(extracted, dict) and config_attr in extracted:
                extracted_value = extracted[config_attr]
            elif extracted is None:
                extracted_value = None
            entries.append({
                "term_id": "",
                "term_label": "",
                "extracted_value": extracted_value,
                "pipeline_record": record
            })

        mapping_result_dict[accession] = entries
    return mapping_result_dict

def detect_target_file_format(target_file):
    with open(target_file, "r") as f:
        first_char = f.read(1)
        while first_char and first_char.isspace():
            first_char = f.read(1)
    if first_char in ["[", "{"]:
        return "json"
    return "tsv"

def load_targets(target_file, config_attr, target_format):
    # Auto-detect JSON versus TSV so existing command lines keep working.
    if target_format == "auto":
        target_format = detect_target_file_format(target_file)
    if target_format == "json":
        return load_target_json(target_file, config_attr)
    return load_target_tsv(target_file)

def build_prompt(sample, term_str, config):
    # The first evaluator pass only judges the final mapping/non-mapping decision.
    if term_str == "":
        prompt = config["prompt_non_mapped"]
    else:
        prompt = config["prompt_mapped"]
    prompt = prompt.replace("{sample}", json.dumps(sample, indent=4)).replace("{term}", term_str)
    return prompt

def build_classification_prompt(sample, target, term_str, config_attr, error_categories, stage):
    # Classification prompts return both a machine-readable category and a short audit note.
    categories_text = "\n".join(
        f"- {category['id']}: {category['description']}"
        for category in error_categories
    )
    category_ids = ", ".join(category["id"] for category in error_categories)
    pipeline_context = build_pipeline_context(target.get("pipeline_record"), config_attr)
    extracted_value = format_tsv_value(target["extracted_value"])
    term_for_prompt = term_str if term_str else "(no final ontology term was mapped)"

    if stage == "extraction":
        stage_instruction = f"""\
An automatic metadata standarization pipeline using an LLM was instructed to extract \
the string(s) representing the sample.
As the "{config_attr}" attribute, the pipeline extracted "{extracted_value}".

Classify the validity of this extraction into exactly one category ID from the list below.

{categories_text}

Choose "extraction_valid" when the extracted value is appropriate for the evaluated \
attribute; otherwise choose the extraction error category that best explains why the \
extracted value itself is inappropriate.
Since the input metadata is manually written by submitters, it may not be well-formatted. \
Extraction should not be considered valid simply because the extracted value derives from \
the attribute in the input data that matches or is similar to "{config_attr}"."""

    else:
        stage_instruction = f"""\
An automatic metadata standarization pipeline using an LLM was instructed to map the \
metadata to the relevant ontology term representing the sample.
As the "{config_attr}" attribute, the pipeline mapped the ontology term below:

{term_for_prompt}
Classify the validity of this mapping into exactly one category ID from the list below.

{categories_text}"""

    return f"""Here is metadata of a sample that was used for a biological experiment.

{json.dumps(sample, indent=4)}

{stage_instruction}

Output only a JSON object with these keys:
- "category": one category ID. Valid category IDs are: {category_ids}
- "reason": one short sentence explaining the judgment.
"""

def build_pipeline_context(pipeline_record, config_attr):
    # Classification only needs the evaluated attribute slice of the upstream pipeline output.
    if pipeline_record is None:
        return None

    extracted = pipeline_record.get("extract", {}).get("extracted")
    return {
        "accession": pipeline_record.get("extract", {}).get("accession"),
        "extracted_for_attribute": extracted.get(config_attr) if isinstance(extracted, dict) else extracted,
        "search_results_for_attribute": pipeline_record.get("search_results", {}).get(config_attr, {}),
        "text2term_results_for_attribute": pipeline_record.get("text2term_results", {}).get(config_attr, {}),
        "final_results_for_attribute": pipeline_record.get("results", {}).get(config_attr, [])
    }

def calc_normalized_bool_prob(decision, top_logprobs):
    # Only exact true/false tokens are included, matching the repository's confidence definition.
    bool_probs = {"true": 0.0, "false": 0.0}
    for item in top_logprobs:
        token = item["token"]
        if token in bool_probs:
            bool_probs[token] += exp(item["logprob"])

    decision = decision.strip().lower()
    total = bool_probs["true"] + bool_probs["false"]
    if decision not in bool_probs or total == 0:
        return ""
    return bool_probs[decision] / total

def post_bool_prompt(prompt, url, headers):
    # Boolean prompts use the observed llama.cpp response_format/logprobs settings.
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
        "temperature": 0,
        "logprobs": True
    }
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()["choices"][0]
    content = data["message"]["content"]  # true / false
    first_token_logprobs = data["logprobs"]["content"][0]
    emitted_token_prob = exp(first_token_logprobs["logprob"])
    normalized_bool_prob = calc_normalized_bool_prob(content, first_token_logprobs["top_logprobs"])
    return content, emitted_token_prob, normalized_bool_prob

def classify_error(sample, target, term_str, config_attr, error_categories, stage, url, headers):
    # The same parser is used for extraction and selection category JSON responses.
    prompt = build_classification_prompt(sample, target, term_str, config_attr, error_categories, stage)
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
        "temperature": 0
    }
    response = requests.post(url, headers=headers, json=payload)
    content = response.json()["choices"][0]["message"]["content"].strip()
    return parse_classification_response(content, error_categories)

def parse_classification_response(content, error_categories):
    # Prefer strict JSON but keep a tolerant fallback for occasional model formatting drift.
    valid_ids = [category["id"] for category in error_categories]

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        category = str(parsed.get("category", "")).strip()
        reason = str(parsed.get("reason", "")).strip()
        if category in valid_ids:
            return category, reason
        for category_id in valid_ids:
            if category_id in category:
                print(
                    f"Warning: Classification category was not exact; extracted '{category_id}' from '{category}'",
                    file=sys.stderr
                )
                return category_id, reason

    if content in valid_ids:
        return content, ""
    for category_id in valid_ids:
        if category_id in content:
            print(
                f"Warning: Classification response was not exact; extracted '{category_id}' from '{content}'",
                file=sys.stderr
            )
            return category_id, content
    print(f"Warning: Could not parse classification response: {content}", file=sys.stderr)
    return "other", content

def format_prob(prob):
    if prob == "":
        return ""
    return round(prob, 3)

def format_tsv_value(value):
    # Keep the evaluator output one physical TSV row per evaluated mapping.
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("\t", " ").replace("\n", " ").replace("\r", " ")

def eval_mappings(ontology, mapping_result_dict, biosample_json_file, url, config, config_attr, error_categories):
    headers = {"Content-Type": "application/json"}
    extraction_categories = error_categories["extraction"]
    selection_categories = error_categories["selection"]

    samples = load_json_file(biosample_json_file, "BioSample")
    for sample in samples:
        bs_id = sample["accession"]
        for target in mapping_result_dict[bs_id]:
            term_id = target["term_id"]
            if term_id == "":
                # Non-mapped cases stop after the configured non-mapping true/false prompt.
                prompt = build_prompt(sample, "", config)
                term_label = ""
                term_str = ""
            else:
                # Mapped cases include ontology evidence in the first-pass mapping prompt.
                local_term_id = ontology_local_id(term_id)
                term_str = dump_owl_term(ontology, local_term_id, config["base_uri"], config["props_for_dump"])
                prompt = build_prompt(sample, term_str, config)
                term_label = target["term_label"] or get_label(ontology, local_term_id, config["base_uri"])

            # First pass: judge whether the final mapping or non-mapping decision is correct.
            content, emitted_token_prob, normalized_bool_prob = post_bool_prompt(prompt, url, headers)
            if normalized_bool_prob == "":
                print(
                    f"Warning: Could not calculate normalized boolean probability for {bs_id}\t{term_id}\t{content}",
                    file=sys.stderr
                )
            extraction_category = ""
            extraction_reason = ""
            selection_category = ""
            selection_reason = ""
            if term_id != "" and content.strip().lower() == "false":
                # Second pass: classify extraction first. Only valid extraction proceeds to selection classification.
                extraction_category, extraction_reason = classify_error(
                    sample,
                    target,
                    term_str,
                    config_attr,
                    extraction_categories,
                    "extraction",
                    url,
                    headers
                )
                if extraction_category == "extraction_valid":
                    selection_category, selection_reason = classify_error(
                        sample,
                        target,
                        term_str,
                        config_attr,
                        selection_categories,
                        "selection",
                        url,
                        headers
                    )
            print(
                bs_id,
                format_tsv_value(target["extracted_value"]),
                term_id,
                term_label,
                content,
                format_prob(emitted_token_prob),
                format_prob(normalized_bool_prob),
                extraction_category,
                format_tsv_value(extraction_reason),
                selection_category,
                format_tsv_value(selection_reason),
                sep="\t"
            )

    return

def load_config(config_file):
    return load_json_file(config_file, "evaluation config")

def load_error_categories(error_category_file):
    # One JSON file holds separate category lists for the two classification passes.
    categories = load_json_file(error_category_file, "error category")
    if not isinstance(categories, dict):
        raise UserInputError("Error category file must contain extraction and selection category lists")
    for stage in ["extraction", "selection"]:
        if stage not in categories or not categories[stage]:
            raise UserInputError(f"Error category file must contain at least one {stage} category")
        for category in categories[stage]:
            if "id" not in category or "description" not in category:
                raise UserInputError(f"Each {stage} error category must contain id and description")
    extraction_ids = {category["id"] for category in categories["extraction"]}
    if "extraction_valid" not in extraction_ids:
        raise UserInputError("Extraction categories must contain extraction_valid")
    return categories

def main():
    parser = argparse.ArgumentParser(description='evaluate ontology mapping results')
    parser.add_argument("-r", '--evaluation_target_file', help='Path to TSV or bsllmner-mk2 select-output JSON containing evaluation targets', required=True)
    parser.add_argument("--evaluation_target_format", choices=["auto", "tsv", "json"], default="auto", help='Format of evaluation_target_file. Default: auto')
    parser.add_argument("-b", '--biosample_json_file', help='Path to input biosample JSON file', required=True)
    parser.add_argument("-c", '--config_file', help='Path to config file', required=True)
    parser.add_argument("--error_category_file", default="input/error_categories.json", help='Path to JSON file defining error categories')
    parser.add_argument("-a", '--config_attr', help='Attribute name, defined in config file, to be used for this run ', required=True)
    parser.add_argument("-u", '--url', help='URL of llama.cpp endpoint', required=True)

    args = parser.parse_args()
    try:
        # Load ontology
        print("Loading ontology...", file=sys.stderr)
        start_time = time.time()
        configs = load_config(args.config_file)
        if args.config_attr not in configs:
            available_attrs = ", ".join(sorted(configs.keys()))
            print(
                f"Error: Attribute '{args.config_attr}' is not defined in {args.config_file}. "
                f"Available attributes: {available_attrs}",
                file=sys.stderr
            )
            sys.exit(1)
        config = configs[args.config_attr]
        ontology_file = config["ontology_file"]
        base_dir = Path(__file__).resolve().parent
        ontology = get_ontology(f"file://{base_dir}/{ontology_file}").load()
        error_categories = load_error_categories(args.error_category_file)
        total_time = time.time() - start_time
        print(f"Ontology loaded in {total_time:.2f} seconds", file=sys.stderr)
        mapping_result_dict = load_targets(
            args.evaluation_target_file,
            args.config_attr,
            args.evaluation_target_format
        )

        print("Performing evaluation...", file=sys.stderr)
        start_time = time.time()
        eval_mappings(
            ontology,
            mapping_result_dict,
            args.biosample_json_file,
            args.url,
            config,
            args.config_attr,
            error_categories
        )
        total_time = time.time() - start_time
        print(f"Evaluation completed in {total_time:.2f} seconds", file=sys.stderr)
    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        sys.exit(1)
    except UserInputError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
