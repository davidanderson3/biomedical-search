#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from evaluate_paragraph_quality import (  # noqa: E402
    DEFAULT_ACCEPTABLE_ALTERNATIVES,
    acceptable_options,
    read_acceptable_alternatives,
)
from evaluate_search_api import read_query_specs  # noqa: E402
from qe_evidence_vectors.search_tokens import content_tokens  # noqa: E402
from qe_evidence_vectors.text import normalized_key  # noqa: E402


DEFAULT_QUERIES = ROOT / "config" / "search_quality_paragraph_queries.tsv"
DEFAULT_USEFUL_EXTRAS = ROOT / "config" / "search_quality_useful_extra_cuis.tsv"

GENERIC_OR_STATUS_LABELS = {
    "absence of pain",
    "after delivery",
    "active",
    "baseline",
    "cohort studies",
    "compatible",
    "complete",
    "critical",
    "education",
    "empiric",
    "ever told you have or had atrial fibrillation",
    "every qualifier",
    "forty four",
    "granular",
    "general mechanism of the forces which caused the injury",
    "had no pain",
    "high dose",
    "hormonal",
    "low dose",
    "mg dl",
    "milliliter per second",
    "neoplasms",
    "pain absent",
    "pending day type",
    "per 4 0 milliliters",
    "prescribed medications",
    "second ordinal",
    "second unit of plane angle",
    "sixty four",
    "singular",
    "symptom score",
    "symptom severe",
    "suspected diagnosis",
    "suspicious",
    "teaching",
    "thyroid hormones",
    "update",
    "viral illness",
    "virus diseases",
    "vitamins",
    "volume",
    "wound status",
    "disease susceptibility",
    "benefit",
}
GENERIC_OR_STATUS_TOKEN_SETS = {
    frozenset(content_tokens(label)) for label in GENERIC_OR_STATUS_LABELS
}
LOW_VALUE_SINGLE_ANCHORS = {
    "active",
    "baseline",
    "compatible",
    "complete",
    "critical",
    "empiric",
    "granular",
    "hormonal",
    "pending",
    "score",
    "second",
    "singular",
    "suspected",
    "suspicious",
    "teaching",
    "update",
    "updated",
    "volume",
}
LOW_SPECIFICITY_SEMANTIC_TYPES = {
    "Classification",
    "Clinical Attribute",
    "Intellectual Product",
    "Quantitative Concept",
    "Qualitative Concept",
    "Temporal Concept",
}


def read_payloads(path: Path) -> dict[str, dict]:
    payloads = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            payload_id = str(payload.get("id") or "").strip()
            if payload_id:
                payloads[payload_id] = payload
    return payloads


def read_useful_extra_cuis(path: Path | None) -> dict[str, set[str]]:
    if not path or not path.exists():
        return {}
    extras: dict[str, set[str]] = defaultdict(set)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        for row in reader:
            query_id = str(row.get("id") or row.get("query_id") or "").strip()
            cui = str(row.get("cui") or row.get("useful_extra_cui") or "").strip().upper()
            if query_id and cui:
                extras[query_id].add(cui)
    return dict(extras)


def accepted_cuis_for_expected(expected_cuis: list[str], alternatives: dict[str, set[str]]) -> set[str]:
    accepted = set()
    for expected_cui in expected_cuis:
        accepted.update(acceptable_options(expected_cui, alternatives))
    return {cui.upper() for cui in accepted}


def semantic_type_names(hit: dict) -> set[str]:
    names = set()
    for semantic_type in hit.get("semantic_types") or []:
        name = str(semantic_type.get("name") or semantic_type.get("sty") or "").strip()
        if name:
            names.add(name)
    return names


def hit_label_token_sets(hit: dict) -> set[frozenset[str]]:
    labels = [str(hit.get("name") or "")]
    labels.extend(str(label) for label in hit.get("labels") or [])
    labels.extend(
        str(hit.get(field) or "")
        for field in ("matched_label", "matched_query_span")
    )
    return {frozenset(content_tokens(label)) for label in labels if content_tokens(label)}


