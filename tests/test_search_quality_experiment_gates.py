from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_search_quality_experiment.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_search_quality_experiment", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def gate_args(**overrides):
    values = {
        "strict_success_at_10_tolerance": 0.006,
        "known_false_positive_at_10_tolerance": 0.0,
        "source_count_collapse_tolerance": 0.25,
        "source_count_collapse_min_baseline": 10,
        "restricted_source_pattern": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_payloads(path: Path, payloads: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(payload, sort_keys=True) + "\n" for payload in payloads),
        encoding="utf-8",
    )


def test_fail_gates_detect_metric_regressions_and_source_collapse(tmp_path: Path) -> None:
    module = load_script_module()
    payloads_path = tmp_path / "run" / "payloads.jsonl"
    write_payloads(
        payloads_path,
        [
            {
                "id": "q1",
                "query": "metformin diabetes",
                "response": {
                    "hits": [
                        {
                            "cui": "C0025598",
                            "name": "Metformin",
                            "sources": ["dailymed"],
                        }
                    ]
                },
            }
        ],
    )
    run = {
        "run_id": "current",
        "label": "Current",
        "search_system": module.SEARCH_SYSTEM_API,
        "api_scope": module.SEARCH_SCOPE_UMLS_EVIDENCE,
        "payloads_path": str(payloads_path),
        "summary": {
            "strict_success_at_10_rate": 0.90,
            "known_false_positive_rate_at_10": 0.01,
            "queries_with_disallowed_at_10": 1,
            "source_counts_at_10": {"dailymed": 5, "pubmed": 20},
        },
    }
    baseline = {
        "run_id": "baseline",
        "label": "Baseline",
        "summary": {
            "strict_success_at_10_rate": 1.0,
            "known_false_positive_rate_at_10": 0.0,
            "queries_with_disallowed_at_10": 0,
            "source_counts_at_10": {"dailymed": 12, "pubmed": 20},
        },
    }

    result = module.evaluate_run_gates(run, baseline, gate_args())

    assert result["passed"] is False
    failed = {check["name"] for check in result["checks"] if check["passed"] is False}
    assert failed == {
        "strict_success_at_10_no_drop",
        "known_false_positive_at_10_no_increase",
        "source_count_no_unexpected_collapse",
    }


def test_fail_gates_skip_metric_baseline_when_evaluation_signature_differs(tmp_path: Path) -> None:
    module = load_script_module()
    payloads_path = tmp_path / "run" / "payloads.jsonl"
    write_payloads(payloads_path, [])
    run = {
        "run_id": "current",
        "label": "Current",
        "search_system": module.SEARCH_SYSTEM_API,
        "api_scope": module.SEARCH_SCOPE_UMLS_EVIDENCE,
        "evaluation_signature": "current-signature",
        "payloads_path": str(payloads_path),
        "summary": {
            "strict_success_at_10_rate": 0.50,
            "known_false_positive_rate_at_10": 0.0,
            "source_counts_at_10": {"pubmed": 1},
        },
    }
    baseline = {
        "run_id": "baseline",
        "label": "Baseline",
        "evaluation_signature": "baseline-signature",
        "summary": {
            "strict_success_at_10_rate": 1.0,
            "known_false_positive_rate_at_10": 0.0,
            "source_counts_at_10": {"pubmed": 100},
        },
    }

    result = module.evaluate_run_gates(run, baseline, gate_args())

    assert result["passed"] is True
    checks = {check["name"]: check for check in result["checks"]}
    assert checks["evaluation_definition_matches_baseline"]["status"] == "skipped"
    assert checks["strict_success_at_10_no_drop"]["status"] == "skipped"
    assert checks["source_count_no_unexpected_collapse"]["status"] == "skipped"


def test_fail_gates_detect_protocol_only_clinicaltrials_and_restricted_source(tmp_path: Path) -> None:
    module = load_script_module()
    payloads_path = tmp_path / "run" / "payloads.jsonl"
    write_payloads(
        payloads_path,
        [
            {
                "id": "q1",
                "query": "trial evidence",
                "response": {
                    "hits": [
                        {
                            "cui": "C0011860",
                            "name": "Diabetes Mellitus Type 2",
                            "sources": ["clinicaltrials_gov"],
                            "evidence": [
                                {
                                    "source": "clinicaltrials_gov",
                                    "text": "ClinicalTrials.gov eligibility criteria and primary outcome measure from protocol text.",
                                }
                            ],
                        },
                        {
                            "cui": "C9999999",
                            "name": "Restricted label",
                            "sources": ["restricted_private"],
                        },
                    ]
                },
            }
        ],
    )
    run = {
        "run_id": "current",
        "label": "Current",
        "search_system": module.SEARCH_SYSTEM_API,
        "api_scope": module.SEARCH_SCOPE_UMLS_EVIDENCE,
        "payloads_path": str(payloads_path),
        "summary": {"source_counts_at_10": {}},
    }

    result = module.evaluate_run_gates(run, None, gate_args())

    assert result["passed"] is False
    failed = {check["name"] for check in result["checks"] if check["passed"] is False}
    assert "clinicaltrials_no_protocol_only_evidence" in failed
    assert "public_display_no_restricted_or_non_level_0_content" in failed


def test_source_counts_from_payloads_collects_top_ten_unique_sources() -> None:
    module = load_script_module()
    payloads = [
        {
            "response": {
                "hits": [
                    {"sources": ["PubMed", "pubmed"], "source_mix": {"items": [{"source": "DailyMed"}]}},
                    {"sources": ["MedlinePlus"]},
                    {"sources": ["ignored"]},
                ]
            }
        }
    ]

    counts = module.source_counts_from_payloads(payloads, limit=2)

    assert counts == {"dailymed": 1, "medlineplus": 1, "pubmed": 1}


