from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from search_quality_shadow_reranker import (  # noqa: E402
    evaluate_evidence_promotion,
    extract_features,
    read_tsv,
    regression_triage_for_row,
    seed_judgments,
    train_shadow_reranker,
)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_seed_judgments_combines_expected_portal_audit_and_pubmed_sources(tmp_path: Path) -> None:
    paragraph = write(
        tmp_path / "paragraph.tsv",
        "id\tquery\texpected_cuis\twhy\tdisallowed_cuis\n"
        "paragraph_01\talpha disease\tC_POS\tcentral target\tC_BAD\n",
    )
    clinical = write(
        tmp_path / "clinical.tsv",
        "id\tquery\texpected_cuis\twhy\n"
        "clinical_01\tclinical text\tC_CLIN\tclinical target\n",
    )
    portal = write(
        tmp_path / "portal.tsv",
        "id\tquery\texpected_cuis\twhy\tdisallowed_cuis\tactive_cuis\tcontext_cuis\texpected_behavior\n"
        "portal_01\tportal text\tC_ACTIVE|C_CONTEXT\tportal why\tC_PORTAL_BAD\tC_ACTIVE\tC_CONTEXT\tactive first\n",
    )
    useful = write(
        tmp_path / "useful.tsv",
        "id\tcui\tlabel\twhy\n"
        "paragraph_01\tC_USEFUL\tUseful thing\tuseful secondary\n",
    )
    review = write(
        tmp_path / "review.tsv",
        "id\tcui\tlabel\treview_class\taction\twhy\n"
        "paragraph_01\tC_FALSE\tBad thing\ttrue_false_positive\tkeep_rule_candidate\tbad drift\n",
    )
    pubmed_slice = write(
        tmp_path / "slice.tsv",
        "id\tsplit\tfocus\twhy\n"
        "pubmed_01\tdev\tfocus\tkeep secondary concepts\n",
    )
    pubmed_queries = write(
        tmp_path / "pubmed.tsv",
        "id\tquery\texpected_cuis\twhy\tdisallowed_cuis\n"
        "pubmed_01\tPubMed text\tC_PUB\tpubmed target\tC_PUB_BAD\n"
        "pubmed_ignored\tOther text\tC_IGNORE\tignore\t\n",
    )
    out = tmp_path / "judgments.tsv"

    rows = seed_judgments(
        out,
        paragraph_queries=paragraph,
        clinical_queries=clinical,
        portal_queries=portal,
        useful_extras=useful,
        precision_review=review,
        pubmed_slice=pubmed_slice,
        pubmed_queries=pubmed_queries,
    )

    by_key = {(row["id"], row["cui"]): row["judgment"] for row in rows}
    assert by_key[("paragraph_01", "C_POS")] == "expected"
    assert by_key[("paragraph_01", "C_BAD")] == "disallowed"
    assert by_key[("paragraph_01", "C_USEFUL")] == "useful_extra"
    assert by_key[("paragraph_01", "C_FALSE")] == "true_false_positive"
    assert by_key[("portal_01", "C_ACTIVE")] == "active_expected"
    assert by_key[("portal_01", "C_CONTEXT")] == "context_expected"
    assert by_key[("portal_01", "C_PORTAL_BAD")] == "disallowed"
    assert by_key[("clinical_01", "C_CLIN")] == "expected"
    assert by_key[("pubmed_01", "C_PUB")] == "expected"
    assert ("pubmed_ignored", "C_IGNORE") not in by_key
    assert out.exists()


