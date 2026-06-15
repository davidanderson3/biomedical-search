from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import sys
import time
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


def smoke_args(tmp_path: Path, **overrides):
    values = {
        "iteration_type": [],
        "static_command": [],
        "focused_command": [],
        "docs_only_change": False,
        "ui_report_only_change": False,
        "broad_change": False,
        "release_quality": False,
        "force_standing_smoke": False,
        "force_rotating_smoke": False,
        "force_patient_portal_smoke": False,
        "skip_standing_smoke": False,
        "skip_rotating_smoke": False,
        "skip_patient_portal_smoke": False,
        "dry_run": True,
        "base_url": "http://127.0.0.1:8766",
        "scope": "umls_evidence",
        "queries": ROOT / "config" / "search_quality_paragraph_queries.tsv",
        "top_k": 60,
        "timeout": 90.0,
        "workers": 2,
        "output_root": tmp_path / "experiments",
        "html_report": tmp_path / "experiments.html",
        "require_api_backend": "elasticsearch",
        "verification_run_dir": str(tmp_path / "verification"),
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_payloads(path: Path, payloads: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(payload, sort_keys=True) + "\n" for payload in payloads),
        encoding="utf-8",
    )


def test_iteration_smoke_docs_only_static_plan_skips_live_smoke(tmp_path: Path) -> None:
    module = load_script_module()
    args = smoke_args(
        tmp_path,
        iteration_type=["process"],
        docs_only_change=True,
        static_command=["node --check /tmp/report.js"],
    )

    types = module.normalize_iteration_types(args.iteration_type)
    decision = module.smoke_tier_decision(args, types)
    steps = module.build_iteration_smoke_steps(args, "SQI-docs", types)

    assert decision["standing_smoke"] is False
    assert decision["rotating_smoke"] is False
    assert [step["tier"] for step in steps] == ["static"]
    assert steps[0]["command"] == "node --check /tmp/report.js"


def test_iteration_smoke_ranking_plan_includes_focused_standing_rotating_and_portal(tmp_path: Path) -> None:
    module = load_script_module()
    args = smoke_args(
        tmp_path,
        iteration_type=["ranking"],
        focused_command=["python3 -m pytest tests/test_evidence_vectors.py -k ranking -q"],
    )

    types = module.normalize_iteration_types(args.iteration_type)
    decision = module.smoke_tier_decision(args, types)
    steps = module.build_iteration_smoke_steps(args, "SQI-ranking", types)

    assert decision["standing_smoke"] is True
    assert decision["rotating_smoke"] is True
    assert decision["patient_portal_smoke"] is True
    assert [step["tier"] for step in steps] == ["focused", "standing", "rotating", "patient_portal"]
    assert "evaluate_search_api.py" in module.command_text(steps[1]["command"])
    rotating_text = module.command_text(steps[2]["command"])
    assert "--query-limit 50" in rotating_text
    assert "--workers 2" in rotating_text
    assert "--fail-gates" in rotating_text
    portal_text = module.command_text(steps[3]["command"])
    assert "search_quality_patient_portal_queries.tsv" in portal_text
    assert "--query-limit 0" in portal_text
    assert "--run-family patient_portal" in portal_text
    assert "--fail-gates" in portal_text


def test_iteration_smoke_can_skip_patient_portal_lane(tmp_path: Path) -> None:
    module = load_script_module()
    args = smoke_args(
        tmp_path,
        iteration_type=["ranking"],
        skip_patient_portal_smoke=True,
    )

    types = module.normalize_iteration_types(args.iteration_type)
    decision = module.smoke_tier_decision(args, types)
    steps = module.build_iteration_smoke_steps(args, "SQI-ranking", types)

    assert decision["standing_smoke"] is True
    assert decision["rotating_smoke"] is True
    assert decision["patient_portal_smoke"] is False
    assert [step["tier"] for step in steps] == ["standing", "rotating"]


def test_patient_portal_run_family_is_first_class() -> None:
    module = load_script_module()

    assert module.RUN_FAMILY_DEFINITIONS["patient_portal"]["class"] == "benchmark"
    assert "patient_portal" in module.RUN_FAMILY_ORDER
    assert "current" in module.RUN_FAMILY_INTERPRETATIONS["patient_portal"].lower()
    assert "history" in module.RUN_FAMILY_INTERPRETATIONS["patient_portal"].lower()


def test_gate_baseline_requires_matching_payload_shape(tmp_path: Path) -> None:
    module = load_script_module()
    queries = tmp_path / "search_quality_patient_portal_queries.tsv"
    queries.write_text("id\tquery\texpected_cuis\nq1\tportal message\tC0000001\n", encoding="utf-8")
    manifest = {
        "runs": [
            {
                "run_id": "lean_baseline",
                "created_at": "2026-06-10T19:00:00Z",
                "search_system": module.SEARCH_SYSTEM_API,
                "api_scope": module.SEARCH_SCOPE_UMLS_EVIDENCE,
                "queries": str(queries),
                "evaluation_signature": "same-signature",
                "top_k": 60,
                "include_related": False,
                "include_linked_concepts": False,
                "include_search_evidence_items": False,
            },
            {
                "run_id": "evidence_item_capture",
                "created_at": "2026-06-10T19:30:00Z",
                "search_system": module.SEARCH_SYSTEM_API,
                "api_scope": module.SEARCH_SCOPE_UMLS_EVIDENCE,
                "queries": str(queries),
                "evaluation_signature": "same-signature",
                "top_k": 60,
                "include_related": False,
                "include_linked_concepts": False,
                "include_search_evidence_items": True,
            },
        ]
    }

    baseline = module.find_previous_gate_baseline(
        manifest,
        search_system=module.SEARCH_SYSTEM_API,
        queries=queries,
        api_scope=module.SEARCH_SCOPE_UMLS_EVIDENCE,
        current_signature="same-signature",
        payload_shape={
            "top_k": 60,
            "include_related": False,
            "include_linked_concepts": False,
            "include_search_evidence_items": False,
        },
    )

    assert baseline["run_id"] == "lean_baseline"


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


