from __future__ import annotations

import gzip
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_medmentions_benchmark import (  # noqa: E402
    document_query_rows,
    medmentions_category_for_tuis,
    mention_query_text,
    mention_query_rows,
    parse_pubtator,
    score_payload,
    summarize_results,
)


PUBTATOR_SAMPLE = """123|t|DCTN4 as a modifier of chronic infection
123|a|Pseudomonas aeruginosa infection in cystic fibrosis patients.
123\t0\t5\tDCTN4\tT116,T123\tC4308010
123\t23\t40\tchronic infection\tT047\tC0854135
123\t73\t88\tcystic fibrosis\tT047\tC0010674

456|t|Metformin response
456|a|Metformin improved glucose control.
456\t0\t9\tMetformin\tT121\tC0025598
"""


def write_gzip(path: Path, text: str) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(text)


def test_parse_pubtator_reads_documents_and_mentions(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus_pubtator.txt.gz"
    write_gzip(corpus, PUBTATOR_SAMPLE)

    documents = parse_pubtator(corpus)

    assert [document.pmid for document in documents] == ["123", "456"]
    assert documents[0].title == "DCTN4 as a modifier of chronic infection"
    assert documents[0].mentions[0].cuis == ("C4308010",)
    assert documents[0].unique_cuis == ("C0010674", "C0854135", "C4308010")


def test_query_rows_include_split_and_expected_cuis(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus_pubtator.txt.gz"
    write_gzip(corpus, PUBTATOR_SAMPLE)
    documents = parse_pubtator(corpus)
    splits = {"123": "dev", "456": "test"}

    mentions = mention_query_rows(
        documents,
        subset="st21pv",
        pmid_to_split=splits,
        selected_splits={"dev"},
        selected_categories=set(),
        context_chars=40,
    )
    docs = document_query_rows(
        documents,
        subset="st21pv",
        pmid_to_split=splits,
        selected_splits={"dev"},
        selected_categories=set(),
    )

    assert len(mentions) == 3
    assert mentions[0]["split"] == "dev"
    assert mentions[0]["expected_cuis"] == "C4308010"
    assert mentions[0]["benchmark_type"] == "mention_context"
    assert mentions[0]["medmentions_category"] == "clinical_useful"
    assert "Context:" in mentions[0]["query"]
    assert docs == [
        {
            "id": "medmentions_st21pv_dev_123_document",
            "query": (
                "PubMed PMID 123. DCTN4 as a modifier of chronic infection "
                "Pseudomonas aeruginosa infection in cystic fibrosis patients."
            ),
            "expected_cuis": "C0010674|C0854135|C4308010",
            "why": (
                "MedMentions document-level CUI set from annotated title/abstract "
                "mentions in PMID 123; category=all."
            ),
            "disallowed_cuis": "",
            "benchmark_type": "document_cui_recall",
            "subset": "st21pv",
            "split": "dev",
            "pmid": "123",
            "mention_index": "",
            "mention_text": "",
            "start": "",
            "end": "",
            "semantic_types": "",
            "medmentions_category": "all",
        }
    ]


def test_mention_query_rows_support_query_styles(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus_pubtator.txt.gz"
    write_gzip(corpus, PUBTATOR_SAMPLE)
    documents = parse_pubtator(corpus)

    mention_only = mention_query_rows(
        documents,
        subset="st21pv",
        pmid_to_split={"123": "dev"},
        selected_splits={"dev"},
        selected_categories=set(),
        context_chars=40,
        query_style="mention_only",
        limit=1,
    )
    anchored = mention_query_text(
        "DCTN4",
        context="DCTN4 as a modifier of chronic infection.",
        query_style="anchored_context",
    )

    assert mention_only[0]["query"] == "DCTN4"
    assert mention_only[0]["benchmark_type"] == "mention_only"
    assert anchored == "Mention: DCTN4. Context: DCTN4 as a modifier of chronic infection."


def test_category_filter_excludes_suppression_audit_mentions(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus_pubtator.txt.gz"
    write_gzip(
        corpus,
        """123|t|United States infection
123|a|United States reports cystic fibrosis.
123\t0\t13\tUnited States\tT082\tC0041703
123\t22\t39\tcystic fibrosis\tT047\tC0010674
""",
    )
    documents = parse_pubtator(corpus)

    mentions = mention_query_rows(
        documents,
        subset="st21pv",
        pmid_to_split={"123": "dev"},
        selected_splits={"dev"},
        selected_categories={"clinical_useful"},
        context_chars=20,
    )

    assert medmentions_category_for_tuis("T082") == "suppression_audit"
    assert medmentions_category_for_tuis("T047") == "clinical_useful"
    assert [row["mention_text"] for row in mentions] == ["cystic fibrosis"]


def test_score_payload_and_summary_report_rank_metrics() -> None:
    row = {
        "id": "q1",
        "benchmark_type": "mention_context",
        "subset": "st21pv",
        "split": "dev",
        "pmid": "123",
        "medmentions_category": "clinical_useful",
        "expected_cuis": "C0010674|C0854135",
        "query": "cystic fibrosis context",
    }
    payload = {
        "backend": "elasticsearch",
        "elapsed_ms": 12,
        "hits": [
            {"cui": "C0000001", "name": "Wrong"},
            {"cui": "C0010674", "name": "Cystic Fibrosis"},
        ],
        "linked_concepts": [{"cui": "C0854135"}],
    }

    scored = score_payload(row, payload, elapsed_seconds=0.02, top_k=10)
    summary = summarize_results([scored], top_k=10)

    assert scored["found_at_1"] == "0"
    assert scored["found_at_3"] == "1"
    assert scored["first_expected_rank"] == "2"
    assert scored["recall_at_10"] == "0.500000"
    assert scored["linked_expected_found"] == "1"
    assert summary["top1_accuracy"] == 0.0
    assert summary["top3_accuracy"] == 1.0
    assert summary["mean_recall_at_10"] == 0.5
    assert summary["mrr"] == 0.5
    assert summary["by_medmentions_category"]["clinical_useful"]["queries"] == 1
