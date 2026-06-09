from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_real_query_inventory.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("build_real_query_inventory", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_real_query_inventory_flags_and_writes_tsv(tmp_path):
    module = load_script_module()
    input_dir = tmp_path / "exports"
    input_dir.mkdir()
    (input_dir / "one-word-real-queries.csv").write_text(
        "\n".join(
            [
                "search_term,unique_users",
                "hypertension,7",
                "user@example.com,1",
                "555-123-4567,1",
                "abc123456,1",
                "cafe\u0301,2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rows = list(module.iter_query_rows(input_dir))
    assert len(rows) == 5
    assert rows[0].normalized_term == "hypertension"
    assert rows[0].normalized_token_count == 1

    flags_by_term = {row.search_term: set(row.privacy_flags) for row in rows}
    assert flags_by_term["user@example.com"] == {"email_like"}
    assert flags_by_term["555-123-4567"] == {"phone_like"}
    assert flags_by_term["abc123456"] == {"long_digit_run"}
    assert flags_by_term["cafe\u0301"] == {"non_ascii"}

    summary = module.summarize(rows)
    assert summary["rows"] == 5
    assert summary["sum_unique_users"] == 12
    assert summary["privacy_flags"]["email_like"] == 1

    out = tmp_path / "query_inventory.tsv"
    module.write_inventory(rows, out)
    with out.open("r", encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle, delimiter="\t"))
    assert written[0]["search_term"] == "hypertension"
    assert written[1]["privacy_flags"] == "email_like"


def test_search_result_from_response_uses_top_rank_score():
    module = load_script_module()

    result = module.search_result_from_response(
        {
            "hits": [
                {"cui": "C0004238", "name": "Atrial Fibrillation", "rank_score": "0.8123"},
                {"cui": "C1111111", "name": "Other"},
            ]
        }
    )

    assert result.hit_count == 2
    assert result.top_cui == "C0004238"
    assert result.top_label == "Atrial Fibrillation"
    assert result.score == 0.8123


def test_scored_inventory_distinguishes_no_hit_from_unscored(tmp_path):
    module = load_script_module()
    rows = [
        module.QueryRow(
            source_file="one-word-real-queries.csv",
            source_row=2,
            token_bucket="one",
            search_term="unmatched term",
            unique_users=3,
            normalized_term="unmatched term",
            normalized_token_count=2,
            privacy_flags=(),
        ),
        module.QueryRow(
            source_file="one-word-real-queries.csv",
            source_row=3,
            token_bucket="one",
            search_term="unscored",
            unique_users=2,
            normalized_term="unscored",
            normalized_token_count=1,
            privacy_flags=(),
        ),
    ]
    server_results = {module.row_key(rows[0]): module.SearchResult(hit_count=0)}

    out = tmp_path / "query_inventory.tsv"
    module.write_inventory(rows, out, server_results)

    with out.open("r", encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle, delimiter="\t"))
    assert written[0]["server_hit_count"] == "0"
    assert written[1]["server_hit_count"] == ""


def test_review_queue_prioritizes_server_failures_and_privacy_flags(tmp_path):
    module = load_script_module()
    rows = [
        module.QueryRow(
            source_file="one-word-real-queries.csv",
            source_row=2,
            token_bucket="one",
            search_term="common term",
            unique_users=20,
            normalized_term="common term",
            normalized_token_count=2,
            privacy_flags=(),
        ),
        module.QueryRow(
            source_file="two-word-real-queries.csv",
            source_row=2,
            token_bucket="two",
            search_term="missed term",
            unique_users=4,
            normalized_term="missed term",
            normalized_token_count=2,
            privacy_flags=(),
        ),
        module.QueryRow(
            source_file="three-word-real-queries.csv",
            source_row=2,
            token_bucket="three",
            search_term="person@example.com",
            unique_users=1,
            normalized_term="person example com",
            normalized_token_count=3,
            privacy_flags=("email_like",),
        ),
    ]
    server_results = {
        module.row_key(rows[0]): module.SearchResult(hit_count=2, top_cui="C1", score=0.9),
        module.row_key(rows[1]): module.SearchResult(hit_count=0),
        module.row_key(rows[2]): module.SearchResult(error="http_400"),
    }

    queue = module.review_queue_rows(
        rows,
        server_results,
        limit=3,
        low_score_threshold=0.35,
        high_demand_min=5,
    )

    assert queue[0]["search_term"] == "person@example.com"
    assert "privacy:email_like" in queue[0]["review_reasons"]
    assert queue[1]["search_term"] == "missed term"
    assert "no_server_hit" in queue[1]["review_reasons"]
    assert queue[2]["search_term"] == "common term"
    assert queue[2]["review_reasons"] == "high_demand"