def label_text(hit: dict) -> str:
    return str(hit.get("name") or hit.get("label") or hit.get("cui") or "")


def is_expected_or_accepted(hit: dict, accepted: set[str]) -> bool:
    return str(hit.get("cui") or "").upper() in accepted


def classify_suspect_hit(hit: dict, *, rank: int, accepted: set[str]) -> list[str]:
    if is_expected_or_accepted(hit, accepted):
        return []

    reasons = []
    semantic_group = str(hit.get("semantic_group") or "OTHER")
    semantic_types = semantic_type_names(hit)
    token_sets = hit_label_token_sets(hit)
    matched_span_tokens = set(content_tokens(str(hit.get("matched_query_span") or "")))
    matched_label_tokens = set(content_tokens(str(hit.get("matched_label") or "")))
    all_matched_tokens = matched_span_tokens | matched_label_tokens
    score_breakdown = hit.get("score_breakdown") or {}

    if rank <= 3:
        reasons.append("visible_top3_nonexpected")
    if semantic_group == "OTHER":
        reasons.append("other_or_uncategorized")
    if semantic_types & LOW_SPECIFICITY_SEMANTIC_TYPES:
        reasons.append("low_specificity_semantic_type")
    if token_sets & GENERIC_OR_STATUS_TOKEN_SETS:
        reasons.append("generic_or_status_label")
    if all_matched_tokens and all_matched_tokens <= LOW_VALUE_SINGLE_ANCHORS:
        reasons.append("single_generic_anchor")
    if (
        not matched_span_tokens
        and semantic_group in {"OTHER", "CONC"}
        and float(score_breakdown.get("lexical_component") or 0.0) <= 0.5
    ):
        reasons.append("weak_unanchored_context")
    if float(score_breakdown.get("relative_specificity_penalty") or 0.0) >= 0.4:
        reasons.append("already_specificity_penalized")
    if float(score_breakdown.get("clinical_context_sense_penalty") or 0.0) >= 0.4:
        reasons.append("already_context_penalized")

    return reasons


def relevance_root_cause(hit: dict, *, rank: int, reasons: list[str], useful: set[str]) -> tuple[str, str]:
    hit_cui = str(hit.get("cui") or "").upper()
    matched_span_tokens = set(content_tokens(str(hit.get("matched_query_span") or "")))
    matched_label_tokens = set(content_tokens(str(hit.get("matched_label") or "")))
    all_matched_tokens = matched_span_tokens | matched_label_tokens
    score_breakdown = hit.get("score_breakdown") or {}
    lexical_component = float(score_breakdown.get("lexical_component") or 0.0)
    rank_score = float(hit.get("rank_score") or hit.get("score") or 0.0)
    semantic_types = semantic_type_names(hit)

    if hit_cui in useful:
        return (
            "known_useful_extra",
            "Consider promoting to expected if it is central to the paragraph; otherwise keep as useful-extra.",
        )
    if "generic_or_status_label" in reasons or "single_generic_anchor" in reasons:
        return (
            "generic_status_or_qualifier",
            "Block the CUI/label or require a stronger local anchor before it can rank visibly.",
        )
    if "low_specificity_semantic_type" in reasons or "other_or_uncategorized" in reasons:
        return (
            "low_specificity_semantic_type",
            "Downweight this semantic type/source in broad paragraphs unless the query explicitly names it.",
        )
    if not matched_span_tokens and (lexical_component <= 0.5 or rank_score < 0.35):
        return (
            "unanchored_vector_drift",
            "Require lexical overlap, relation support, or a high-confidence definition/evidence anchor.",
        )
    if "already_specificity_penalized" in reasons or "already_context_penalized" in reasons:
        return (
            "penalty_not_strong_enough",
            "Convert repeated penalized false positives into a cutoff, not just a lower score.",
        )
    if rank <= 3 and all_matched_tokens:
        if semantic_types & {
            "Antibiotic",
            "Diagnostic Procedure",
            "Laboratory Procedure",
            "Organic Chemical",
            "Pharmacologic Substance",
            "Therapeutic or Preventive Procedure",
        }:
            return (
                "literal_auxiliary_concept",
                "Decide whether the benchmark should expect mentioned drugs/tests/procedures; otherwise apply task/view weighting.",
            )
        return (
            "expected_set_gap_or_valid_secondary",
            "Judge the result: add expected/useful-extra if clinically relevant, or add a reusable context rule if not.",
        )
    return (
        "needs_manual_judgment",
        "Review manually, then turn repeated patterns into a source/type/anchor rule.",
    )