def test_rotating_query_sample_limits_and_records_selection() -> None:
    module = load_script_module()
    specs = [
        module.QuerySpec(query_id=f"q{index}", query=f"query {index}", expected_cuis=[f"C{index}"])
        for index in range(1, 12)
    ]
    args = argparse.Namespace(query_limit=5, query_selection="rotate", query_rotation_seed="seed-a")

    selected, metadata = module.select_query_specs_for_run(specs, args, run_id="run-a", label="Run A")
    selected_again, metadata_again = module.select_query_specs_for_run(specs, args, run_id="run-a", label="Run A")

    assert [spec.query_id for spec in selected] == [spec.query_id for spec in selected_again]
    assert metadata == metadata_again
    assert metadata["query_pool_count"] == 11
    assert metadata["query_selected_count"] == 5
    assert metadata["query_selection"] == "rotate"
    assert metadata["query_selection_ids"] == [spec.query_id for spec in selected]

    alternate_ids = None
    for seed in ("seed-b", "seed-c", "seed-d", "seed-e"):
        alternate_args = argparse.Namespace(query_limit=5, query_selection="rotate", query_rotation_seed=seed)
        alternate, _alternate_metadata = module.select_query_specs_for_run(
            specs,
            alternate_args,
            run_id="run-b",
            label="Run B",
        )
        alternate_ids = [spec.query_id for spec in alternate]
        if alternate_ids != metadata["query_selection_ids"]:
            break

    assert alternate_ids != metadata["query_selection_ids"]


def test_query_limit_zero_uses_full_query_pool() -> None:
    module = load_script_module()
    specs = [
        module.QuerySpec(query_id=f"q{index}", query=f"query {index}", expected_cuis=[f"C{index}"])
        for index in range(1, 6)
    ]
    args = argparse.Namespace(query_limit=0, query_selection="rotate", query_rotation_seed="seed-a")

    selected, metadata = module.select_query_specs_for_run(specs, args, run_id="run-a", label="Run A")

    assert [spec.query_id for spec in selected] == [spec.query_id for spec in specs]
    assert metadata["query_selection"] == "all"
    assert metadata["query_selected_count"] == 5


def test_api_response_requires_elasticsearch_backend_by_default(monkeypatch) -> None:
    module = load_script_module()

    def fake_get_json(base_url, path, params, *, timeout):
        return {"backend": "local", "hits": []}

    monkeypatch.setattr(module, "get_json", fake_get_json)
    args = argparse.Namespace(
        base_url="http://127.0.0.1:8766",
        top_k=10,
        include_related=False,
        include_linked_concepts=False,
        include_search_evidence_items=False,
        mode="balanced",
        scope=module.SEARCH_SCOPE_UMLS_EVIDENCE,
        timeout=1.0,
        require_api_backend="elasticsearch",
    )
    spec = module.QuerySpec(query_id="q1", query="heart failure", expected_cuis=[], disallowed_cuis=[])

    try:
        module.search_api_response(args, spec)
    except SystemExit as exc:
        assert "did not match required backend 'elasticsearch'" in str(exc)
    else:
        raise AssertionError("expected backend mismatch to stop the experiment")


def test_source_quality_contribution_tracks_expected_and_bad_hits() -> None:
    module = load_script_module()
    rows = [
        {
            "id": "q1",
            "query": "accepted alternative",
            "verdict": "good",
            "expected_cuis": "C1",
            "acceptable_cuis": "C1|C1A",
            "top_on_target": "1",
            "missing_at_10": "",
            "disallowed_at_10": "",
        },
        {
            "id": "q2",
            "query": "known false positive",
            "verdict": "mixed",
            "expected_cuis": "C2",
            "acceptable_cuis": "C2",
            "top_on_target": "0",
            "missing_at_10": "",
            "disallowed_at_10": "C9",
        },
    ]
    payloads = [
        {
            "id": "q1",
            "query": "accepted alternative",
            "response": {
                "hits": [
                    {"cui": "C1A", "name": "Accepted alternative", "sources": ["PubMed"]},
                    {"cui": "C3", "name": "Context hit", "sources": ["DailyMed"]},
                ]
            },
        },
        {
            "id": "q2",
            "query": "known false positive",
            "response": {
                "hits": [
                    {"cui": "C9", "name": "Known false positive", "sources": ["DailyMed"]},
                    {"cui": "C2", "name": "Expected concept", "sources": ["PubMed"]},
                ]
            },
        },
    ]

    contribution = module.source_quality_contribution(payloads, rows, limit=10)
    sources = contribution["sources"]

    assert contribution["ranked_sources"][0]["source"] == "pubmed"
    assert sources["pubmed"]["expected_queries_at_10"] == 2
    assert sources["pubmed"]["strict_success_expected_queries_at_10"] == 1
    assert sources["pubmed"]["failed_expected_queries_at_10"] == 1
    assert sources["pubmed"]["top1_strict_success_expected_queries"] == 1
    assert sources["pubmed"]["mean_best_expected_rank_at_10"] == 1.5
    assert sources["dailymed"]["queries_present_at_10"] == 2
    assert sources["dailymed"]["strict_success_queries_present_at_10"] == 1
    assert sources["dailymed"]["expected_queries_at_10"] == 0
    assert sources["dailymed"]["disallowed_queries_at_10"] == 1
    assert sources["dailymed"]["disallowed_hit_source_appearances_at_10"] == 1
