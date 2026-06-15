from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_pubmed_long_document_slice import (
    materialize_slice,
    read_query_rows,
    read_slice,
    write_query_tsv as write_long_document_query_tsv,
)
from fetch_pubmed_paragraph_queries import curated_query_row, read_curation, write_query_tsv

ROOT = Path(__file__).resolve().parents[1]


def test_read_curation_keys_by_pmid(tmp_path: Path) -> None:
    path = tmp_path / "curation.tsv"
    path.write_text(
        "pmid\tsplit\treview_status\texpected_cuis\tdisallowed_cuis\twhy\n"
        "# ignored comment\n"
        "123\tdev\tapproved\tC001|C002\tC999\tReviewed from abstract text.\n",
        encoding="utf-8",
    )

    rows = read_curation(path)

    assert rows["123"]["expected_cuis"] == "C001|C002"
    assert rows["123"]["split"] == "dev"


def test_curated_query_row_uses_per_abstract_expectations() -> None:
    topic = {
        "id": "topic",
        "term": "example",
        "expected_cuis": "C_TOPIC",
        "disallowed_cuis": "C_BAD_TOPIC",
        "why": "Topic reason.",
    }
    article = {"pmid": "123", "title": "Title", "abstract": "Abstract"}
    curation = {
        "expected_cuis": "C_ABSTRACT",
        "disallowed_cuis": "C_BAD_ABSTRACT",
        "split": "heldout",
        "review_status": "approved",
        "why": "Abstract reason.",
    }

    row = curated_query_row(
        topic=topic,
        article=article,
        query="PubMed PMID 123. Title Abstract",
        row_id="topic_123",
        curation=curation,
    )

    assert row["expected_cuis"] == "C_ABSTRACT"
    assert row["disallowed_cuis"] == "C_BAD_ABSTRACT"
    assert row["split"] == "heldout"
    assert row["expected_source"] == "per_abstract"
    assert row["review_status"] == "approved"


def test_curated_query_row_marks_uncurated_topic_fallback() -> None:
    topic = {"id": "topic", "term": "example", "expected_cuis": "C_TOPIC", "why": "Topic reason."}
    article = {"pmid": "123", "title": "Title", "abstract": "Abstract"}

    row = curated_query_row(
        topic=topic,
        article=article,
        query="PubMed PMID 123. Title Abstract",
        row_id="topic_123",
        curation=None,
    )

    assert row["expected_cuis"] == "C_TOPIC"
    assert row["split"] == "unreviewed"
    assert row["expected_source"] == "topic_fallback"
    assert row["review_status"] == "pending"


def test_write_query_tsv_keeps_evaluator_columns_only(tmp_path: Path) -> None:
    path = tmp_path / "queries.tsv"
    write_query_tsv(
        path,
        [
            {
                "id": "row_1",
                "query": "query text",
                "expected_cuis": "C001",
                "why": "because",
                "disallowed_cuis": "C999",
                "split": "dev",
                "review_status": "approved",
            }
        ],
    )

    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert rows == [
        {
            "id": "row_1",
            "query": "query text",
            "expected_cuis": "C001",
            "why": "because",
            "disallowed_cuis": "C999",
        }
    ]


def test_pubmed_long_document_slice_config_is_focused_dev_set() -> None:
    rows = read_slice(ROOT / "config" / "search_quality_pubmed_long_document_slice.tsv")

    assert len(rows) >= 6
    assert {row["split"] for row in rows} == {"dev"}
    assert len({row["id"] for row in rows}) == len(rows)
    assert len({row["focus"] for row in rows}) == len(rows)
    assert any("pharmacogenomics" in row["focus"] for row in rows)
    assert any("oncology" in row["focus"] for row in rows)


def test_materialize_pubmed_long_document_slice_from_seed_rows(tmp_path: Path) -> None:
    slice_path = tmp_path / "slice.tsv"
    slice_path.write_text(
        "id\tsplit\tfocus\twhy\n"
        "pubmed_example_1\tdev\ttreatment secondary concepts\tChecks secondary concepts.\n",
        encoding="utf-8",
    )
    query_path = tmp_path / "queries.tsv"
    long_query = ("PubMed PMID 1. " + ("Long abstract text with many biomedical details. " * 20)).strip()
    query_path.write_text(
        "id\tquery\texpected_cuis\twhy\tdisallowed_cuis\n"
        f"pubmed_example_1\t{long_query}\tC001|C002\tOriginal curation reason.\tC999\n",
        encoding="utf-8",
    )

    slice_rows = read_slice(slice_path)
    query_rows, _query_sources = read_query_rows([query_path])
    selected = materialize_slice(slice_rows, query_rows)

    assert selected == [
        {
            "id": "pubmed_example_1",
            "query": long_query,
            "expected_cuis": "C001|C002",
            "why": (
                "Original curation reason. Focused long-document lane: treatment secondary concepts. "
                "Slice reason: Checks secondary concepts."
            ),
            "disallowed_cuis": "C999",
        }
    ]

    output_path = tmp_path / "focused.tsv"
    write_long_document_query_tsv(output_path, selected)
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert rows[0]["id"] == "pubmed_example_1"
    assert set(rows[0]) == {"id", "query", "expected_cuis", "why", "disallowed_cuis"}
