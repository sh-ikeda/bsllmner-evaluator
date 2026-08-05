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

def build_category_prompt(sample, target, term_str, config_attr, category, stage):
    # One yes/no question per category, instead of an N-way choice, so each
    # judgment stays a simple, independently checkable question.
    extracted_value = format_tsv_value(target["extracted_value"])
    term_for_prompt = term_str if term_str else "(no final ontology term was mapped)"

    if stage == "extraction":
        stage_instruction = f"""\
An automatic metadata standarization pipeline using an LLM was instructed to extract \
the string(s) representing the sample.
As the "{config_attr}" attribute, the pipeline extracted "{extracted_value}"."""

    else:
        stage_instruction = f"""\
An automatic metadata standarization pipeline using an LLM was instructed to map the \
metadata to the relevant ontology term representing the sample.
As the "{config_attr}" attribute, the pipeline mapped the ontology term below:

{term_for_prompt}"""

    return f"""Here is metadata of a sample that was used for a biological experiment.

{json.dumps(sample, indent=4)}

{stage_instruction}

Consider whether the following statement correctly describes this {stage}:

"{category['description']}"

Does this statement apply? Output only a JSON object with these keys:
- "decision": true or false.
- "reason": one concise sentence explaining the judgment. Keep it short.
"""

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

def calc_normalized_bool_prob_loose(decision, top_logprobs):
    # Same as calc_normalized_bool_prob, but tolerant of a leading space on
    # the true/false token. Inside a {"decision": ..., "reason": ...} object
    # the value token is naturally emitted as " true"/" false" (JSON "key":
    # value syntax), unlike the top-level boolean case where content has no
    # such prefix and the strict exact-match rule applies.
    bool_probs = {"true": 0.0, "false": 0.0}
    for item in top_logprobs:
        token = item["token"].strip()
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

def find_bool_token_logprobs(content_logprobs):
    # The decision is no longer necessarily the first content token (it now
    # sits inside a {"decision": ..., "reason": ...} object), so scan for it.
    # The token itself carries a leading space here (JSON "key": value
    # syntax), e.g. " false", hence the stripped comparison.
    for item in content_logprobs:
        if item["token"].strip() in ("true", "false"):
            return item
    return None

def post_category_prompt(prompt, url, headers):
    # Category questions ask for a compact {"decision": bool, "reason": "..."}
    # object in a single non-thinking pass. An earlier version enabled
    # llama.cpp "thinking" to get a separate reasoning trace, but that made
    # each category call take ~45-50s (up to 12+ minutes for a single row
    # with 15 categories) -- too slow in practice, so thinking is off again.
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
                "type": "object",
                "properties": {
                    "decision": {"type": "boolean"},
                    "reason": {"type": "string"}
                },
                "required": ["decision", "reason"]
            }
        },
        "temperature": 0,
        "logprobs": True
    }
    response = requests.post(url, headers=headers, json=payload)
    data = response.json()["choices"][0]
    content = data["message"]["content"]
    parsed = json.loads(content)
    decision = "true" if parsed["decision"] else "false"
    reason = str(parsed["reason"]).strip()

    bool_token_logprobs = find_bool_token_logprobs(data["logprobs"]["content"])
    if bool_token_logprobs is None:
        emitted_token_prob = ""
        normalized_bool_prob = ""
    else:
        emitted_token_prob = exp(bool_token_logprobs["logprob"])
        normalized_bool_prob = calc_normalized_bool_prob_loose(
            decision, bool_token_logprobs["top_logprobs"]
        )
    return decision, emitted_token_prob, normalized_bool_prob, reason

def classify_by_category(sample, target, term_str, config_attr, categories, stage, url, headers, verbose=False):
    # Ask every category as an independent yes/no question rather than
    # forcing a single N-way choice; all judgments are kept, none discarded.
    judgments = []
    for category in categories:
        prompt = build_category_prompt(sample, target, term_str, config_attr, category, stage)
        decision, emitted_prob, normalized_prob, reason = post_category_prompt(prompt, url, headers)
        if verbose:
            print(f"    [{stage}] {category['id']}: {decision}", file=sys.stderr)
        judgments.append({
            "category": category["id"],
            "decision": decision,
            "probability": format_prob(emitted_prob),
            "normalized_probability": format_prob(normalized_prob),
            "reason": reason
        })
    return judgments

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

