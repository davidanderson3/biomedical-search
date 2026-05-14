from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_openalex_cited_evidence import (  # noqa: E402
    document_identity_keys,
    filter_existing_documents,
    load_existing_document_keys,
    read_query_file,
)
from qe_evidence_vectors.schema import CorpusDocument  # noqa: E402


def test_openalex_missing_filter_matches_existing_ids_and_titles(tmp_path: Path) -> None:
    existing = tmp_path / "existing.jsonl"
    existing.write_text(
        json.dumps(
            {
                "doc_id": "PMID:12345",
                "title": "Existing Trial of a Common Drug",
                "metadata": {"doi": "10.1000/example", "pmid": "12345"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    existing_keys = load_existing_document_keys([existing])

    duplicate_by_doi = CorpusDocument(
        doc_id="OPENALEX:W1",
        source="openalex_top_cited",
        title="Different title",
        text="Different title",
        metadata={"doi": "https://doi.org/10.1000/example", "cited_by_count": 900},
    )
    duplicate_by_title = CorpusDocument(
        doc_id="OPENALEX:W2",
        source="openalex_top_cited",
        title="Existing trial of a common drug",
        text="Existing trial of a common drug",
        metadata={"cited_by_count": 800},
    )
    novel = CorpusDocument(
        doc_id="OPENALEX:W3",
        source="openalex_top_cited",
        title="Novel Highly Cited Article",
        text="Novel Highly Cited Article",
        metadata={"openalex_id": "https://openalex.org/W3", "cited_by_count": 700},
    )

    kept, excluded = filter_existing_documents(
        [duplicate_by_doi, duplicate_by_title, novel],
        existing_keys,
    )

    assert excluded == 2
    assert kept == [novel]
    assert "openalex:w3" in document_identity_keys(novel)


def test_openalex_query_file_reads_tsv_query_column(tmp_path: Path) -> None:
    query_file = tmp_path / "queries.tsv"
    query_file.write_text(
        "query_id\tquery\trationale\n"
        "a\tdiabetes semaglutide outcomes\tcommon drug evidence\n"
        "b\tsepsis antibiotics mortality\tinfection evidence\n",
        encoding="utf-8",
    )

    assert read_query_file(query_file) == [
        "diabetes semaglutide outcomes",
        "sepsis antibiotics mortality",
    ]