def test_extract_features_and_train_shadow_reranker_report(tmp_path: Path) -> None:
    judgments = write(
        tmp_path / "judgments.tsv",
        "id\tcui\tjudgment\ttarget\tweight\tsource\tlabel\tquery\twhy\n"
        "q1\tC_POS\texpected\t3\t3\tfixture\tAlpha disease\talpha beta disease\tcentral\n"
        "q1\tC_NEG\ttrue_false_positive\t-2\t4\tfixture\tGeneric noise\talpha beta disease\tnoise\n",
    )
    payload = {
        "id": "q1",
        "query": "alpha beta disease",
        "response": {
            "hits": [
                {
                    "cui": "C_NEG",
                    "name": "Generic noise",
                    "rank_score": 2.0,
                    "score": 2.0,
                    "semantic_group": "CONC",
                    "score_breakdown": {"generic_penalty": 0.4},
                    "assertion": {"status": "present"},
                },
                {
                    "cui": "C_POS",
                    "name": "Alpha beta disease",
                    "rank_score": 1.0,
                    "score": 1.0,
                    "semantic_group": "DISO",
                    "matched_query_span": "alpha beta disease",
                    "score_breakdown": {
                        "exact_label_component": 1.0,
                        "lexical_component": 1.0,
                    },
                    "assertion": {"status": "present"},
                    "semantic_types": [{"tui": "T047", "name": "Disease or Syndrome"}],
                },
                {
                    "cui": "C_OTHER",
                    "name": "Other",
                    "rank_score": 0.5,
                    "score": 0.5,
                    "semantic_group": "OTHER",
                },
            ]
        },
    }
    payloads = write(tmp_path / "payloads.jsonl", json.dumps(payload) + "\n")
    features = tmp_path / "features.tsv"

    feature_rows = extract_features(judgments, [payloads], features)
    assert len(feature_rows) == 3
    extracted = read_tsv(features)
    assert any(row["cui"] == "C_OTHER" and row["judgment"] == "unlabeled" for row in extracted)

    out_dir = tmp_path / "shadow"
    summary = train_shadow_reranker(features, out_dir, judgment_path=judgments, epochs=12)
    rank_rows = read_tsv(out_dir / "shadow_rank_rows.tsv")
    by_cui = {row["cui"]: row for row in rank_rows}

    assert summary["judged_rows"] == 2
    assert by_cui["C_POS"]["outcome"] == "win"
    assert int(by_cui["C_POS"]["ml_rank"]) < int(by_cui["C_POS"]["current_rank"])
    assert by_cui["C_NEG"]["outcome"] == "win"
    assert int(by_cui["C_NEG"]["ml_rank"]) > int(by_cui["C_NEG"]["current_rank"])
    assert (out_dir / "search_quality_shadow_reranker.html").exists()
    assert (out_dir / "shadow_regression_triage.tsv").exists()