def compact_expected(expected: list[str], accepted: set[str]) -> str:
    expected_set = {cui.upper() for cui in expected}
    extra = sorted(accepted - expected_set)
    if not extra:
        return "|".join(sorted(expected_set))
    return f"{'|'.join(sorted(expected_set))}; alternatives={'|'.join(extra)}"


def audit_payloads(
    *,
    query_path: Path,
    payload_path: Path,
    alternatives_path: Path,
    useful_extras_path: Path | None,
    top_n: int,
) -> tuple[list[dict], dict]:
    specs = read_query_specs(query_path)
    payloads = read_payloads(payload_path)
    alternatives = read_acceptable_alternatives(alternatives_path)
    useful_extras = read_useful_extra_cuis(useful_extras_path)
    rows = []
    reason_counts: Counter[str] = Counter()
    root_cause_counts: Counter[str] = Counter()
    suspect_counts_by_cui: Counter[str] = Counter()
    names_by_cui: dict[str, str] = {}
    examples_by_cui: defaultdict[str, list[str]] = defaultdict(list)
    nonexpected_top_n = 0
    useful_extra_top_n = 0

    for spec in specs:
        payload = payloads.get(spec.query_id)
        if not payload:
            continue
        hits = list((payload.get("response") or {}).get("hits") or [])
        accepted = accepted_cuis_for_expected(spec.expected_cuis, alternatives)
        useful = useful_extras.get(spec.query_id, set())
        accepted_or_useful = accepted | useful
        for rank, hit in enumerate(hits[:top_n], start=1):
            hit_cui = str(hit.get("cui") or "").upper()
            if hit_cui not in accepted:
                nonexpected_top_n += 1
            if hit_cui in useful and hit_cui not in accepted:
                useful_extra_top_n += 1
            reasons = classify_suspect_hit(hit, rank=rank, accepted=accepted_or_useful)
            if not reasons:
                continue
            root_cause, recommended_action = relevance_root_cause(
                hit,
                rank=rank,
                reasons=reasons,
                useful=useful,
            )
            root_cause_counts[root_cause] += 1
            cui = hit_cui
            name = label_text(hit)
            suspect_counts_by_cui[cui] += 1
            names_by_cui[cui] = name
            for reason in reasons:
                reason_counts[reason] += 1
            if len(examples_by_cui[cui]) < 3:
                examples_by_cui[cui].append(spec.query_id)
            rows.append(
                {
                    "id": spec.query_id,
                    "rank": rank,
                    "cui": cui,
                    "name": name,
                    "semantic_group": str(hit.get("semantic_group") or "OTHER"),
                    "semantic_types": "; ".join(sorted(semantic_type_names(hit))),
                    "rank_score": hit.get("rank_score", hit.get("score", "")),
                    "matched_label": str(hit.get("matched_label") or ""),
                    "matched_query_span": str(hit.get("matched_query_span") or ""),
                    "reasons": "|".join(reasons),
                    "root_cause": root_cause,
                    "recommended_action": recommended_action,
                    "expected_or_accepted": compact_expected(spec.expected_cuis, accepted),
                    "useful_extra_cuis": "|".join(sorted(useful)),
                    "query": spec.query,
                }
            )

    total_top_n = len(specs) * top_n
    top_suspects = [
        {
            "cui": cui,
            "name": names_by_cui.get(cui, ""),
            "count": count,
            "example_ids": examples_by_cui.get(cui, []),
        }
        for cui, count in suspect_counts_by_cui.most_common(30)
    ]
    metrics = {
        "paragraphs": len(specs),
        "payloads": len(payloads),
        "top_n": top_n,
        "top_n_slots": total_top_n,
        "nonexpected_top_n_hits": nonexpected_top_n,
        "useful_extra_top_n_hits": useful_extra_top_n,
        "suspect_top_n_hits": len(rows),
        "suspect_hits_per_paragraph": len(rows) / len(specs) if specs else 0.0,
        "useful_extra_rows": sum(len(values) for values in useful_extras.values()),
        "reason_counts": dict(sorted(reason_counts.items())),
        "root_cause_counts": dict(sorted(root_cause_counts.items())),
        "top_suspect_cuis": top_suspects,
    }
    return rows, metrics


