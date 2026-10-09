from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_umls_vector_search.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("compare_umls_vector_search", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_outputs_creates_blinded_union_pool():
    module = load_script_module()
    base = {
        "id": "q1",
        "search_term": "lay phrase",
        "normalized_token_count": "2",
        "sum_unique_users": "5",
        "umls_error": "",
        "umls_hit_cuis": "C0000001|C0000002",
        "umls_hits": "1:C0000001 First label | 2:C0000002 Second label",
    }
    payload = {
        "backend": "elasticsearch",
        "elapsed_ms": 12.5,
        "hits": [
            {"cui": "C0000002", "name": "Second label", "score": 0.9},
            {"cui": "C0000003", "name": "Third label", "score": 0.8},
        ],
    }

    comparisons, provenance, judgments, query_review = module.build_outputs(
        [base], {"q1": (payload, "")}, top_k=10, seed=17
    )

    assert comparisons[0]["overlap_count_at_k"] == 1
    assert comparisons[0]["vector_only_count_at_k"] == 1
    assert len(provenance) == 3
    assert len(judgments) == 3
    assert set(judgments[0]) == set(module.JUDGMENT_FIELDS)
    assert "in_umls" not in judgments[0]
    assert "in_vector" not in judgments[0]
    assert len(query_review) == 1


def test_score_reviewed_pool_computes_paired_recall(tmp_path):
    module = load_script_module()
    judgments_path = tmp_path / "judgments.tsv"
    provenance_path = tmp_path / "provenance.tsv"
    query_review_path = tmp_path / "queries.tsv"
    module.write_tsv(
        judgments_path,
        [
            {"relevance_grade": "2", "review_note": "", "pool_id": "p1", "id": "q1", "search_term": "term", "cui": "C0000001", "label": "One"},
            {"relevance_grade": "0", "review_note": "", "pool_id": "p2", "id": "q1", "search_term": "term", "cui": "C0000002", "label": "Two"},
            {"relevance_grade": "2", "review_note": "", "pool_id": "p3", "id": "q1", "search_term": "term", "cui": "C0000003", "label": "Three"},
        ],
        module.JUDGMENT_FIELDS,
    )
    module.write_tsv(
        provenance_path,
        [
            {"id": "q1", "search_term": "term", "cui": "C0000001", "label": "One", "in_umls": "1", "umls_rank": "1", "in_vector": "0", "vector_rank": "", "vector_score": ""},
            {"id": "q1", "search_term": "term", "cui": "C0000002", "label": "Two", "in_umls": "1", "umls_rank": "2", "in_vector": "1", "vector_rank": "1", "vector_score": "0.9"},
            {"id": "q1", "search_term": "term", "cui": "C0000003", "label": "Three", "in_umls": "0", "umls_rank": "", "in_vector": "1", "vector_rank": "2", "vector_score": "0.8"},
        ],
        module.PROVENANCE_FIELDS,
    )
    module.write_tsv(
        query_review_path,
        [{"query_status": "include", "intended_concept_note": "", "id": "q1", "search_term": "term", "normalized_token_count": "1", "sum_unique_users": "5"}],
        module.QUERY_REVIEW_FIELDS,
    )

    query_stats, summary = module.score_reviewed_pool(
        judgments_path=judgments_path,
        provenance_path=provenance_path,
        query_review_path=query_review_path,
    )

    assert len(query_stats) == 1
    assert summary["umls_micro_recall_in_judged_pool"] == 0.5
    assert summary["vector_micro_recall_in_judged_pool"] == 0.5
    assert summary["umls_missed_relevant_result_percentage"] == 50.0
    assert summary["vector_missed_relevant_result_percentage"] == 50.0


def test_preserve_review_columns_keeps_existing_judgments(tmp_path):
    module = load_script_module()
    path = tmp_path / "judgments.tsv"
    module.write_tsv(
        path,
        [
            {
                "relevance_grade": "2",
                "review_note": "confirmed",
                "pool_id": "p1",
                "id": "q1",
                "search_term": "term",
                "cui": "C0000001",
                "label": "One",
            }
        ],
        module.JUDGMENT_FIELDS,
    )

    merged = module.preserve_review_columns(
        path,
        [{"pool_id": "p1", "relevance_grade": "", "review_note": "", "label": "Updated"}],
        key="pool_id",
        fields=("relevance_grade", "review_note"),
    )

    assert merged[0]["relevance_grade"] == "2"
    assert merged[0]["review_note"] == "confirmed"
    assert merged[0]["label"] == "Updated"


def test_select_pilot_is_reproducible_and_query_complete():
    module = load_script_module()
    comparisons = [
        {"id": f"q{index}", "umls_complete": "1", "vector_complete": "1"}
        for index in range(10)
    ]
    judgments = [
        {"id": f"q{index}", "pool_id": f"p{index}_{cui}"}
        for index in range(10)
        for cui in range(3)
    ]
    queries = [{"id": f"q{index}"} for index in range(10)]

    judgments_a, queries_a, ids_a = module.select_pilot(
        comparisons, judgments, queries, size=4, seed=17
    )
    judgments_b, queries_b, ids_b = module.select_pilot(
        comparisons, judgments, queries, size=4, seed=17
    )

    assert ids_a == ids_b
    assert judgments_a == judgments_b
    assert queries_a == queries_b
    assert len(ids_a) == 4
    assert len(judgments_a) == 12
