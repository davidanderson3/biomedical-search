from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_private_real_query_diagnostic.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_private_real_query_diagnostic", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def query_row(module, term="missed hypertension", users=6):
    return module.QueryRow(
        source_file="two-word-real-queries.csv",
        source_row=2,
        token_bucket="two",
        search_term=term,
        unique_users=users,
        normalized_term=term,
        normalized_token_count=len(term.split()),
        privacy_flags=(),
    )


def test_evaluate_payloads_flags_low_score_and_umls_top_missing():
    module = load_script_module()
    row = query_row(module)

    result = module.evaluate_payloads(
        row,
        local_payload={
            "hits": [
                {"cui": "C0000001", "name": "Local Result", "rank_score": 0.2},
                {"cui": "C0000002", "name": "Other Result", "rank_score": 0.1},
            ]
        },
        umls_payload={
            "result": {
                "results": [
                    {"ui": "C0020538", "name": "Hypertensive disease", "rootSource": "MTH"}
                ]
            }
        },
        local_error="",
        umls_error="",
        low_score_threshold=0.35,
        compare_top_n=10,
        show_hits=3,
        high_demand_min=5,
    )

    assert result["local_low_score"] == "1"
    assert result["umls_top_cui"] == "C0020538"
    assert result["umls_top_in_local_rank"] == ""
    assert "local_low_score" in result["review_reasons"]
    assert "umls_top_missing_locally" in result["review_reasons"]
    assert "top_disagreement" in result["review_reasons"]
    assert result["recommended_action"] == "review_for_possible_promotion"


def test_review_queue_orders_privacy_before_local_no_hit():
    module = load_script_module()
    privacy_row = module.evaluate_payloads(
        module.QueryRow(
            source_file="one-word-real-queries.csv",
            source_row=2,
            token_bucket="one",
            search_term="person@example.com",
            unique_users=1,
            normalized_term="person example com",
            normalized_token_count=3,
            privacy_flags=("email_like",),
        ),
        local_payload={"hits": []},
        umls_payload={"result": {"results": []}},
        local_error="",
        umls_error="",
        low_score_threshold=0.35,
        compare_top_n=10,
        show_hits=3,
        high_demand_min=5,
    )
    no_hit_row = module.evaluate_payloads(
        query_row(module, term="rare condition", users=50),
        local_payload={"hits": []},
        umls_payload={
            "result": {
                "results": [{"ui": "C1234567", "name": "Rare condition", "rootSource": "MTH"}]
            }
        },
        local_error="",
        umls_error="",
        low_score_threshold=0.35,
        compare_top_n=10,
        show_hits=3,
        high_demand_min=5,
    )

    queue = module.review_queue_rows([no_hit_row, privacy_row], limit=2)

    assert queue[0]["search_term"] == "person@example.com"
    assert queue[0]["recommended_action"] == "privacy_review_do_not_promote"
    assert queue[1]["search_term"] == "rare condition"


def test_review_queue_skips_high_demand_only_rows():
    module = load_script_module()
    healthy = module.evaluate_payloads(
        query_row(module, term="hypertension", users=50),
        local_payload={"hits": [{"cui": "C0020538", "name": "Hypertensive disease", "rank_score": 0.9}]},
        umls_payload={
            "result": {
                "results": [{"ui": "C0020538", "name": "Hypertensive disease", "rootSource": "MTH"}]
            }
        },
        local_error="",
        umls_error="",
        low_score_threshold=0.35,
        compare_top_n=10,
        show_hits=3,
        high_demand_min=5,
    )

    assert healthy["review_reasons"] == "high_demand"
    assert module.review_queue_rows([healthy], limit=10) == []


def test_promotion_candidates_skip_privacy_and_prefill_umls_top():
    module = load_script_module()
    safe = module.evaluate_payloads(
        query_row(module, term="hypertension", users=10),
        local_payload={"hits": [{"cui": "C0000001", "name": "Wrong", "rank_score": 0.9}]},
        umls_payload={
            "result": {
                "results": [{"ui": "C0020538", "name": "Hypertensive disease", "rootSource": "MTH"}]
            }
        },
        local_error="",
        umls_error="",
        low_score_threshold=0.35,
        compare_top_n=10,
        show_hits=3,
        high_demand_min=5,
    )
    private = dict(safe)
    private["id"] = "private"
    private["privacy_flags"] = "email_like"

    candidates = module.promotion_candidate_rows([private, safe], limit=10)

    assert len(candidates) == 1
    assert candidates[0]["query"] == "hypertension"
    assert candidates[0]["expected_cuis"] == "C0020538"
    assert candidates[0]["review_status"] == ""


def test_ensure_regression_template_writes_header(tmp_path):
    module = load_script_module()
    out = tmp_path / "real_query_regression.tsv"

    module.ensure_regression_template(out)

    with out.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t"))
    assert rows == [["id", "query", "expected_cuis", "why", "source"]]


def test_select_rows_for_run_skips_seen_ids_and_updates_state(tmp_path):
    module = load_script_module()
    rows = [
        query_row(module, term="alpha", users=3),
        query_row(module, term="beta", users=2),
        query_row(module, term="gamma", users=1),
    ]
    rows[0] = module.QueryRow(**{**rows[0].__dict__, "source_row": 2})
    rows[1] = module.QueryRow(**{**rows[1].__dict__, "source_row": 3})
    rows[2] = module.QueryRow(**{**rows[2].__dict__, "source_row": 4})
    seen_state = tmp_path / "seen.json"
    seen_state.write_text(
        '{"version":1,"seen_query_ids":["two-word_row_2"],"runs":[]}\n',
        encoding="utf-8",
    )

    selected, state = module.select_rows_for_run(
        rows,
        limit=2,
        sort_mode="demand",
        selection="unseen",
        seen_state_path=seen_state,
        reset_seen_state=False,
    )

    assert [module.query_id(row) for row in selected] == ["two-word_row_3", "two-word_row_4"]
    assert state["selected_new_queries"] == 2
    assert state["selected_recycled_queries"] == 0

    module.write_seen_state(seen_state, state, run_id="test_run")
    updated = module.read_seen_state(seen_state)
    assert set(updated["seen_query_ids"]) == {
        "two-word_row_2",
        "two-word_row_3",
        "two-word_row_4",
    }


def test_select_rows_for_run_recycles_after_unseen_pool_is_empty(tmp_path):
    module = load_script_module()
    rows = [
        query_row(module, term="alpha", users=3),
        query_row(module, term="beta", users=2),
    ]
    rows[0] = module.QueryRow(**{**rows[0].__dict__, "source_row": 2})
    rows[1] = module.QueryRow(**{**rows[1].__dict__, "source_row": 3})
    seen_state = tmp_path / "seen.json"
    seen_state.write_text(
        '{"version":1,"seen_query_ids":["two-word_row_2"],"runs":[]}\n',
        encoding="utf-8",
    )

    selected, state = module.select_rows_for_run(
        rows,
        limit=2,
        sort_mode="demand",
        selection="unseen",
        seen_state_path=seen_state,
        reset_seen_state=False,
    )

    assert [module.query_id(row) for row in selected] == ["two-word_row_3", "two-word_row_2"]
    assert state["selected_new_queries"] == 1
    assert state["selected_recycled_queries"] == 1
