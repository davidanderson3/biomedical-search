from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.label_index import build_label_index
from qe_evidence_vectors.lexical_normalization import lexical_lookup_keys, lexical_normalized_key
from qe_evidence_vectors.search_label_fallback import LabelFallback
from qe_evidence_vectors.search_ranking import rank_hits
from qe_evidence_vectors.search_tokens import content_tokens


def test_content_tokens_share_specialist_lexical_normalization() -> None:
    assert content_tokens("status of pulmonary thrombus") == ["status", "pulmonary", "thrombus"]
    assert content_tokens("pulmonary thrombi and arterial emboli") == [
        "pulmonary",
        "thrombus",
        "arterial",
        "embolus",
    ]
    assert content_tokens("diabetes mellitus and sepsis") == ["diabetes", "mellitus", "sepsis"]


def test_lexical_lookup_keys_cover_surface_and_canonical_variants() -> None:
    assert lexical_normalized_key("middle cerebral arteries infarctions") == (
        "middle cerebral artery infarct"
    )
    keys = lexical_lookup_keys("middle cerebral arteries infarctions")

    assert "middle cerebral artery infarct" in keys
    assert "middle cerebral arteries infarction" in keys


def test_label_fallback_resolves_irregular_plural_query_against_literal_index(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "C9991001|ENG|P|L1|PF|S1|Y|A1|||D001|MSH|MH|D001|Pulmonary Artery Thrombus|0|N||\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "search_labels.sqlite"
    build_label_index(
        mrconso_path=mrconso,
        out_path=index_path,
        replace=True,
        include_lexical_variants=False,
    )
    fallback = LabelFallback([index_path])

    hits = fallback.search("pulmonary arteries thrombi", limit=5)

    assert hits[0]["cui"] == "C9991001"
    assert hits[0]["matched_query_span"] == "pulmonary arteries thrombi"
    assert hits[0]["matched_lookup_norm"] == "pulmonary artery thrombus"


def test_ranker_scores_irregular_plural_label_variant_as_exact_span() -> None:
    hit = {
        "cui": "C9991001",
        "name": "Pulmonary Artery Thrombus",
        "labels": ["Pulmonary Artery Thrombus"],
        "score": 0.82,
        "match_type": "umls_label",
        "matched_label": "Pulmonary Artery Thrombus",
        "matched_query_span": "pulmonary arteries thrombi",
        "sources": ["umls_label"],
        "evidence_count": 3,
        "semantic_types": [{"name": "Pathologic Function"}],
        "semantic_group": "DISO",
    }

    ranked = rank_hits("CTA described pulmonary arteries thrombi.", [hit], top_k=1)

    assert ranked[0]["score_breakdown"]["exact_span_component"] > 0.0
    assert ranked[0]["score_breakdown"]["lexical_component"] > 0.0
