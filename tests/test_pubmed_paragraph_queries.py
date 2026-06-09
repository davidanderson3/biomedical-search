from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from fetch_pubmed_paragraph_queries import curated_query_row, read_curation, write_query_tsv


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
