from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_trec_benchmark import (  # noqa: E402
    build_corpus_index,
    build_coverage_rows,
    document_query_rows,
    merge_qrels,
    parse_qrels,
    parse_topics,
    score_payload,
    summarize_results,
    summarize_coverage,
)


def test_parse_topics_and_qrels_for_precision_medicine(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.xml"
    topics_path.write_text(
        """<topics>
  <topic number="1">
    <disease>non-small cell lung cancer</disease>
    <gene>EGFR exon 20 insertion</gene>
    <demographic>64-year-old woman</demographic>
  </topic>
</topics>
""",
        encoding="utf-8",
    )
    qrels_path = tmp_path / "qrels.txt"
    qrels_path.write_text(
        """1 0 12345 2
1 0 NCT00000001 1
1 0 99999 0
""",
        encoding="utf-8",
    )

    topics = parse_topics(topics_path, track="precision_medicine")
    qrels = parse_qrels(qrels_path, track="pm")
    rows = document_query_rows(topics, qrels)

    assert topics[0].topic_id == "1"
    assert "Disease: non-small cell lung cancer" in topics[0].query
    assert qrels[0].doc_id == "PMID:12345"
    assert qrels[1].doc_id == "NCT:NCT00000001"
    assert qrels[2].is_positive is False
    assert rows[0]["expected_doc_ids"] == "NCT:NCT00000001|PMID:12345"
    assert rows[0]["expected_pubmed_ids"] == "12345"
    assert rows[0]["expected_clinical_trial_ids"] == "NCT00000001"
    assert rows[0]["benchmark_type"] == "document_source_retrieval"
    assert rows[0]["unjudged_policy"] == "unknown_not_false_positive"
    assert rows[0]["coverage_policy"] == "all_judged_positives"


def test_coverage_resolves_judged_ids_against_local_corpora(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.tsv"
    topics_path.write_text("topic_id\tquery\n1\tEGFR lung cancer\n", encoding="utf-8")
    qrels_path = tmp_path / "qrels.txt"
    qrels_path.write_text(
        """1 0 PMID:12345 2
1 0 NCT00000001 1
1 0 PMID:99999 0
""",
        encoding="utf-8",
    )
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "doc_id": "PMID:12345",
                        "source": "pubmed",
                        "title": "EGFR exon 20 insertion lung cancer",
                        "metadata": {"pmid": "12345"},
                    }
                ),
                json.dumps(
                    {
                        "doc_id": "NCT:NCT00000001",
                        "source": "clinicaltrials_gov",
                        "title": "EGFR inhibitor trial",
                        "metadata": {"nct_id": "NCT00000001"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    qrels = parse_qrels(qrels_path, track="precision_medicine")
    corpus_index, corpus_summary = build_corpus_index([corpus_path])
    coverage = build_coverage_rows(qrels, corpus_index)
    summary = summarize_coverage(qrels, coverage, corpus_summary)

    assert summary["positive_judgments"] == 2
    assert summary["positive_resolved"] == 2
    assert summary["positive_coverage_rate"] == 1.0
    assert {row["doc_id"]: row["resolved"] for row in coverage} == {
        "PMID:12345": "1",
        "NCT:NCT00000001": "1",
        "PMID:99999": "0",
    }


def test_multiple_qrels_files_merge_abstracts_and_trials(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.xml"
    topics_path.write_text(
        """<topics>
  <topic number="1">
    <disease>melanoma</disease>
    <gene>BRAF V600E</gene>
  </topic>
</topics>
""",
        encoding="utf-8",
    )
    abstract_qrels = tmp_path / "abstracts.qrels"
    abstract_qrels.write_text("1 0 12345 1\n1 0 77777 0\n", encoding="utf-8")
    trial_qrels = tmp_path / "trials.qrels"
    trial_qrels.write_text("1 0 NCT00123456 2\n1 0 12345 0\n", encoding="utf-8")

    topics = parse_topics(topics_path, track="pm")
    qrels = merge_qrels(
        [
            *parse_qrels(abstract_qrels, track="pm"),
            *parse_qrels(trial_qrels, track="pm"),
        ]
    )
    rows = document_query_rows(topics, qrels)

    assert rows[0]["expected_doc_ids"] == "NCT:NCT00123456|PMID:12345"
    assert rows[0]["expected_pubmed_ids"] == "12345"
    assert rows[0]["expected_clinical_trial_ids"] == "NCT00123456"


def test_document_query_rows_can_limit_to_resolved_positive_ids(tmp_path: Path) -> None:
    topics_path = tmp_path / "topics.tsv"
    topics_path.write_text("topic_id\tquery\n1\tEGFR lung cancer\n", encoding="utf-8")
    qrels_path = tmp_path / "qrels.txt"
    qrels_path.write_text(
        """1 0 PMID:12345 2
1 0 NCT00000001 1
1 0 PMID:99999 1
""",
        encoding="utf-8",
    )

    topics = parse_topics(topics_path, track="precision_medicine")
    qrels = parse_qrels(qrels_path, track="precision_medicine")
    rows = document_query_rows(
        topics,
        qrels,
        allowed_doc_ids={"PMID:12345"},
        coverage_policy="resolved_local_judged_positives",
    )

    assert rows[0]["expected_doc_ids"] == "PMID:12345"
    assert rows[0]["coverage_policy"] == "resolved_local_judged_positives"


def test_clinical_decision_support_topics_parse_description_summary(tmp_path: Path) -> None:
    topics_path = tmp_path / "cds_topics.xml"
    topics_path.write_text(
        """<topics>
  <topic number="7" type="diagnosis">
    <description>Patient with fever and pancytopenia after chemotherapy.</description>
    <summary>Find evidence for infectious complications.</summary>
  </topic>
</topics>
""",
        encoding="utf-8",
    )

    topics = parse_topics(topics_path, track="clinical_decision_support")

    assert topics[0].track == "clinical_decision_support"
    assert topics[0].topic_id == "7"
    assert "fever and pancytopenia" in topics[0].query
    assert "infectious complications" in topics[0].query


def test_score_payload_uses_judged_positives_and_leaves_unjudged_unknown() -> None:
    row = {
        "id": "trec_precision_medicine_1_document_source",
        "benchmark_type": "document_source_retrieval",
        "track": "precision_medicine",
        "topic_id": "1",
        "query": "EGFR lung cancer",
        "expected_doc_ids": "PMID:12345|NCT:NCT00000001",
    }
    payload = {
        "backend": "elasticsearch",
        "elapsed_ms": 15,
        "hits": [
            {
                "cui": "C0000001",
                "name": "Wrong concept",
                "evidence_items": [{"metadata": {"pmid": "77777"}}],
            },
            {
                "cui": "C0684249",
                "name": "Non-Small Cell Lung Carcinoma",
                "evidence_items": [{"metadata": {"pmid": "12345"}}],
            },
            {
                "cui": "C1515886",
                "name": "Clinical Trial",
                "source_doc_id": "NCT00000001",
            },
        ],
    }

    scored = score_payload(row, payload, elapsed_seconds=0.02, top_k=10)

    assert scored["found_at_1"] == "0"
    assert scored["found_at_3"] == "2"
    assert scored["recall_at_10"] == "1.000000"
    assert scored["first_expected_rank"] == "2"
    assert scored["found_doc_id_ranks"] == "PMID:12345:2|NCT:NCT00000001:3"
    assert scored["unscored_doc_ids_seen"] == "PMID:77777"


def test_result_summary_reports_document_source_types_separately() -> None:
    rows = [
        {
            "track": "precision_medicine",
            "expected_doc_ids": "PMID:12345|NCT:NCT00000001",
            "found_at_1": "0",
            "found_at_3": "2",
            "found_at_5": "2",
            "found_at_10": "2",
            "found_at_k": "2",
            "recall_at_10": "1.000000",
            "recall_at_k": "1.000000",
            "reciprocal_first_expected_rank": "0.500000",
            "elapsed_ms": "20.0",
            "found_doc_id_ranks": "PMID:12345:2|NCT:NCT00000001:3",
        },
        {
            "track": "precision_medicine",
            "expected_doc_ids": "PMID:99999",
            "found_at_1": "0",
            "found_at_3": "0",
            "found_at_5": "0",
            "found_at_10": "0",
            "found_at_k": "0",
            "recall_at_10": "0.000000",
            "recall_at_k": "0.000000",
            "reciprocal_first_expected_rank": "0.000000",
            "elapsed_ms": "10.0",
            "found_doc_id_ranks": "",
        },
    ]

    summary = summarize_results(rows, top_k=10)

    assert summary["document_source_retrieval"] is True
    assert summary["unjudged_policy"] == "unknown_not_false_positive"
    assert summary["by_source_type"]["pubmed"]["expected_documents"] == 2
    assert summary["by_source_type"]["pubmed"]["found_documents_at_10"] == 1
    assert summary["by_source_type"]["pubmed"]["document_recall_at_10"] == 0.5
    assert summary["by_source_type"]["clinicaltrials_gov"]["document_recall_at_10"] == 1.0