def build_header(error_categories):
    # One decision/probability/normalized_probability/reason column group per
    # category, so every judgment is its own TSV column instead of a JSON blob.
    header = [
        "accession",
        "extracted_value",
        "term_id",
        "term_label",
        "mapping_decision",
        "mapping_probability",
        "mapping_normalized_probability"
    ]
    if error_categories is None:
        # bool_only mode: no classification pass, so no category columns.
        return header
    # Category IDs already convey their stage (e.g. "extraction_wrong_attribute",
    # "selection_failed_to_reject"), and no ID collides across stages, so the
    # column name is just the ID itself rather than a redundant stage prefix.
    for categories in (error_categories["extraction"], error_categories["selection"]):
        for category in categories:
            header += [
                f"{category['id']}_decision",
                f"{category['id']}_probability",
                f"{category['id']}_normalized_probability",
                f"{category['id']}_reason"
            ]
    return header

def flatten_judgments(categories, judgments):
    # Empty strings mean the category was never asked (e.g. mapping decision was true).
    judgment_by_category = {j["category"]: j for j in judgments}
    values = []
    for category in categories:
        judgment = judgment_by_category.get(category["id"])
        if judgment is None:
            values += ["", "", "", ""]
        else:
            values += [
                judgment["decision"],
                judgment["probability"],
                judgment["normalized_probability"],
                format_tsv_value(judgment["reason"])
            ]
    return values

def eval_mappings(ontology, mapping_result_dict, biosample_json_file, url, config, config_attr, error_categories, verbose=False, bool_only=False):
    headers = {"Content-Type": "application/json"}
    extraction_categories = error_categories["extraction"] if error_categories else []
    selection_categories = error_categories["selection"] if error_categories else []
    total_targets = sum(len(targets) for targets in mapping_result_dict.values())
    row_number = 0

    print(*build_header(None if bool_only else error_categories), sep="\t")

    samples = load_json_file(biosample_json_file, "BioSample")
    for sample in samples:
        bs_id = sample["accession"]
        for target in mapping_result_dict[bs_id]:
            row_number += 1
            term_id = target["term_id"]
            if verbose:
                print(f"[{row_number}/{total_targets}] {bs_id}\t{term_id}", file=sys.stderr)
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
            if verbose:
                print(f"  mapping decision: {content.strip().lower()}", file=sys.stderr)
            if normalized_bool_prob == "":
                print(
                    f"Warning: Could not calculate normalized boolean probability for {bs_id}\t{term_id}\t{content}",
                    file=sys.stderr
                )
            extraction_judgments = []
            selection_judgments = []
            if not bool_only and term_id != "" and content.strip().lower() == "false":
                # Second pass: ask every extraction and selection category as an
                # independent yes/no question. Both stages always run together;
                # extraction_valid is just one more reported judgment, not a gate.
                extraction_judgments = classify_by_category(
                    sample,
                    target,
                    term_str,
                    config_attr,
                    extraction_categories,
                    "extraction",
                    url,
                    headers,
                    verbose
                )
                selection_judgments = classify_by_category(
                    sample,
                    target,
                    term_str,
                    config_attr,
                    selection_categories,
                    "selection",
                    url,
                    headers,
                    verbose
                )
            row = [
                bs_id,
                format_tsv_value(target["extracted_value"]),
                term_id,
                term_label,
                content,
                format_prob(emitted_token_prob),
                format_prob(normalized_bool_prob)
            ]
            if not bool_only:
                row += flatten_judgments(extraction_categories, extraction_judgments)
                row += flatten_judgments(selection_categories, selection_judgments)
            print(*row, sep="\t")

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
    parser.add_argument("-v", '--verbose', action="store_true", help='Print per-row and per-category progress to stderr')
    parser.add_argument("--bool_only", action="store_true", help='Only run the first-pass mapping correctness judgment; skip the extraction/selection category classification pass')

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
        error_categories = None if args.bool_only else load_error_categories(args.error_category_file)
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
            error_categories,
            args.verbose,
            args.bool_only
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
