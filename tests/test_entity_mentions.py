from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.code_index import build_code_index
from qe_evidence_vectors.label_index import build_label_index
from qe_evidence_vectors.search_rerank import LONG_DOCUMENT_MAX_ENTITY_MENTION_OCCURRENCES_PER_SPAN
from qe_evidence_vectors.search_service import SearchIndex
from qe_evidence_vectors.semantic_type_index import build_semantic_type_index


def write_mrconso(path: Path) -> None:
    path.write_text(
        "C0004238|ENG|P|L1|PF|S1|Y|A1||49436004|49436004|SNOMEDCT_US|PT|49436004|Atrial fibrillation|0|N||\n"
        "C0151613|ENG|P|L2|PF|S2|Y|A2||166686006|166686006|SNOMEDCT_US|PT|166686006|Electrolytes outside reference range|0|N||\n"
        "C0025859|ENG|P|L3|PF|S3|Y|A3|||6918|RXNORM|IN|6918|metoprolol|0|N||\n"
        "C0007131|ENG|P|L4|PF|S4|Y|A4||254637007|254637007|SNOMEDCT_US|PT|254637007|Non-small cell lung cancer|0|N||\n"
        "C0310367|ENG|P|L5|PF|S5|Y|A5||||MSH|MH|D013997|Today|0|N||\n",
        encoding="utf-8",
    )


def write_mrsty(path: Path) -> None:
    path.write_text(
        "C0004238|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C0151613|T033|A2.2|Finding|AT2|\n"
        "C0025859|T121|A1.4.1.1.1|Pharmacologic Substance|AT3|\n"
        "C0007131|T191|A1.2.3.5|Neoplastic Process|AT4|\n"
        "C0310367|T109|A1.4.1.2.1.7|Organic Chemical|AT5|\n",
        encoding="utf-8",
    )


def build_index(tmp_path: Path) -> SearchIndex:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    label_index = tmp_path / "labels.sqlite"
    code_index = tmp_path / "codes.sqlite"
    semantic_type_index = tmp_path / "semantic_types.sqlite"
    write_mrconso(mrconso)
    write_mrsty(mrsty)
    build_label_index(mrconso_path=mrconso, out_path=label_index, replace=True)
    build_code_index(mrconso_path=mrconso, out_path=code_index, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_type_index, replace=True)
    return SearchIndex(
        vector_paths=[],
        doc_paths=[],
        evidence_paths=[],
        provenance_index_path=None,
        provider="hashing",
        model=None,
        dim=16,
        local_files_only=True,
        max_seq_length=None,
        device="cpu",
        label_index_paths=[label_index],
        code_index_path=code_index,
        semantic_type_index_path=semantic_type_index,
    )


def test_search_response_includes_entity_mentions_with_offsets_assertions_and_codes(tmp_path: Path) -> None:
    index = build_index(tmp_path)
    query = (
        "No atrial fibrillation was seen. "
        "Electrolytes outside reference range prompted metoprolol review."
    )

    result = index.search(query, top_k=5, include_related=False, include_linked_concepts=True)
    mentions = {mention["text"].lower(): mention for mention in result["mentions"]}

    assert result["mentions_enabled"] is True
    assert result["mention_count"] == len(result["mentions"])
    assert mentions["atrial fibrillation"]["cui"] == "C0004238"
    assert mentions["atrial fibrillation"]["start"] == query.index("atrial fibrillation")
    assert mentions["atrial fibrillation"]["end"] == query.index(" was seen")
    assert mentions["atrial fibrillation"]["assertion"]["status"] == "negated"
    assert mentions["electrolytes outside reference range"]["cui"] == "C0151613"
    assert mentions["electrolytes outside reference range"]["assertion"]["status"] == "current"
    assert {row["system"] for row in mentions["metoprolol"]["codes"]} == {"RXNORM"}


def test_entity_mentions_expand_parenthetical_abbreviations(tmp_path: Path) -> None:
    index = build_index(tmp_path)
    query = (
        "BACKGROUND: Patients with non-small cell lung cancer (NSCLC) "
        "had NSCLC progression after therapy."
    )

    mentions = index.query_entity_mentions(query, limit=20)
    nsclc_mentions = [
        mention
        for mention in mentions
        if mention["text"] == "NSCLC" and mention.get("abbreviation_expansion")
    ]

    assert any(mention["cui"] == "C0007131" for mention in nsclc_mentions)
    assert {mention["section"] for mention in nsclc_mentions} == {"background"}


def test_entity_mentions_suppress_temporal_word_chemical_false_positive(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    mentions = index.query_entity_mentions(
        "The patient reports vaginal bleeding today.",
        limit=20,
    )

    assert all(mention["text"].lower() != "today" for mention in mentions)


def test_entity_mentions_reuse_repeated_span_lookups_and_cap_occurrences(tmp_path: Path) -> None:
    index = build_index(tmp_path)
    original_lookup = index.entity_mention_rows_for_lookup
    lookup_calls: list[str] = []

    def counted_lookup(lookup_norm: str, *, query_norm: str) -> list[dict]:
        lookup_calls.append(lookup_norm)
        return original_lookup(lookup_norm, query_norm=query_norm)

    index.entity_mention_rows_for_lookup = counted_lookup
    query = " ".join(["Atrial fibrillation was documented."] * 10)

    mentions = index.query_entity_mentions(query, limit=50)
    atrial_mentions = [
        mention
        for mention in mentions
        if mention["normalized_text"] == "atrial fibrillation"
    ]

    assert lookup_calls.count("atrial fibrillation") == 1
    assert len(atrial_mentions) == LONG_DOCUMENT_MAX_ENTITY_MENTION_OCCURRENCES_PER_SPAN
    assert any(mention["start"] == query.rindex("Atrial fibrillation") for mention in atrial_mentions)
    assert all(mention["cui"] == "C0004238" for mention in atrial_mentions)


def test_mentions_are_omitted_when_linked_concepts_are_disabled(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    result = index.search(
        "Atrial fibrillation treated with metoprolol.",
        top_k=5,
        include_related=False,
        include_linked_concepts=False,
    )

    assert result["mentions"] == []
    assert result["mentions_enabled"] is False
    assert result["mention_count"] == 0