def test_run_experiment_parallel_api_keeps_order_and_writes_timings(tmp_path: Path, monkeypatch) -> None:
    module = load_script_module()
    queries = tmp_path / "queries.tsv"
    queries.write_text(
        "\n".join(
            [
                "id\tquery\texpected_cuis",
                "q1\tslow concept\tC0000001",
                "q2\tfast concept\tC0000002",
                "q3\tmiddle concept\tC0000003",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    alternatives = tmp_path / "alternatives.tsv"
    alternatives.write_text("expected_cui\tacceptable_cui\n", encoding="utf-8")
    cui_by_query = {
        "slow concept": "C0000001",
        "fast concept": "C0000002",
        "middle concept": "C0000003",
    }
    delay_by_query = {
        "slow concept": 0.04,
        "fast concept": 0.0,
        "middle concept": 0.02,
    }

    def fake_get_json(base_url, path, params, *, timeout):
        query = str(params["q"])
        time.sleep(delay_by_query[query])
        return {
            "backend": "elasticsearch",
            "elapsed_ms": delay_by_query[query] * 1000,
            "server_timing": {
                "total_ms": delay_by_query[query] * 1000,
                "by_stage": {
                    "embedding": 2.0,
                    "base_vector_search": 2.5,
                    "long_document_chunk_vector_search": 3.5,
                    "mention_extraction": 4.0,
                    "long_document_mention_extraction": 6.0,
                    "label_fallback_and_ranking": 5.0,
                    "long_document_merge_and_ranking": 7.0,
                    "active_label_context_search": 1.25,
                    "long_document_support_signals": 0.75,
                    "long_document_merge_ranking": 2.0,
                    "response_compaction": 0.5,
                },
            },
            "hits": [
                {
                    "cui": cui_by_query[query],
                    "name": query,
                    "semantic_group": "Concepts & Ideas",
                    "sources": ["TEST"],
                    "source_mix": {"items": [{"source": "TEST", "sample_refs": 1}]},
                }
            ],
        }

    monkeypatch.setattr(module, "get_json", fake_get_json)
    args = argparse.Namespace(
        label="parallel-test",
        run_id="parallel-test",
        run_family="smoke",
        queries=queries,
        query_limit=0,
        query_selection="first",
        query_rotation_seed="",
        alternatives=alternatives,
        base_url="http://127.0.0.1:8766",
        require_api_backend="elasticsearch",
        mode="balanced",
        scope=module.SEARCH_SCOPE_UMLS_EVIDENCE,
        top_k=5,
        include_related=False,
        include_linked_concepts=False,
        include_search_evidence_items=False,
        timeout=1.0,
        workers=2,
        output_root=tmp_path / "experiments",
        verbose=False,
    )

    run = module.run_experiment(args, search_system=module.SEARCH_SYSTEM_API)

    rows_path = Path(run["rows_path"])
    with rows_path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert [row["id"] for row in rows] == ["q1", "q2", "q3"]
    assert run["workers"] == 2
    assert run["summary"]["workers"] == 2
    assert run["summary"]["query_parallelism_saved_seconds"] > 0

    timings_path = Path(run["query_timings_path"])
    with timings_path.open("r", encoding="utf-8", newline="") as handle:
        timings = list(csv.DictReader(handle, delimiter="\t"))
    assert [row["id"] for row in timings] == ["q1", "q2", "q3"]
    assert [row["backend"] for row in timings] == ["elasticsearch", "elasticsearch", "elasticsearch"]
    assert timings[0]["server_embedding_ms"] == "2.0"
    assert timings[0]["server_mention_extraction_ms"] == "10.0"
    assert timings[0]["server_ranking_ms"] == "9.0"
    assert run["summary"]["server_embedding_sum_seconds"] == 0.006
    assert run["summary"]["server_ranking_sum_seconds"] == 0.027
    assert run["summary"]["server_timing_total_sum_seconds"] == 0.06


def test_query_timing_row_uses_uncached_server_timing_for_cached_response() -> None:
    module = load_script_module()
    spec = module.QuerySpec(query_id="q1", query="cached concept", expected_cuis=[])

    row = module.query_timing_row(
        spec,
        {
            "backend": "elasticsearch",
            "elapsed_ms": 1.2,
            "cache_hit": True,
            "server_timing": {
                "total_ms": 1.2,
                "by_stage": {"cache_lookup": 0.8},
            },
            "uncached_server_timing": {
                "total_ms": 42.0,
                "by_stage": {
                    "embedding": 3.0,
                    "base_vector_search": 4.0,
                },
            },
            "hits": [],
        },
        hit_count=0,
        elapsed_seconds=0.002,
    )

    assert row["cache_hit"] == "1"
    assert row["server_total_ms"] == 42.0
    assert row["server_embedding_ms"] == 3.0
    assert row["server_base_vector_search_ms"] == 4.0


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
