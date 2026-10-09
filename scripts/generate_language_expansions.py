#!/usr/bin/env python3
"""Create a reproducible, conservative language-variant manifest for UMLS audits."""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Deliberately small, auditable synonym/lay-language map.  This is a proxy for
# semantic expansion, not a claim that every generated variant is correct.
TOKEN_VARIANTS = {
    "tylenol": [("acetaminophen", "brand_to_ingredient")],
    "acetaminophen": [("paracetamol", "ingredient_synonym")],
    "fractured": [("broken", "lay_clinical")],
    "fracture": [("broken", "lay_clinical")],
    "myocardial": [("heart", "lay_clinical")],
    "infarction": [("attack", "lay_clinical")],
    "leukaemia": [("leukemia", "spelling_variant")],
    "oedema": [("edema", "spelling_variant")],
    "haemorrhage": [("hemorrhage", "spelling_variant")],
    "paediatric": [("pediatric", "spelling_variant")],
    "renal": [("kidney", "lay_clinical")],
    "cervical": [("neck", "lay_clinical")],
    "ophthalmic": [("eye", "lay_clinical")],
}

PHRASE_VARIANTS = {
    "poisoning": [("overdose", "lay_clinical")],
    "perfusion imaging": [("perfusion scan", "lay_clinical")],
    "bone marrow aspiration": [("aspiration bone marrow", "word_order")],
}


def variants(term: str) -> list[tuple[str, str, str]]:
    seen = {term.casefold()}
    output: list[tuple[str, str, str]] = []
    lowered = term.casefold()
    for phrase, replacements in PHRASE_VARIANTS.items():
        if phrase in lowered:
            for replacement, strategy in replacements:
                query = lowered.replace(phrase, replacement)
                if query not in seen:
                    seen.add(query)
                    output.append((query, strategy, f"phrase variant: {phrase} -> {replacement}"))
    words = lowered.split()
    for index, word in enumerate(words):
        for replacement, strategy in TOKEN_VARIANTS.get(word, []):
            changed = words[:]
            changed[index] = replacement
            query = " ".join(changed)
            if query not in seen:
                seen.add(query)
                output.append((query, strategy, f"token variant: {word} -> {replacement}"))
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.baseline_run / "rows.tsv"
    output = args.output or args.baseline_run / "language_expansions.tsv"
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "search_term", "decision", "expansion_query", "expansion_strategy", "expansion_note"]
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            generated = variants(row["search_term"])
            writer.writerow({"id": row["id"], "search_term": row["search_term"], "decision": "include", "expansion_query": "", "expansion_strategy": "", "expansion_note": "generated conservative language variants"})
            for query, strategy, note in generated:
                writer.writerow({"id": row["id"], "search_term": row["search_term"], "decision": "include", "expansion_query": query, "expansion_strategy": strategy, "expansion_note": note})
    print(f"wrote {output} ({sum(len(variants(r['search_term'])) for r in rows)} generated variants)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
