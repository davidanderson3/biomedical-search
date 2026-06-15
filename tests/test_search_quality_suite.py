from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_search_quality_suite.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("run_search_quality_suite", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_suite_defines_core_layers() -> None:
    module = load_script_module()
    suite = module.load_suite(ROOT / "config" / "search_quality_suite.json")
    layers = {layer["id"]: layer for layer in suite["layers"]}

    assert {
        "unit_static_regressions",
        "coverage_representativeness_audit",
        "real_short_query_regression",
        "full_clinical_benchmark",
        "cycling_clinical_regression",
        "clinical_text_type_variety",
        "consumer_lay_language",
        "patient_portal_intent",
        "pubmed_approved_long_documents",
        "precision_safety",
        "external_embedding_neighbor_probe",
        "source_specific_evidence",
        "pubmed_focused_long_documents",
    } <= set(layers)
    assert {
        "suite_guard",
        "coverage_representativeness",
        "real_short_query_regression",
        "full_clinical_coverage",
        "cycling_regression",
        "clinical_text_type_variety",
        "consumer_lay_language",
        "workflow_intent",
        "long_document_recall",
        "precision_safety",
        "external_embedding_neighbors",
        "source_specific_evidence",
    } <= {layer.get("signal") for layer in suite["layers"]}
    assert layers["patient_portal_intent"]["blocking"] is True
    assert layers["coverage_representativeness_audit"]["blocking"] is False
    assert layers["coverage_representativeness_audit"]["known_weakness"] is True
    assert layers["coverage_representativeness_audit"]["kind"] == "command"
    assert layers["clinical_text_type_variety"]["blocking"] is False
    assert layers["clinical_text_type_variety"]["known_weakness"] is True
    assert layers["consumer_lay_language"]["blocking"] is False
    assert layers["consumer_lay_language"]["known_weakness"] is True
    assert layers["pubmed_approved_long_documents"]["known_weakness"] is True
    assert layers["external_embedding_neighbor_probe"]["blocking"] is False
    assert layers["external_embedding_neighbor_probe"]["kind"] == "command"
    assert layers["cycling_clinical_regression"]["query_selection"] == "rotate"
    assert layers["real_short_query_regression"]["thresholds"]["min_top_on_target_count"] == 20
    assert layers["source_specific_evidence"]["thresholds"]["min_queries_all_expected_at_10"] == 9
    assert layers["source_specific_evidence"]["thresholds"]["min_found_at_10"] == 20
    assert layers["source_specific_evidence"]["queries"] == "config/search_quality_source_specific_queries.tsv"
    assert (
        layers["clinical_text_type_variety"]["queries"]
        == "config/search_quality_clinical_text_variety_queries.tsv"
    )
    assert (
        layers["consumer_lay_language"]["queries"]
        == "config/search_quality_consumer_lay_queries.tsv"
    )


def test_real_short_query_regression_uses_primary_cuis_and_acceptables() -> None:
    with (ROOT / "config" / "search_quality_real_query_regression.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle, delimiter="\t")}

    for row_id in (
        "real_one-word-row-3",
        "real_one-word-row-7",
        "real_two-word-row-3",
        "real_two-word-row-4",
    ):
        assert "|" not in rows[row_id]["expected_cuis"]

    alternatives = (ROOT / "config" / "search_quality_acceptable_cui_alternatives.tsv").read_text(
        encoding="utf-8"
    )
    assert "C0011847\tC0011849" in alternatives
    assert "C0038454\tC0948008" in alternatives
    assert "C0004238\tC2926591" in alternatives
    assert "C0018801\tC0018802" in alternatives


def test_source_specific_evidence_uses_reviewed_acceptables() -> None:
    alternatives = (ROOT / "config" / "search_quality_acceptable_cui_alternatives.tsv").read_text(
        encoding="utf-8"
    )

    assert "C0041755\tC0413696" in alternatives
    assert "C0041755\tC0559546" in alternatives


def test_real_short_query_ui_asset_matches_reviewed_regression_queries() -> None:
    with (ROOT / "config" / "search_quality_real_query_regression.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        expected_queries = [row["query"] for row in csv.DictReader(handle, delimiter="\t")]

    asset_queries = json.loads(
        (ROOT / "docs" / "search_quality" / "real_short_queries.json").read_text(encoding="utf-8")
    )

    assert asset_queries == expected_queries
    assert len(asset_queries) == 20


def test_source_specific_suite_file_covers_core_source_families() -> None:
    with (ROOT / "config" / "search_quality_source_specific_queries.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert len(rows) == 9
    assert {row["source"] for row in rows} == {
        "dailymed",
        "medlineplus",
        "pubmed_pmc",
    }
    assert {"clinicaltrials_gov", "pubtator3"}.isdisjoint({row["source"] for row in rows})
    assert all(row["expected_cuis"] for row in rows)
    assert sum(len(row["expected_cuis"].split("|")) for row in rows) == 20


def test_external_embedding_neighbor_probe_is_opt_in_and_guarded() -> None:
    with (ROOT / "config" / "search_quality_external_embedding_neighbor_probe.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert len(rows) == 5
    assert {row["source"] for row in rows} == {"BioConceptVec", "cui2vec"}
    assert {row["mode"] for row in rows} == {"opt_in_association_signal"}
    assert {row["policy"] for row in rows} == {"candidate_subset", "suppress_default_noise"}
    assert sum(bool(row["positive_neighbor_cuis"]) for row in rows) >= 4
    assert all(row["disallowed_default_cuis"] for row in rows)
    assert any(row["policy"] == "suppress_default_noise" for row in rows)


def test_external_embedding_neighbors_are_not_search_server_default() -> None:
    server_source = (ROOT / "scripts" / "search_quality_server.py").read_text(encoding="utf-8")
    option_start = server_source.index('"--external-cui-vector-index"')
    option_end = server_source.index('"--definition-index"', option_start)
    option_block = server_source[option_start:option_end]

    assert "default=DEFAULT_EXTERNAL_CUI_VECTOR_INDEX" not in option_block
    assert "are not loaded by default" in option_block


def test_source_strategy_audit_records_marginal_value_policy() -> None:
    with (ROOT / "config" / "search_quality_source_strategy_audit.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = {row["id"]: row for row in csv.DictReader(handle, delimiter="\t")}

    assert rows["dailymed_top_drugs_vs_mthspl"]["policy"] == "core_relationship_source"
    assert int(rows["dailymed_top_drugs_vs_mthspl"]["cuis_outside_source_sab"]) == 253
    assert int(rows["dailymed_round4_vs_mthspl"]["cuis_outside_source_sab"]) == 360
    assert rows["medlineplus_full_vs_medlineplus_sab"]["policy"] == "core_consumer_context_source"
    assert int(rows["medlineplus_full_vs_medlineplus_sab"]["cuis_outside_source_sab"]) == 6141
    assert rows["clinicaltrials_default_source_policy"]["policy"] == "opt_in_posted_results_only"
    assert rows["pubtator3_relation_candidate_policy"]["policy"] == "opt_in_relation_candidate_stub"
    assert int(rows["pubtator3_relation_candidate_policy"]["direct_evidence_rows"]) == 100
    assert int(rows["pubtator3_relation_candidate_policy"]["direct_unique_cuis"]) == 87
    assert rows["cui2vec_external_neighbor_policy"]["policy"] == "opt_in_association_signal"
    assert rows["bioconceptvec_external_neighbor_policy"]["policy"] == "opt_in_association_signal"


def test_clinical_text_variety_suite_file_covers_realistic_note_formats() -> None:
    with (ROOT / "config" / "search_quality_clinical_text_variety_queries.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert len(rows) == 12
    assert {row["id"] for row in rows} == {
        "clinical_text_variety_01_discharge_summary",
        "clinical_text_variety_02_radiology_report",
        "clinical_text_variety_03_pathology_report",
        "clinical_text_variety_04_operating_note",
        "clinical_text_variety_05_nursing_note",
        "clinical_text_variety_06_lab_flowsheet",
        "clinical_text_variety_07_medication_administration_record",
        "clinical_text_variety_08_therapy_note",
        "clinical_text_variety_09_home_health_wound_note",
        "clinical_text_variety_10_telephone_triage",
        "clinical_text_variety_11_consult_note",
        "clinical_text_variety_12_prior_authorization",
    }
    assert sum(len(row["expected_cuis"].split("|")) for row in rows) == 60
    assert all(row["expected_cuis"] for row in rows)
    assert all("multilingual" not in row["why"].lower() for row in rows)


def test_consumer_lay_language_suite_file_covers_literal_drift_cases() -> None:
    with (ROOT / "config" / "search_quality_consumer_lay_queries.tsv").open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert len(rows) == 13
    assert {row["id"] for row in rows} == {
        "consumer_lay_01_water_pill",
        "consumer_lay_02_water_pill_furosemide",
        "consumer_lay_03_pee_test",
        "consumer_lay_04_urine_test",
        "consumer_lay_05_belly_pain",
        "consumer_lay_06_abdominal_pain",
        "consumer_lay_07_sugar_diabetes",
        "consumer_lay_08_heart_tracing",
        "consumer_lay_09_ekg",
        "consumer_lay_10_colon_scope",
        "consumer_lay_11_stomach_scope",
        "consumer_lay_12_blood_thinner",
        "consumer_lay_13_anticoagulant",
    }
    assert {row["source"] for row in rows} == {"consumer_lay"}
    assert all(row["expected_cuis"] for row in rows)
    disallowed_rows = {row["id"] for row in rows if row.get("disallowed_cuis")}
    assert {
        "consumer_lay_01_water_pill",
        "consumer_lay_05_belly_pain",
        "consumer_lay_07_sugar_diabetes",
        "consumer_lay_08_heart_tracing",
        "consumer_lay_10_colon_scope",
    } <= disallowed_rows


def test_experiment_command_uses_suite_id_and_rotation_seed(tmp_path: Path) -> None:
    module = load_script_module()
    suite = module.load_suite(ROOT / "config" / "search_quality_suite.json")
    layer = next(item for item in suite["layers"] if item["id"] == "cycling_clinical_regression")

    command = module.build_experiment_command(
        layer,
        suite=suite,
        suite_id="SQS-test",
        base_url="http://127.0.0.1:9999",
        output_root=tmp_path / "experiments",
        html_report=tmp_path / "experiments.html",
    )

    assert "--run-id" in command
    assert command[command.index("--run-id") + 1] == "SQS-test-cycling_clinical_regression"
    assert command[command.index("--base-url") + 1] == "http://127.0.0.1:9999"
    assert command[command.index("--query-rotation-seed") + 1] == "SQS-test-clinical-cycle"
    assert command[command.index("--query-limit") + 1] == "50"


def test_command_layer_templates_use_suite_id(tmp_path: Path) -> None:
    module = load_script_module()
    suite = module.load_suite(ROOT / "config" / "search_quality_suite.json")
    layer = next(item for item in suite["layers"] if item["id"] == "coverage_representativeness_audit")

    command = module.command_for_layer(
        layer,
        suite=suite,
        suite_id="SQS-template",
        base_url="http://127.0.0.1:9999",
        output_root=tmp_path / "experiments",
        html_report=tmp_path / "experiments.html",
    )

    assert isinstance(command, list)
    assert "build/search_quality_coverage_audit/SQS-template" in command
    assert module.format_command_template(
        ["jq", "{docs}", "{layer_id}", "{suite_id}"],
        suite_id="SQS template",
        layer=layer,
    ) == ["jq", "{docs}", "coverage_representativeness_audit", "SQS-template"]


def test_thresholds_check_counts_and_sources() -> None:
    module = load_script_module()
    checks = module.evaluate_thresholds(
        {
            "queries_all_expected_at_10": 11,
            "top_wrong_count": 1,
            "source_counts_at_10": {"pmc_oa": 0, "pubmed_bulk": 3},
        },
        {
            "min_queries_all_expected_at_10": 12,
            "max_top_wrong_count": 0,
            "source_min_counts_at_10": {"pmc_oa": 1, "pubmed_bulk": 1},
        },
    )

    by_name = {check["name"]: check for check in checks}
    assert by_name["queries_all_expected_at_10"]["passed"] is False
    assert by_name["top_wrong_count"]["passed"] is False
    assert by_name["source_counts_at_10.pmc_oa"]["passed"] is False
    assert by_name["source_counts_at_10.pubmed_bulk"]["passed"] is True


def test_dry_run_writes_suite_plan(tmp_path: Path, monkeypatch) -> None:
    module = load_script_module()
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "Tiny Suite",
                "layers": [
                    {
                        "id": "static",
                        "kind": "command",
                        "role": "static",
                        "blocking": True,
                        "command": ["python3", "--version"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "suite": suite_path,
            "suite_id": "SQS-dry-run",
            "base_url": "",
            "output_root": tmp_path / "out",
            "experiment_output_root": None,
            "html_report": None,
            "only": None,
            "skip_static": False,
            "dry_run": True,
            "fail_on": "blocking",
            "command_timeout": None,
        },
    )()

    result, exit_code = module.run_suite(args)

    assert exit_code == 0
    assert result["status"] == "planned"
    assert result["layers"][0]["status"] == "planned"
    assert (tmp_path / "out" / "SQS-dry-run" / "suite.json").exists()


def test_unknown_layer_filter_fails_fast(tmp_path: Path) -> None:
    module = load_script_module()
    args = type(
        "Args",
        (),
        {
            "suite": ROOT / "config" / "search_quality_suite.json",
            "suite_id": "SQS-bad-filter",
            "base_url": "",
            "output_root": tmp_path / "out",
            "experiment_output_root": None,
            "html_report": None,
            "only": ["not-a-layer"],
            "skip_static": False,
            "dry_run": True,
            "fail_on": "blocking",
            "command_timeout": None,
        },
    )()

    with pytest.raises(SystemExit, match="unknown suite layer"):
        module.run_suite(args)


def test_nonblocking_command_failure_is_reported_without_blocking_exit(tmp_path: Path) -> None:
    module = load_script_module()
    suite_path = tmp_path / "suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "Nonblocking Suite",
                "layers": [
                    {
                        "id": "known_probe",
                        "kind": "command",
                        "role": "probe",
                        "blocking": False,
                        "command": [sys.executable, "-c", "import sys; sys.exit(2)"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    args = type(
        "Args",
        (),
        {
            "suite": suite_path,
            "suite_id": "SQS-nonblocking",
            "base_url": "",
            "output_root": tmp_path / "out",
            "experiment_output_root": None,
            "html_report": None,
            "only": None,
            "skip_static": False,
            "dry_run": False,
            "fail_on": "blocking",
            "command_timeout": None,
        },
    )()

    result, exit_code = module.run_suite(args)

    assert exit_code == 0
    assert result["status"] == "nonblocking_failed"
    assert result["layers"][0]["status"] == "failed"
