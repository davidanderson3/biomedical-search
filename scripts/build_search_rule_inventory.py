#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from qe_evidence_vectors.generic_filters import (  # noqa: E402
    BLOCKED_GENERIC_CUIS,
    BLOCKED_GENERIC_LABELS,
    BLOCKED_GENERIC_QUERIES,
)
from qe_evidence_vectors.search_assertions import (  # noqa: E402
    AFTER_CUES,
    ASSERTION_CONFIRMED,
    ASSERTION_FAMILY_HISTORY,
    ASSERTION_HISTORICAL,
    ASSERTION_NEGATED,
    ASSERTION_PLANNED,
    ASSERTION_UNCERTAIN,
    BEFORE_CUES,
    CHART_HISTORY_CUES,
)
from qe_evidence_vectors.search_ranking import (  # noqa: E402
    BROAD_CORTICOSTEROID_CLASS_REVIEW_MIN_TOKENS,
    BROAD_CORTICOSTEROID_CLASS_REVIEW_PENALTY,
    BROAD_CORTICOSTEROID_CLASS_SPANS,
    PATIENT_MESSAGE_META_CONTEXT_TOKENS,
    PATIENT_MESSAGE_META_NOISE_TOKENS,
    PATIENT_MESSAGE_META_SELF_TOKENS,
    PATIENT_STATE_CONFUSION_CONTEXT_TOKENS,
)


DEFAULT_HTML_OUTPUT = ROOT / "docs" / "search_rule_inventory.html"


RULE_SOURCES = {
    "generic_meta_suppression": "src/qe_evidence_vectors/generic_filters.py",
    "clinical_alias_supplement": "config/active_label_supplement.tsv",
    "assertion_context": "src/qe_evidence_vectors/search_assertions.py",
    "patient_portal_meta_context": "src/qe_evidence_vectors/search_ranking.py",
    "ranking_score_guards": "src/qe_evidence_vectors/search_ranking.py",
    "precision_audit_outcomes": "config/search_quality_precision_audit_review.tsv",
    "benchmark_guardrails": (
        "config/search_quality_paragraph_queries.tsv; "
        "config/search_quality_patient_portal_queries.tsv; "
        "config/search_quality_useful_extra_cuis.tsv"
    ),
}


