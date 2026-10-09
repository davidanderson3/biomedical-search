from __future__ import annotations

import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_real_queries_umls_api.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("audit_real_queries_umls_api", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def query_row(module, term: str, users: int, source_row: int, privacy_flags=()):
    normalized = term.lower()
    return module.QueryRow(
        source_file="queries.csv",
        source_row=source_row,
        token_bucket="test",
        search_term=term,
        unique_users=users,
        normalized_term=normalized,
        normalized_token_count=len(normalized.split()),
        privacy_flags=privacy_flags,
    )


def audit_query(module, term: str, users: int):
    return module.AuditQuery(
        query_id=f"q_{term}",
        search_term=term,
        normalized_term=term,
        normalized_token_count=len(term.split()),
        sum_unique_users=users,
        source_rows=("queries.csv:2",),
        privacy_flags=(),
    )


def test_collapse_queries_aggregates_normalized_duplicates():
    module = load_script_module()
    rows = [
        query_row(module, "Heart Attack", 4, 2),
        query_row(module, "heart attack", 3, 3),
        query_row(module, "private@example.com", 1, 4, ("email_like",)),
    ]

    collapsed = module.collapse_queries(rows)

    heart_attack = next(row for row in collapsed if row.normalized_term == "heart attack")
    assert heart_attack.sum_unique_users == 7
    assert heart_attack.source_rows == ("queries.csv:2", "queries.csv:3")
    private = next(row for row in collapsed if row.normalized_term == "private@example.com")
    assert private.privacy_flags == ("email_like",)


def test_default_eligibility_excludes_privacy_and_long_queries():
    module = load_script_module()
    rows = [
        audit_query(module, "one", 5),
        audit_query(module, "one two three four five", 2),
        module.AuditQuery(
            query_id="private",
            search_term="private term",
            normalized_term="private term",
            normalized_token_count=2,
            sum_unique_users=1,
            source_rows=("queries.csv:3",),
            privacy_flags=("email_like",),
        ),
    ]

    eligible = module.eligible_queries(
        rows,
        min_tokens=1,
        max_tokens=4,
        include_privacy_flagged=False,
    )

    assert [row.normalized_term for row in eligible] == ["one"]


def test_sampling_is_reproducible_and_methods_are_distinct():
    module = load_script_module()
    rows = [audit_query(module, f"query {index}", 100 if index == 0 else 1) for index in range(20)]

    uniform_a = module.select_sample(rows, size=5, method="uniform", seed=17)
    uniform_b = module.select_sample(rows, size=5, method="uniform", seed=17)
    demand = module.select_sample(rows, size=5, method="demand", seed=17)

    assert uniform_a == uniform_b
    assert demand != uniform_a
    assert rows[0] in demand


def test_result_row_and_summary_count_no_hits_and_errors():
    module = load_script_module()
    hit_query = audit_query(module, "heart attack", 8)
    miss_query = audit_query(module, "lay phrase", 3)
    error_query = audit_query(module, "error phrase", 2)
    hit = module.result_row(
        hit_query,
        {"result": {"results": [{"ui": "C0027051", "name": "Myocardial Infarction", "rootSource": "MTH"}]}},
        "",
        search_type="words",
    )
    miss = module.result_row(
        miss_query,
        {"result": {"results": []}},
        "",
        search_type="words",
    )
    error = module.result_row(error_query, None, "HTTP 500", search_type="words")
    args = Namespace(
        umls_base_url="https://example.test",
        search_type="words",
        sabs="",
        sampling="uniform",
        seed=17,
        sample_size=3,
        min_tokens=1,
        max_tokens=4,
        include_privacy_flagged=False,
    )

    summary = module.summarize(
        [hit, miss, error],
        all_queries=[hit_query, miss_query, error_query],
        eligible=[hit_query, miss_query, error_query],
        sample=[hit_query, miss_query, error_query],
        args=args,
        run_id="test",
    )

    assert summary["scored_queries"] == 2
    assert summary["api_error_queries"] == 1
    assert summary["umls_no_hit_queries"] == 1
    assert summary["umls_no_hit_query_rate"] == 0.5
    assert summary["umls_no_hit_demand_rate"] == round(3 / 11, 6)


def test_resolve_api_key_prefers_environment(monkeypatch):
    module = load_script_module()
    monkeypatch.setenv("UMLS_API_KEY", "secret-from-env")
    monkeypatch.setattr(module.getpass, "getpass", lambda prompt: (_ for _ in ()).throw(AssertionError(prompt)))

    assert module.resolve_api_key() == "secret-from-env"


def test_score_reviewed_rows_calculates_expected_result_false_negative_rate():
    module = load_script_module()
    rows = [
        {
            "review_status": "include",
            "expected_cuis": "C0000001|C0000002",
            "failure_class": "synonym",
            "sum_unique_users": "5",
            "umls_hit_cuis": "C0000001|C9999999",
            "umls_hits": "",
        },
        {
            "review_status": "approved",
            "expected_cuis": "C0000003",
            "failure_class": "abbreviation",
            "sum_unique_users": "3",
            "umls_hit_cuis": "C9999998",
            "umls_hits": "",
        },
        {
            "review_status": "exclude",
            "expected_cuis": "C0000004",
            "failure_class": "noise",
            "sum_unique_users": "100",
            "umls_hit_cuis": "",
            "umls_hits": "",
        },
    ]

    scored, summary = module.score_reviewed_rows(rows)

    assert len(scored) == 2
    assert summary["expected_query_cui_results"] == 3
    assert summary["returned_expected_query_cui_results"] == 1
    assert summary["missed_expected_query_cui_results"] == 2
    assert summary["missed_expected_result_percentage"] == 66.67
    assert summary["queries_with_any_expected_result_missed"] == 2
    assert summary["queries_with_any_expected_result_missed_percentage"] == 100.0
    assert summary["queries_with_partial_expected_results"] == 1
    assert summary["query_partial_miss_percentage"] == 50.0
    assert summary["queries_with_complete_expected_result_coverage"] == 0
    assert summary["queries_with_all_expected_results_missed"] == 1
    assert summary["query_total_miss_percentage"] == 50.0
    assert summary["demand_weighted_query_total_miss_percentage"] == 37.5


def test_review_queue_includes_api_hits_and_no_hits_but_not_errors(tmp_path):
    module = load_script_module()
    path = tmp_path / "expected_result_review_queue.tsv"
    base = {
        "id": "q1",
        "search_term": "term",
        "normalized_term": "term",
        "normalized_token_count": 1,
        "sum_unique_users": 1,
        "source_rows": "queries.csv:2",
        "privacy_flags": "",
        "search_type": "words",
        "umls_top_cui": "",
        "umls_top_name": "",
        "umls_top_source": "",
        "umls_hit_cuis": "",
        "umls_hits": "",
    }
    hit = {**base, "id": "hit", "umls_hit_count": 1, "umls_no_hit": "0", "umls_error": ""}
    no_hit = {**base, "id": "no_hit", "umls_hit_count": 0, "umls_no_hit": "1", "umls_error": ""}
    error = {
        **base,
        "id": "error",
        "umls_hit_count": 0,
        "umls_no_hit": "",
        "umls_error": "HTTP 500",
    }

    module.write_review_queue(path, [hit, no_hit, error])
    rows = module.read_review_rows(path)

    assert [row["id"] for row in rows] == ["no_hit", "hit"]


def test_html_report_marks_unreviewed_results_as_preliminary_and_escapes_queries(tmp_path):
    module = load_script_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    summary = {
        "run_id": "test-run",
        "sampled_queries": 2,
        "scored_queries": 1,
        "api_error_queries": 1,
        "umls_no_hit_queries": 1,
        "umls_no_hit_query_rate": 1.0,
        "umls_no_hit_demand_rate": 1.0,
        "scored_sum_unique_users": 3,
        "eligible_queries": 100,
        "random_seed": 17,
        "results_by_normalized_token_count": {
            "2": {
                "scored_queries": 1,
                "no_hit_queries": 1,
                "no_hit_query_rate": 1.0,
                "no_hit_demand_rate": 1.0,
            }
        },
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    row = {
        field: "" for field in module.ROW_FIELDS
    }
    row.update(
        {
            "id": "q1",
            "search_term": "<unsafe query>",
            "normalized_term": "unsafe query",
            "normalized_token_count": 2,
            "sum_unique_users": 3,
            "umls_hit_count": 0,
            "umls_no_hit": "1",
        }
    )
    module.write_tsv(run_dir / "rows.tsv", [row], module.ROW_FIELDS)
    module.write_review_queue(run_dir / "expected_result_review_queue.tsv", [row])

    output = module.write_html_report(run_dir)
    document = output.read_text(encoding="utf-8")

    assert "Preliminary — adjudication pending" in document
    assert "100.0%" in document
    assert "&lt;unsafe query&gt;" in document
    assert "<unsafe query>" not in document