def write_tsv(path: Path, rows: list[dict]) -> None:
    fields = [
        "id",
        "rank",
        "cui",
        "name",
        "semantic_group",
        "semantic_types",
        "rank_score",
        "matched_label",
        "matched_query_span",
        "reasons",
        "root_cause",
        "recommended_action",
        "expected_or_accepted",
        "useful_extra_cuis",
        "query",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, metrics: dict) -> None:
    lines = [
        "# Paragraph Precision Audit",
        "",
        "This audit flags top results that are not in the expected CUI set or configured acceptable alternatives and have low-specificity signals. A flagged result is a review target, not automatically a false positive.",
        "",
        "## Metrics",
        "",
        f"- Paragraphs: {metrics['paragraphs']}",
        f"- Payloads: {metrics['payloads']}",
        f"- Top-N audited per paragraph: {metrics['top_n']}",
        f"- Nonexpected top-N hits: {metrics['nonexpected_top_n_hits']}/{metrics['top_n_slots']}",
        f"- Useful extra top-N hits: {metrics['useful_extra_top_n_hits']}",
        f"- Suspect top-N hits: {metrics['suspect_top_n_hits']}",
        f"- Suspect hits per paragraph: {metrics['suspect_hits_per_paragraph']:.2f}",
        f"- Configured useful extra rows: {metrics['useful_extra_rows']}",
        f"- Reason counts: {metrics['reason_counts']}",
        f"- Root-cause counts: {metrics['root_cause_counts']}",
        "",
        "## Strategy Buckets",
        "",
    ]
    root_cause_counts = metrics.get("root_cause_counts") or {}
    if not root_cause_counts:
        lines.append("- None.")
    else:
        for root_cause, count in sorted(root_cause_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- {root_cause}: {count}")
    lines.extend(
        [
            "",
            "## Most Frequent Suspect CUIs",
            "",
        ]
    )
    top_suspects = metrics.get("top_suspect_cuis") or []
    if not top_suspects:
        lines.append("- None.")
    else:
        for item in top_suspects[:20]:
            examples = ",".join(item.get("example_ids") or [])
            lines.append(
                f"- {item['cui']} {item['name']}: {item['count']} hits"
                + (f" (examples: {examples})" if examples else "")
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit visible nonexpected paragraph search results.")
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--payloads", type=Path, required=True)
    parser.add_argument("--alternatives", type=Path, default=DEFAULT_ACCEPTABLE_ALTERNATIVES)
    parser.add_argument("--useful-extras", type=Path, default=DEFAULT_USEFUL_EXTRAS)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-n", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rows, metrics = audit_payloads(
        query_path=args.queries,
        payload_path=args.payloads,
        alternatives_path=args.alternatives,
        useful_extras_path=args.useful_extras,
        top_n=args.top_n,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "paragraph_precision_audit.tsv", rows)
    (args.output_dir / "paragraph_precision_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    write_report(args.output_dir / "paragraph_precision_report.md", metrics)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