STATUS_ORDER = [
    ASSERTION_NEGATED,
    ASSERTION_UNCERTAIN,
    ASSERTION_HISTORICAL,
    ASSERTION_FAMILY_HISTORY,
    ASSERTION_PLANNED,
    ASSERTION_CONFIRMED,
]


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(
            (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
            delimiter="\t",
        )
        return [
            {str(key): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def split_pipe_values(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def count_pipe_rows(rows: Iterable[dict[str, str]], column: str) -> int:
    return sum(1 for row in rows if split_pipe_values(row.get(column, "")))


def count_pipe_values(rows: Iterable[dict[str, str]], column: str) -> int:
    return sum(len(split_pipe_values(row.get(column, ""))) for row in rows)


def sorted_counter(counter: Counter[str]) -> list[dict[str, int | str]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def table(headers: list[str], rows: list[list[object]]) -> str:
    if not rows:
        return "_None._\n"
    escaped_headers = [escape_cell(header) for header in headers]
    lines = [
        "| " + " | ".join(escaped_headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(escape_cell(cell) for cell in row) + " |")
    return "\n".join(lines) + "\n"


def escape_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def inline_list(values: Iterable[str], *, limit: int = 18) -> str:
    items = list(values)
    shown = items[:limit]
    suffix = "" if len(items) <= limit else f", ... +{len(items) - limit} more"
    return ", ".join(f"`{item}`" for item in shown) + suffix


def html_escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def html_inline_list(values: Iterable[str], *, limit: int = 18) -> str:
    items = list(values)
    shown = items[:limit]
    suffix = "" if len(items) <= limit else f", ... +{len(items) - limit} more"
    return ", ".join(f"<code>{html_escape(item)}</code>" for item in shown) + html_escape(suffix)


def html_table(headers: list[str], rows: list[list[object]], *, class_name: str = "") -> str:
    class_attr = f' class="{html_escape(class_name)}"' if class_name else ""
    header_html = "".join(f"<th>{html_escape(header)}</th>" for header in headers)
    row_html = []
    for row in rows:
        row_html.append(
            "<tr>"
            + "".join(f"<td>{cell if isinstance(cell, HtmlCell) else html_escape(cell)}</td>" for cell in row)
            + "</tr>"
        )
    if not row_html:
        row_html.append(f"<tr><td colspan=\"{len(headers)}\">None.</td></tr>")
    return (
        f"<table{class_attr}>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody>"
        "</table>"
    )


class HtmlCell(str):
    pass


def source_link(path_text: str) -> HtmlCell:
    first_path = str(path_text).split(";")[0].strip()
    href = first_path if "://" in first_path else f"../{first_path}"
    return HtmlCell(f'<code><a href="{html_escape(href)}">{html_escape(path_text)}</a></code>')


def inventory_totals(inventory: dict) -> dict[str, int]:
    classes = {item["name"]: item for item in inventory["rule_classes"]}
    generic = classes["generic_meta_suppression"]["counts"]
    active = classes["clinical_alias_supplement"]["counts"]
    assertion = classes["assertion_context"]["counts"]
    portal = classes["patient_portal_meta_context"]["counts"]
    ranking = classes["ranking_score_guards"]["counts"]
    precision = classes["precision_audit_outcomes"]["counts"]
    guardrails = classes["benchmark_guardrails"]["counts"]
    active_heuristic_items = (
        generic["blocked_labels"]
        + generic["blocked_queries"]
        + generic["blocked_cuis"]
        + active["rows"]
        + assertion["before_cues"]
        + assertion["after_cues"]
        + assertion["chart_history_cues"]
        + portal["context_tokens"]
        + portal["self_tokens"]
        + portal["noise_tokens"]
        + portal["clinical_confusion_exception_tokens"]
        + ranking["named_guards"]
    )
    audit_guardrail_rows = (
        precision["review_rows"]
        + precision["useful_extra_rows"]
        + guardrails["paragraph_rows"]
        + guardrails["patient_portal_rows"]
    )
    return {
        "rule_classes": len(inventory["rule_classes"]),
        "active_heuristic_items": active_heuristic_items,
        "audit_guardrail_rows": audit_guardrail_rows,
        "generic_suppression_items": (
            generic["blocked_labels"] + generic["blocked_queries"] + generic["blocked_cuis"]
        ),
        "clinical_alias_rows": active["rows"],
        "assertion_cues": (
            assertion["before_cues"] + assertion["after_cues"] + assertion["chart_history_cues"]
        ),
        "patient_portal_tokens": (
            portal["context_tokens"]
            + portal["self_tokens"]
            + portal["noise_tokens"]
            + portal["clinical_confusion_exception_tokens"]
        ),
        "ranking_score_guards": ranking["named_guards"],
    }


def build_inventory() -> dict:
    active_rows = read_tsv(ROOT / "config" / "active_label_supplement.tsv")
    precision_rows = read_tsv(ROOT / "config" / "search_quality_precision_audit_review.tsv")
    useful_extra_rows = read_tsv(ROOT / "config" / "search_quality_useful_extra_cuis.tsv")
    paragraph_rows = read_tsv(ROOT / "config" / "search_quality_paragraph_queries.tsv")
    portal_rows = read_tsv(ROOT / "config" / "search_quality_patient_portal_queries.tsv")

    before_counts = {
        status: len(BEFORE_CUES.get(status, ()))
        for status in STATUS_ORDER
        if BEFORE_CUES.get(status)
    }
    after_counts = {
        status: len(AFTER_CUES.get(status, ()))
        for status in STATUS_ORDER
        if AFTER_CUES.get(status)
    }

    return {
        "rule_classes": [
            {
                "name": "generic_meta_suppression",
                "purpose": "Suppress UMLS concepts that behave like ordinary prose, form labels, or chart metadata instead of biomedical retrieval anchors.",
                "source": RULE_SOURCES["generic_meta_suppression"],
                "counts": {
                    "blocked_labels": len(BLOCKED_GENERIC_LABELS),
                    "blocked_queries": len(BLOCKED_GENERIC_QUERIES),
                    "blocked_cuis": len(BLOCKED_GENERIC_CUIS),
                },
                "examples": {
                    "labels": sorted(BLOCKED_GENERIC_LABELS),
                    "queries": sorted(BLOCKED_GENERIC_QUERIES),
                    "cuis": sorted(BLOCKED_GENERIC_CUIS),
                },
            },
            {
                "name": "clinical_alias_supplement",
                "purpose": "Add explicit, reviewed clinical phrases for known CUIs when core UMLS labels or default indexing miss the user-facing phrase.",
                "source": RULE_SOURCES["clinical_alias_supplement"],
                "counts": {
                    "rows": len(active_rows),
                    "unique_cuis": len({row.get("cui", "") for row in active_rows if row.get("cui")}),
                    "rows_with_context_any": count_pipe_rows(active_rows, "context_any"),
                    "rows_with_block_any": count_pipe_rows(active_rows, "block_any"),
                },
                "field_counts": sorted_counter(Counter(row.get("field", "") for row in active_rows)),
                "semantic_type_counts": sorted_counter(
                    Counter(row.get("semantic_type", "") for row in active_rows)
                ),
            },
            {
                "name": "assertion_context",
                "purpose": "Classify mentions as current, negated, uncertain, historical, family-history, planned, or confirmed before ranking them.",
                "source": RULE_SOURCES["assertion_context"],
                "counts": {
                    "before_cues": sum(before_counts.values()),
                    "after_cues": sum(after_counts.values()),
                    "chart_history_cues": len(CHART_HISTORY_CUES),
                },
                "before_counts": before_counts,
                "after_counts": after_counts,
                "chart_history_cues": sorted(CHART_HISTORY_CUES),
            },
            {
                "name": "patient_portal_meta_context",
                "purpose": "Detect patient portal prose and suppress conversational uncertainty/meta words without suppressing clinical confusion contexts.",
                "source": RULE_SOURCES["patient_portal_meta_context"],
                "counts": {
                    "context_tokens": len(PATIENT_MESSAGE_META_CONTEXT_TOKENS),
                    "self_tokens": len(PATIENT_MESSAGE_META_SELF_TOKENS),
                    "noise_tokens": len(PATIENT_MESSAGE_META_NOISE_TOKENS),
                    "clinical_confusion_exception_tokens": len(
                        PATIENT_STATE_CONFUSION_CONTEXT_TOKENS
                    ),
                },
                "tokens": {
                    "context": sorted(PATIENT_MESSAGE_META_CONTEXT_TOKENS),
                    "self": sorted(PATIENT_MESSAGE_META_SELF_TOKENS),
                    "noise": sorted(PATIENT_MESSAGE_META_NOISE_TOKENS),
                    "clinical_confusion_exceptions": sorted(
                        PATIENT_STATE_CONFUSION_CONTEXT_TOKENS
                    ),
                },
            },
            {
                "name": "ranking_score_guards",
                "purpose": "Apply narrow score components or penalties for recurring ranking error classes that cannot be expressed as generic suppression or alias supplementation.",
                "source": RULE_SOURCES["ranking_score_guards"],
                "counts": {
                    "named_guards": 1,
                },
                "guards": [
                    {
                        "name": "broad_corticosteroid_class_penalty",
                        "purpose": "Demote broad steroid/corticosteroid class hits in long treatment-review queries when multiple non-class anchors show the abstract is about a condition and its treatment options.",
                        "guardrail": "tests/test_evidence_vectors.py::test_ranker_demotes_broad_corticosteroid_class_in_long_status_review",
                        "penalty": BROAD_CORTICOSTEROID_CLASS_REVIEW_PENALTY,
                        "minimum_query_tokens": BROAD_CORTICOSTEROID_CLASS_REVIEW_MIN_TOKENS,
                        "matched_spans": sorted(BROAD_CORTICOSTEROID_CLASS_SPANS),
                    }
                ],
            },
            {
                "name": "precision_audit_outcomes",
                "purpose": "Separate useful secondary concepts from true false positives so future ranking changes have an unambiguous target.",
                "source": RULE_SOURCES["precision_audit_outcomes"],
                "counts": {
                    "review_rows": len(precision_rows),
                    "useful_extra_rows": len(useful_extra_rows),
                },
                "review_class_counts": sorted_counter(
                    Counter(row.get("review_class", "") for row in precision_rows)
                ),
                "action_counts": sorted_counter(Counter(row.get("action", "") for row in precision_rows)),
            },
            {
                "name": "benchmark_guardrails",
                "purpose": "Keep rule changes measurable through expected CUIs, active/current CUIs, context CUIs, disallowed CUIs, and known useful extras.",
                "source": RULE_SOURCES["benchmark_guardrails"],
                "counts": {
                    "paragraph_rows": len(paragraph_rows),
                    "patient_portal_rows": len(portal_rows),
                    "paragraph_rows_with_disallowed_cuis": count_pipe_rows(
                        paragraph_rows, "disallowed_cuis"
                    ),
                    "portal_rows_with_disallowed_cuis": count_pipe_rows(
                        portal_rows, "disallowed_cuis"
                    ),
                    "portal_active_cui_values": count_pipe_values(portal_rows, "active_cuis"),
                    "portal_context_cui_values": count_pipe_values(portal_rows, "context_cuis"),
                    "useful_extra_rows": len(useful_extra_rows),
                },
            },
        ],
        "sources": RULE_SOURCES,
    }


def render_markdown(inventory: dict) -> str:
    classes = {item["name"]: item for item in inventory["rule_classes"]}
    totals = inventory_totals(inventory)
    generic = classes["generic_meta_suppression"]
    active = classes["clinical_alias_supplement"]
    assertion = classes["assertion_context"]
    portal = classes["patient_portal_meta_context"]
    ranking_guards = classes["ranking_score_guards"]
    precision = classes["precision_audit_outcomes"]
    guardrails = classes["benchmark_guardrails"]

    lines: list[str] = [
        "# Search Rule Inventory",
        "",
        "Generated from the current checkout by `python3 scripts/build_search_rule_inventory.py`.",
        "Use this file as the review surface for heuristic changes: every rule should have a class, a source artifact, and a benchmark or audit artifact that explains why it exists.",
        "",
        "## Why This Exists",
        "",
        "The search stack is intentionally heuristic, but the rules should not be an unbounded pile of special cases. Keep them in named layers:",
        "",
        "1. **Suppress generic/meta concepts** when UMLS exposes ordinary prose as concepts.",
        "2. **Rescue clinical aliases** when a real clinical phrase should map to a known CUI.",
        "3. **Classify assertion/currentness** when a mention is old, negated, uncertain, planned, or active.",
        "4. **Handle patient-message meta language** when the user text contains conversational words that should not outrank clinical entities.",
        "5. **Apply narrow ranking score guards** when a recurring error class cannot be represented as suppression or alias data.",
        "6. **Audit useful extras versus false positives** so ranking changes target real errors.",
        "7. **Guard with benchmark rows** so each improvement is repeatable.",
        "",
        "## Inventory Summary",
        "",
        f"- Active heuristic items in the live search path: {totals['active_heuristic_items']}",
        f"- Rule classes: {totals['rule_classes']}",
        f"- Audit and benchmark guardrail rows: {totals['audit_guardrail_rows']}",
        f"- Generic suppression items: {totals['generic_suppression_items']}",
        f"- Clinical alias supplement rows: {totals['clinical_alias_rows']}",
        f"- Assertion/currentness cues: {totals['assertion_cues']}",
        f"- Patient-portal/meta tokens and exceptions: {totals['patient_portal_tokens']}",
        f"- Named ranking score guards: {totals['ranking_score_guards']}",
        "",
        "## Rule Classes",
        "",
        table(
            ["Class", "Source", "Purpose", "Current Size"],
            [
                [
                    "generic_meta_suppression",
                    generic["source"],
                    generic["purpose"],
                    (
                        f"{generic['counts']['blocked_labels']} labels; "
                        f"{generic['counts']['blocked_cuis']} CUIs; "
                        f"{generic['counts']['blocked_queries']} query blocks"
                    ),
                ],
                [
                    "clinical_alias_supplement",
                    active["source"],
                    active["purpose"],
                    (
                        f"{active['counts']['rows']} rows; "
                        f"{active['counts']['unique_cuis']} CUIs"
                    ),
                ],
                [
                    "assertion_context",
                    assertion["source"],
                    assertion["purpose"],
                    (
                        f"{assertion['counts']['before_cues']} before-cues; "
                        f"{assertion['counts']['after_cues']} after-cues"
                    ),
                ],
                [
                    "patient_portal_meta_context",
                    portal["source"],
                    portal["purpose"],
                    (
                        f"{portal['counts']['context_tokens']} context tokens; "
                        f"{portal['counts']['noise_tokens']} noise tokens"
                    ),
                ],
                [
                    "precision_audit_outcomes",
                    precision["source"],
                    precision["purpose"],
                    f"{precision['counts']['review_rows']} reviewed rows",
                ],
                [
                    "ranking_score_guards",
                    ranking_guards["source"],
                    ranking_guards["purpose"],
                    f"{ranking_guards['counts']['named_guards']} named guards",
                ],
                [
                    "benchmark_guardrails",
                    guardrails["source"],
                    guardrails["purpose"],
                    (
                        f"{guardrails['counts']['paragraph_rows']} paragraph rows; "
                        f"{guardrails['counts']['patient_portal_rows']} portal rows"
                    ),
                ],
            ],
        ),
        "## Plain-Language Rule Guide",
        "",
        "### Generic Meta Suppression",
        "",
        "This is the hard-stop layer for UMLS labels that are technically concepts but are bad search answers in ordinary use. It catches words and phrases that usually mean the system latched onto prose, chart structure, or a form field instead of a biomedical entity.",
        "",
        "- Use for: generic answers such as `Do not`, `Result`, `Instructions`, `Still`, `Unknown`, or `Problem` when they appear as standalone concepts.",
        "- Do not use for: valid longer clinical phrases that contain generic words, such as `Do not resuscitate` or a specific diagnostic result.",
        "- Guardrail: add a benchmark `disallowed_cuis` row or a unit test that proves the bad concept is suppressed while the valid clinical phrase still survives.",
        "",
        "### Clinical Alias Supplement",
        "",
        "This is the phrase-rescue layer. It adds explicit labels for real clinical phrases when the target CUI is correct but the default UMLS label index or evidence retrieval does not surface the wording users actually type.",
        "",
        "- Use for: abbreviations, shorthand, and clinically meaningful phrases such as `Head CT`, `PHQ-9`, or local active-label wording that should resolve to a known CUI.",
        "- Do not use for: current-versus-history interpretation, negation, generic noise, or concepts that need a new CUI rather than another label.",
        "- Guardrail: each row needs a `why`, a semantic type, a field, and context gates for risky short labels or ambiguous aliases.",
        "",
        "### Assertion and Currentness Context",
        "",
        "This layer interprets the status of a real mention. It decides whether a concept is current, negated, uncertain, historical, family history, planned, or confirmed before ranking penalties are applied.",
        "",
        "- Use for: cues like `old`, `another visit`, `history of`, `no evidence of`, `possible`, `planned`, or `confirmed` when they change how a nearby clinical mention should rank.",
        "- Do not use for: suppressing standalone generic concepts or adding missing synonyms.",
        "- Guardrail: add a benchmark row showing active/current CUIs above context CUIs, and add a unit test when the cue is reusable across query types.",
        "",
        "### Patient Portal Meta Context",
        "",
        "This layer handles patient-message wording. It recognizes that phrases such as `I am confused`, `I am worried`, `plain language`, or `what diagnosis should I use` describe the user's communication task, not the medical problem.",
        "",
        "- Use for: conversational portal-message words that otherwise outrank the active medical issue.",
        "- Do not use for: true clinical confusion, altered mental status, delirium, stroke, hypoglycemia, or other cases where `confused` is itself medically meaningful.",
        "- Guardrail: portal benchmark rows should include active CUIs, context/history CUIs, and disallowed meta CUIs.",
        "",
        "### Ranking Score Guards",
        "",
        "This layer handles reusable ranking error classes that are too contextual for hard suppression and too behavioral for alias data. A guard should be named, scoped, and visible in score breakdowns.",
        "",
        "- Use for: broad but valid concepts that should remain searchable, but should not outrank directly relevant anchors in a specific long-query context.",
        "- Do not use for: missing synonyms, generic prose concepts that should be suppressed outright, or one-off CUI-specific hacks without a repeatable error class.",
        "- Guardrail: add focused tests for both the demotion and the obvious direct-search false positive.",
        "",
        "### Precision Audit Outcomes",
        "",
        "This is the human judgment ledger for suspect results. It separates useful secondary concepts from true false positives so future score changes are measured against the right target.",
        "",
        "- Use for: deciding whether a result that looks extra is actually helpful clinical context or should become a rule candidate.",
        "- Do not use for: silently accepting broad drift without a readable reason.",
        "- Guardrail: every row needs a review class, action, and `why` that a reviewer can understand without reading the ranking code.",
        "",
        "### Benchmark Guardrails",
        "",
        "This is the repeatability layer. It turns known examples into runnable expectations so heuristic changes can be checked before they become permanent behavior.",
        "",
        "- Use for: user-visible failures, long patient messages, paragraph recall cases, PubMed abstracts, and known false positives.",
        "- Do not use for: undocumented anecdotes or one-off checks that cannot be rerun.",
        "- Guardrail: include expected CUIs, disallowed CUIs when relevant, and a short expected-behavior statement for the ranking intent.",
        "",
        "## Where to Put a New Rule",
        "",
        table(
            ["Problem", "Preferred Artifact", "Required Guardrail"],
            [
                [
                    "UMLS concept is generic prose or chart metadata, such as `Do not`, `Result`, or `Instructions`.",
                    "`src/qe_evidence_vectors/generic_filters.py`",
                    "A focused regression row with `disallowed_cuis`, or a unit test proving a clinical phrase such as DNR still survives.",
                ],
                [
                    "A real clinical phrase is missing or under-ranked, but the target CUI is known.",
                    "`config/active_label_supplement.tsv`",
                    "`why`, semantic type, field, context gates for risky aliases, and `python3 scripts/validate_active_label_supplement.py`.",
                ],
                [
                    "The mention is current versus old/history, negated, uncertain, planned, or family history.",
                    "`src/qe_evidence_vectors/search_assertions.py`",
                    "A patient/clinical benchmark row showing active CUIs above context CUIs, plus unit coverage when the cue is reusable.",
                ],
                [
                    "Patient portal prose contains conversational uncertainty or workflow words.",
                    "`src/qe_evidence_vectors/search_ranking.py` patient-message meta context",
                    "A portal row with active/current CUIs, context CUIs, and disallowed meta CUIs.",
                ],
                [
                    "A valid but broad ranked concept should remain searchable but stop winning in a repeatable context.",
                    "`src/qe_evidence_vectors/search_ranking.py` ranking score guard",
                    "A focused test for the failing context, a protection test for direct lookup, and a score-breakdown field.",
                ],
                [
                    "A non-primary concept is expected and useful, not a false positive.",
                    "`config/search_quality_useful_extra_cuis.tsv` and `config/search_quality_precision_audit_review.tsv`",
                    "Audit classification with a human-readable `why`.",
                ],
                [
                    "A new class of user-visible failure needs tracking.",
                    "`config/search_quality_*queries.tsv`",
                    "Expected CUIs, disallowed CUIs when applicable, and a short expected-behavior statement.",
                ],
            ],
        ),
        "## Current Generic Suppression",
        "",
        f"- Blocked labels: {generic['counts']['blocked_labels']}",
        f"- Blocked CUIs: {generic['counts']['blocked_cuis']}",
        f"- Blocked exact queries: {generic['counts']['blocked_queries']}",
        f"- Label examples: {inline_list(generic['examples']['labels'])}",
        f"- CUI examples: {inline_list(generic['examples']['cuis'])}",
        "",
        "Rule of thumb: add a generic suppression only when the concept is not useful as a standalone biomedical answer. If a longer clinical phrase is valid, protect it separately in a benchmark row.",
        "",
        "## Current Clinical Alias Supplement",
        "",
        f"- Rows: {active['counts']['rows']}",
        f"- Unique CUIs: {active['counts']['unique_cuis']}",
        f"- Rows with `context_any`: {active['counts']['rows_with_context_any']}",
        f"- Rows with `block_any`: {active['counts']['rows_with_block_any']}",
        "",
        "Field counts:",
        "",
        table(
            ["Field", "Rows"],
            [[row["value"] or "(blank)", row["count"]] for row in active["field_counts"]],
        ),
        "Top semantic type counts:",
        "",
        table(
            ["Semantic Type", "Rows"],
            [
                [row["value"] or "(blank)", row["count"]]
                for row in active["semantic_type_counts"][:12]
            ],
        ),
        "## Current Assertion and Currentness Cues",
        "",
        "Before-cue counts:",
        "",
        table(
            ["Status", "Cue Count"],
            [[status, assertion["before_counts"].get(status, 0)] for status in STATUS_ORDER],
        ),
        "After-cue counts:",
        "",
        table(
            ["Status", "Cue Count"],
            [[status, assertion["after_counts"].get(status, 0)] for status in STATUS_ORDER],
        ),
        f"Chart-history cues: {inline_list(assertion['chart_history_cues'])}",
        "",
        "Rule of thumb: currentness belongs here when it changes how a real clinical mention should be interpreted. Generic words belong in suppression; missing synonyms belong in the active-label supplement.",
        "",
        "## Current Patient Portal Meta Layer",
        "",
        f"- Context tokens: {inline_list(portal['tokens']['context'])}",
        f"- Self tokens: {inline_list(portal['tokens']['self'])}",
        f"- Noise tokens: {inline_list(portal['tokens']['noise'])}",
        f"- Clinical confusion exception tokens: {inline_list(portal['tokens']['clinical_confusion_exceptions'])}",
        "",
        "Rule of thumb: this layer should require patient-message context before suppressing words like `confused` or `worried`, and it should exempt clinical confusion contexts such as hypoglycemia, delirium, or stroke.",
        "",
        "## Current Ranking Score Guards",
        "",
        table(
            ["Guard", "Purpose", "Scope", "Guardrail"],
            [
                [
                    guard["name"],
                    guard["purpose"],
                    (
                        f"Penalty {guard['penalty']}; min query tokens "
                        f"{guard['minimum_query_tokens']}; matched spans "
                        f"{inline_list(guard['matched_spans'], limit=8)}"
                    ),
                    guard["guardrail"],
                ]
                for guard in ranking_guards["guards"]
            ],
        ),
        "Rule of thumb: score guards should be visible in `score_breakdown`, limited by context, and backed by a positive test plus a direct-search protection test.",
        "",
        "## Current Audit and Benchmark Guardrails",
        "",
        table(
            ["Artifact", "Rows / Values"],
            [
                [
                    "Precision audit review rows",
                    precision["counts"]["review_rows"],
                ],
                [
                    "Known useful extra CUI rows",
                    precision["counts"]["useful_extra_rows"],
                ],
                [
                    "Paragraph benchmark rows",
                    guardrails["counts"]["paragraph_rows"],
                ],
                [
                    "Paragraph rows with disallowed CUIs",
                    guardrails["counts"]["paragraph_rows_with_disallowed_cuis"],
                ],
                [
                    "Patient portal benchmark rows",
                    guardrails["counts"]["patient_portal_rows"],
                ],
                [
                    "Patient portal rows with disallowed CUIs",
                    guardrails["counts"]["portal_rows_with_disallowed_cuis"],
                ],
                [
                    "Patient portal active CUI values",
                    guardrails["counts"]["portal_active_cui_values"],
                ],
                [
                    "Patient portal context CUI values",
                    guardrails["counts"]["portal_context_cui_values"],
                ],
            ],
        ),
        "Precision audit review classes:",
        "",
        table(
            ["Review Class", "Rows"],
            [
                [row["value"] or "(blank)", row["count"]]
                for row in precision["review_class_counts"]
            ],
        ),
        "Precision audit actions:",
        "",
        table(
            ["Action", "Rows"],
            [[row["value"] or "(blank)", row["count"]] for row in precision["action_counts"]],
        ),
        "## Review Standard",
        "",
        "A new heuristic is sustainable when all of these are true:",
        "",
        "1. It has a named class from this inventory.",
        "2. The rule source is the narrowest artifact that can express it.",
        "3. The `why` is readable by someone who did not write the code.",
        "4. It has a focused query, disallowed CUI, useful-extra audit row, or unit test.",
        "5. The full clinical smoke is run when the rule can affect broad ranking behavior.",
        "",
    ]
    return "\n".join(lines)


def render_html(inventory: dict) -> str:
    classes = {item["name"]: item for item in inventory["rule_classes"]}
    totals = inventory_totals(inventory)
    generic = classes["generic_meta_suppression"]
    active = classes["clinical_alias_supplement"]
    assertion = classes["assertion_context"]
    portal = classes["patient_portal_meta_context"]
    ranking_guards = classes["ranking_score_guards"]
    precision = classes["precision_audit_outcomes"]
    guardrails = classes["benchmark_guardrails"]

    rule_class_rows = [
        [
            "generic_meta_suppression",
            source_link(generic["source"]),
            generic["purpose"],
            (
                f"{generic['counts']['blocked_labels']} labels; "
                f"{generic['counts']['blocked_cuis']} CUIs; "
                f"{generic['counts']['blocked_queries']} query blocks"
            ),
        ],
        [
            "clinical_alias_supplement",
            source_link(active["source"]),
            active["purpose"],
            f"{active['counts']['rows']} rows; {active['counts']['unique_cuis']} CUIs",
        ],
        [
            "assertion_context",
            source_link(assertion["source"]),
            assertion["purpose"],
            (
                f"{assertion['counts']['before_cues']} before-cues; "
                f"{assertion['counts']['after_cues']} after-cues"
            ),
        ],
        [
            "patient_portal_meta_context",
            source_link(portal["source"]),
            portal["purpose"],
            (
                f"{portal['counts']['context_tokens']} context tokens; "
                f"{portal['counts']['noise_tokens']} noise tokens"
            ),
        ],
        [
            "precision_audit_outcomes",
            source_link(precision["source"]),
            precision["purpose"],
            f"{precision['counts']['review_rows']} reviewed rows",
        ],
        [
            "ranking_score_guards",
            source_link(ranking_guards["source"]),
            ranking_guards["purpose"],
            f"{ranking_guards['counts']['named_guards']} named guards",
        ],
        [
            "benchmark_guardrails",
            source_link(guardrails["source"]),
            guardrails["purpose"],
            (
                f"{guardrails['counts']['paragraph_rows']} paragraph rows; "
                f"{guardrails['counts']['patient_portal_rows']} portal rows"
            ),
        ],
    ]
    placement_rows = [
        [
            "UMLS concept is generic prose or chart metadata.",
            source_link("src/qe_evidence_vectors/generic_filters.py"),
            "Add a focused regression row with disallowed CUIs or a unit test proving a valid clinical phrase still survives.",
        ],
        [
            "A real clinical phrase is missing or under-ranked, but the target CUI is known.",
            source_link("config/active_label_supplement.tsv"),
            "Include why, semantic type, field, context gates for risky aliases, and run active-label validation.",
        ],
        [
            "The mention is current versus old/history, negated, uncertain, planned, or family history.",
            source_link("src/qe_evidence_vectors/search_assertions.py"),
            "Add a patient/clinical benchmark row showing active CUIs above context CUIs, plus reusable unit coverage.",
        ],
        [
            "Patient portal prose contains conversational uncertainty or workflow words.",
            source_link("src/qe_evidence_vectors/search_ranking.py"),
            "Add a portal row with active/current CUIs, context CUIs, and disallowed meta CUIs.",
        ],
        [
            "A valid but broad ranked concept should remain searchable but stop winning in a repeatable context.",
            source_link("src/qe_evidence_vectors/search_ranking.py"),
            "Add a focused test for the failing context, a direct-search protection test, and a score-breakdown field.",
        ],
        [
            "A non-primary concept is expected and useful, not a false positive.",
            source_link("config/search_quality_useful_extra_cuis.tsv"),
            "Record audit classification with a human-readable why.",
        ],
        [
            "A new class of user-visible failure needs tracking.",
            source_link("config/search_quality_*queries.tsv"),
            "Include expected CUIs, disallowed CUIs when relevant, and a short expected-behavior statement.",
        ],
    ]
    guard_rows = [
        [
            guard["name"],
            guard["purpose"],
            HtmlCell(
                f"Penalty {guard['penalty']}; min query tokens "
                f"{guard['minimum_query_tokens']}; matched spans "
                f"{html_inline_list(guard['matched_spans'], limit=8)}"
            ),
            HtmlCell(f"<code>{html_escape(guard['guardrail'])}</code>"),
        ]
        for guard in ranking_guards["guards"]
    ]
    summary_cards = [
        ("Active heuristic items", totals["active_heuristic_items"], "Live search path"),
        ("Rule classes", totals["rule_classes"], "Named layers"),
        ("Guardrail rows", totals["audit_guardrail_rows"], "Audit and benchmark"),
        ("Generic suppression", totals["generic_suppression_items"], "Labels, CUIs, queries"),
        ("Clinical aliases", totals["clinical_alias_rows"], "Reviewed rows"),
        ("Assertion cues", totals["assertion_cues"], "Before, after, chart history"),
        ("Portal meta tokens", totals["patient_portal_tokens"], "Tokens and exceptions"),
        ("Score guards", totals["ranking_score_guards"], "Named guards"),
    ]
    summary_html = "".join(
        (
            '<div class="metric">'
            f"<span>{html_escape(label)}</span>"
            f"<strong>{value:,}</strong>"
            f'<div class="muted">{html_escape(detail)}</div>'
            "</div>"
        )
        for label, value, detail in summary_cards
    )
    audit_guardrail_rows = [
        ["Precision audit review rows", precision["counts"]["review_rows"]],
        ["Known useful extra CUI rows", precision["counts"]["useful_extra_rows"]],
        ["Paragraph benchmark rows", guardrails["counts"]["paragraph_rows"]],
        [
            "Paragraph rows with disallowed CUIs",
            guardrails["counts"]["paragraph_rows_with_disallowed_cuis"],
        ],
        ["Patient portal benchmark rows", guardrails["counts"]["patient_portal_rows"]],
        [
            "Patient portal rows with disallowed CUIs",
            guardrails["counts"]["portal_rows_with_disallowed_cuis"],
        ],
        ["Patient portal active CUI values", guardrails["counts"]["portal_active_cui_values"]],
        ["Patient portal context CUI values", guardrails["counts"]["portal_context_cui_values"]],
    ]

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Search Rule Inventory</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #5d6978;
      --line: #d7dde5;
      --accent: #176b87;
      --accent-soft: #e8f4f7;
      --warn: #8c5b14;
      --warn-soft: #fff4dc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 48px;
    }}
    header {{
      margin-bottom: 22px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 34px 0 12px;
      font-size: 20px;
      letter-spacing: 0;
    }}
    h3 {{
      margin: 24px 0 8px;
      font-size: 16px;
      letter-spacing: 0;
    }}
    p {{
      margin: 0 0 12px;
    }}
    .muted {{
      color: var(--muted);
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 10px;
      margin: 18px 0 26px;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .metric strong {{
      display: block;
      font-size: 26px;
      line-height: 1;
      margin-bottom: 7px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    .note {{
      background: var(--accent-soft);
      border: 1px solid #b7dce5;
      border-radius: 8px;
      padding: 14px;
      margin: 16px 0;
    }}
    .warning {{
      background: var(--warn-soft);
      border-color: #f1d6a3;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      margin: 10px 0 20px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #eef2f6;
      color: #233142;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    tr:last-child td {{
      border-bottom: 0;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      background: #eef2f6;
      border-radius: 4px;
      padding: 1px 4px;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
    a:hover {{
      text-decoration: underline;
    }}
    ul, ol {{
      margin: 8px 0 16px 22px;
      padding: 0;
    }}
    li {{
      margin: 6px 0;
    }}
    .two-col {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    @media (max-width: 720px) {{
      main {{
        width: min(100vw - 20px, 1180px);
        padding-top: 18px;
      }}
      table {{
        display: block;
        overflow-x: auto;
      }}
      h1 {{
        font-size: 25px;
      }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>Search Rule Inventory</h1>
    <p class="muted">Generated from the current checkout by <code>python3 scripts/build_search_rule_inventory.py</code>.</p>
    <p class="muted">Use this as the review surface for heuristic changes. Every rule should have a class, a source artifact, and a benchmark or audit artifact explaining why it exists.</p>
  </header>

  <section class="summary-grid" aria-label="Inventory summary">
    {summary_html}
  </section>

  <section class="note">
    <p><strong>Interpretation:</strong> active heuristic items are entries that can directly shape live search behavior. Guardrail rows are review and benchmark data that govern changes, but they are not all runtime rules.</p>
  </section>

  <h2>Rule Classes</h2>
  {html_table(["Class", "Source", "Purpose", "Current Size"], rule_class_rows)}

  <h2>Why This Exists</h2>
  <ol>
    <li>Suppress generic/meta concepts when UMLS exposes ordinary prose as concepts.</li>
    <li>Rescue clinical aliases when a real clinical phrase should map to a known CUI.</li>
    <li>Classify assertion/currentness when a mention is old, negated, uncertain, planned, or active.</li>
    <li>Handle patient-message meta language when conversational words should not outrank clinical entities.</li>
    <li>Apply narrow ranking score guards when a recurring error class cannot be represented as suppression or alias data.</li>
    <li>Audit useful extras versus false positives so ranking changes target real errors.</li>
    <li>Guard with benchmark rows so each improvement is repeatable.</li>
  </ol>

  <h2>Where To Put A New Rule</h2>
  {html_table(["Problem", "Preferred Artifact", "Required Guardrail"], placement_rows)}

  <h2>Current Generic Suppression</h2>
  <ul>
    <li>Blocked labels: <strong>{generic['counts']['blocked_labels']}</strong></li>
    <li>Blocked CUIs: <strong>{generic['counts']['blocked_cuis']}</strong></li>
    <li>Blocked exact queries: <strong>{generic['counts']['blocked_queries']}</strong></li>
    <li>Label examples: {html_inline_list(generic['examples']['labels'])}</li>
    <li>CUI examples: {html_inline_list(generic['examples']['cuis'])}</li>
  </ul>

  <h2>Current Clinical Alias Supplement</h2>
  <ul>
    <li>Rows: <strong>{active['counts']['rows']}</strong></li>
    <li>Unique CUIs: <strong>{active['counts']['unique_cuis']}</strong></li>
    <li>Rows with <code>context_any</code>: <strong>{active['counts']['rows_with_context_any']}</strong></li>
    <li>Rows with <code>block_any</code>: <strong>{active['counts']['rows_with_block_any']}</strong></li>
  </ul>
  <div class="two-col">
    <section>
      <h3>Field Counts</h3>
      {html_table(["Field", "Rows"], [[row["value"] or "(blank)", row["count"]] for row in active["field_counts"]])}
    </section>
    <section>
      <h3>Top Semantic Type Counts</h3>
      {html_table(["Semantic Type", "Rows"], [[row["value"] or "(blank)", row["count"]] for row in active["semantic_type_counts"][:12]])}
    </section>
  </div>

  <h2>Current Assertion And Currentness Cues</h2>
  <div class="two-col">
    <section>
      <h3>Before-Cue Counts</h3>
      {html_table(["Status", "Cue Count"], [[status, assertion["before_counts"].get(status, 0)] for status in STATUS_ORDER])}
    </section>
    <section>
      <h3>After-Cue Counts</h3>
      {html_table(["Status", "Cue Count"], [[status, assertion["after_counts"].get(status, 0)] for status in STATUS_ORDER])}
    </section>
  </div>
  <p>Chart-history cues: {html_inline_list(assertion['chart_history_cues'])}</p>

  <h2>Current Patient Portal Meta Layer</h2>
  <ul>
    <li>Context tokens: {html_inline_list(portal['tokens']['context'])}</li>
    <li>Self tokens: {html_inline_list(portal['tokens']['self'])}</li>
    <li>Noise tokens: {html_inline_list(portal['tokens']['noise'])}</li>
    <li>Clinical confusion exception tokens: {html_inline_list(portal['tokens']['clinical_confusion_exceptions'])}</li>
  </ul>

  <h2>Current Ranking Score Guards</h2>
  {html_table(["Guard", "Purpose", "Scope", "Guardrail"], guard_rows)}

  <h2>Current Audit And Benchmark Guardrails</h2>
  {html_table(["Artifact", "Rows / Values"], audit_guardrail_rows)}
  <div class="two-col">
    <section>
      <h3>Precision Audit Review Classes</h3>
      {html_table(["Review Class", "Rows"], [[row["value"] or "(blank)", row["count"]] for row in precision["review_class_counts"]])}
    </section>
    <section>
      <h3>Precision Audit Actions</h3>
      {html_table(["Action", "Rows"], [[row["value"] or "(blank)", row["count"]] for row in precision["action_counts"]])}
    </section>
  </div>

  <h2>Review Standard</h2>
  <ol>
    <li>It has a named class from this inventory.</li>
    <li>The rule source is the narrowest artifact that can express it.</li>
    <li>The why is readable by someone who did not write the code.</li>
    <li>It has a focused query, disallowed CUI, useful-extra audit row, or unit test.</li>
    <li>The full clinical smoke is run when the rule can affect broad ranking behavior.</li>
  </ol>
</main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional Markdown inventory to write.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON inventory to write for automated diffs.",
    )
    parser.add_argument(
        "--html-output",
        type=Path,
        default=DEFAULT_HTML_OUTPUT,
        help="HTML inventory to write.",
    )
    parser.add_argument(
        "--no-html-output",
        action="store_true",
        help="Skip writing the HTML inventory.",
    )
    args = parser.parse_args()

    inventory = build_inventory()
    html_report = render_html(inventory)

    output = None
    if args.output:
        markdown = render_markdown(inventory)
        output = args.output.expanduser()
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown, encoding="utf-8")

    if args.json_output:
        json_output = args.json_output.expanduser()
        if not json_output.is_absolute():
            json_output = ROOT / json_output
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    html_output = None
    if not args.no_html_output and args.html_output:
        html_output = args.html_output.expanduser()
        if not html_output.is_absolute():
            html_output = ROOT / html_output
        html_output.parent.mkdir(parents=True, exist_ok=True)
        html_output.write_text(html_report, encoding="utf-8")

    if output:
        print(f"wrote {relative(output)}")
    if html_output:
        print(f"wrote {relative(html_output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