def test_evidence_promotion_report_separates_positive_negative_and_unjudged(tmp_path: Path) -> None:
    judgments = write(
        tmp_path / "judgments.tsv",
        "id\tcui\tjudgment\ttarget\tweight\tsource\tlabel\tquery\twhy\n"
        "q1\tC_POS\texpected\t3\t3\tfixture\tAlpha disease\talpha disease\tcentral\n"
        "q2\tC_POS\texpected\t3\t3\tfixture\tAlpha disease\talpha disease flare\tcentral\n"
        "q1\tC_NEG\ttrue_false_positive\t-2\t4\tfixture\tTrial protocol\talpha disease\tnoise\n"
        "q2\tC_NEG\ttrue_false_positive\t-2\t4\tfixture\tTrial protocol\talpha disease flare\tnoise\n",
    )
    payloads = write(
        tmp_path / "payloads.jsonl",
        "\n".join(
            json.dumps(payload)
            for payload in [
                {
                    "id": "q1",
                    "query": "alpha disease",
                    "response": {
                        "hits": [
                            {
                                "cui": "C_POS",
                                "name": "Alpha disease",
                                "view": "pubmed_clinical_context",
                                "sources": ["pubmed"],
                                "evidence_items": [
                                    {
                                        "text": "Alpha disease diagnosis and treatment evidence.",
                                        "weight": 2,
                                        "sources": [{"source": "pubmed"}],
                                    }
                                ],
                            },
                            {
                                "cui": "C_NEG",
                                "name": "Trial protocol",
                                "view": "clinicaltrials_protocol_context",
                                "sources": ["clinicaltrials_gov"],
                                "evidence_items": [
                                    {
                                        "text": "Eligibility criteria and primary outcome measure from protocol text.",
                                        "weight": 1,
                                        "sources": [{"source": "clinicaltrials_gov"}],
                                    }
                                ],
                            },
                            {
                                "cui": "C_OTHER",
                                "name": "Unjudged item",
                                "view": "dailymed_drug_label",
                                "sources": ["dailymed"],
                            },
                        ]
                    },
                },
                {
                    "id": "q2",
                    "query": "alpha disease flare",
                    "response": {
                        "hits": [
                            {
                                "cui": "C_POS",
                                "name": "Alpha disease",
                                "view": "pubmed_clinical_context",
                                "sources": ["pubmed"],
                                "evidence_items": [
                                    {
                                        "text": "Alpha disease diagnosis and treatment evidence.",
                                        "weight": 2,
                                        "sources": [{"source": "pubmed"}],
                                    }
                                ],
                            },
                            {
                                "cui": "C_NEG",
                                "name": "Trial protocol",
                                "view": "clinicaltrials_protocol_context",
                                "sources": ["clinicaltrials_gov"],
                                "evidence_items": [
                                    {
                                        "text": "Eligibility criteria and primary outcome measure from protocol text.",
                                        "weight": 1,
                                        "sources": [{"source": "clinicaltrials_gov"}],
                                    }
                                ],
                            },
                        ]
                    },
                },
            ]
        )
        + "\n",
    )

    summary = evaluate_evidence_promotion(
        judgments,
        [payloads],
        tmp_path / "evidence",
        top_k=10,
        min_positive=2,
        min_negative=2,
        min_judged=2,
        heldout_pct=0,
    )
    rows = read_tsv(tmp_path / "evidence" / "evidence_promotion_rows.tsv")
    by_scope_key = {(row["scope"], row["key"]): row for row in rows}

    assert summary["decision_counts"]["promote_candidate"] >= 3
    assert by_scope_key[("source", "pubmed")]["decision"] == "promote_candidate"
    assert by_scope_key[("source", "clinicaltrials_gov")]["decision"] == "demote_candidate"
    assert by_scope_key[("source", "dailymed")]["decision"] == "neutral_insufficient"
    assert "protocol_only_trial_text" in by_scope_key[
        ("source_type", "clinicaltrials_gov|clinicaltrials_protocol_context")
    ]["quality_flags"]
    policy_rows = read_tsv(tmp_path / "evidence" / "evidence_shadow_policy.tsv")
    policies = {(row["scope"], row["key"]): row["policy"] for row in policy_rows}
    assert policies[("source", "pubmed")] == "promote_shadow"
    assert policies[("source", "clinicaltrials_gov")] == "demote_shadow"
    assert ("source", "dailymed") not in policies

    feature_rows = extract_features(
        judgments,
        [payloads],
        tmp_path / "features_with_policy.tsv",
        evidence_policy_path=tmp_path / "evidence" / "evidence_shadow_policy.tsv",
    )
    q1_features = {row.meta["cui"]: row.features for row in feature_rows if row.meta["id"] == "q1"}
    assert q1_features["C_POS"]["evidence_policy_promote_shadow_count_log"] > 0
    assert q1_features["C_POS"]["evidence_policy_shadow_weight_sum"] > 0
    assert q1_features["C_NEG"]["evidence_policy_demote_shadow_count_log"] > 0
    assert q1_features["C_NEG"]["evidence_policy_shadow_weight_sum"] < 0
    assert "evidence_policy_match_count_log" not in q1_features["C_OTHER"]
    assert (tmp_path / "evidence" / "evidence_promotion_report.html").exists()
    assert read_tsv(tmp_path / "evidence" / "evidence_promotion_examples.tsv")


def test_shadow_regression_triage_classifies_strong_positive_demotions() -> None:
    cause, reason = regression_triage_for_row(
        {
            "target": "3",
            "judgment": "expected",
            "semantic_group": "CHEM",
            "current_rank": "6",
            "f_rank_score": "1.4",
            "f_query_name_overlap": "1",
            "f_matched_query_coverage": "0.03",
            "f_match_type_umls_label": "1",
        },
        "regression",
    )

    assert cause == "model_shape_issue"
    assert "CHEM" in reason
