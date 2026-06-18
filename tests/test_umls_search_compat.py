from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.code_index import build_code_index, build_runtime_code_index
from qe_evidence_vectors.search_service import SearchIndex
from qe_evidence_vectors.semantic_type_index import build_semantic_type_index
from qe_evidence_vectors.umls_search_compat import umls_search_response


def write_mrconso(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "C0000001|ENG|P|L1|PF|S1|Y|A0000001||D000001|D000001|MSH|MH|D000001|Heart attack|0|N||",
                "C0000002|ENG|P|L2|PF|S2|Y|A0000002||D000002|D000002|MSH|MH|D000002|Myocardial infarction|0|N||",
                "C0000003|ENG|P|L3|PF|S3|Y|A0000003||D000003|D000003|MSH|MH|D000003|Bronchitis|0|N||",
                "C0000004|ENG|P|L4|PF|S4|Y|A0000004||111|D000004|SNOMEDCT_US|PT|111|Bronchial artery|0|N||",
                "C0000005|ENG|P|L5|PF|S5|Y|A0000005||D000005|D000005|MSH|MH|D000005|Colitis|0|N||",
                "C0000006|ENG|P|L6|PF|S6|Y|A0000006|||7057|RXNORM|IN|7057|insulins|0|N||",
                "C0000007|ENG|P|L7|PF|S7|Y|A0000007||D000007|D000007|MSH|MH|D000007|Hidden fever|0|Y||",
                "C0000008|ENG|P|L8|PF|S8|Y|A0000008||9468002|D9468002|SNOMEDCT_US|PT|9468002|Fracture of carpal bone|0|N||",
                "C0000009|ENG|P|L9|PF|S9|Y|A0000009||GENE1|GENE1|HGNC|PT|GENE1|INS gene|0|N||",
                "C0000010|ENG|P|L10|PF|S10|Y|A0000010||D000010|D000010|MSH|MH|D000010|Old fever|0|O||",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_mrsty(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "C0000001|T047|B2.2.1.2.1|Disease or Syndrome|AT0000001|",
                "C0000002|T047|B2.2.1.2.1|Disease or Syndrome|AT0000002|",
                "C0000003|T047|B2.2.1.2.1|Disease or Syndrome|AT0000003|",
                "C0000004|T023|A1.2.3.1|Body Part, Organ, or Organ Component|AT0000004|",
                "C0000005|T047|B2.2.1.2.1|Disease or Syndrome|AT0000005|",
                "C0000006|T116|A1.4.1.1.3|Amino Acid, Peptide, or Protein|AT0000006|",
                "C0000007|T184|A2.2.2|Sign or Symptom|AT0000007|",
                "C0000008|T037|B2.3|Injury or Poisoning|AT0000008|",
                "C0000009|T028|A1.2.3.5|Gene or Genome|AT0000009|",
                "C0000010|T184|A2.2.2|Sign or Symptom|AT0000010|",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def build_index(tmp_path: Path) -> SearchIndex:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    full_codes = tmp_path / "codes.full.sqlite"
    codes = tmp_path / "codes.runtime.sqlite"
    semantic_types = tmp_path / "semantic_types.sqlite"
    write_mrconso(mrconso)
    write_mrsty(mrsty)
    build_code_index(
        mrconso_path=mrconso,
        out_path=full_codes,
        include_suppressed=True,
        replace=True,
    )
    build_runtime_code_index(source_path=full_codes, out_path=codes, replace=True)
    build_semantic_type_index(mrsty_path=mrsty, out_path=semantic_types, replace=True)
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
        label_index_paths=[],
        code_index_path=codes,
        semantic_type_index_path=semantic_types,
    )


def response(index: SearchIndex, query: str) -> dict:
    return umls_search_response(index, parse_qs(query), version="2025AB")


def result_uis(payload: dict) -> list[str]:
    return [row["ui"] for row in payload["result"]["results"]]


def test_umls_compat_exact_and_words_search_keep_concept_output(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    exact = response(index, "string=Fracture+of+carpal+bone&searchType=exact&pageSize=25")
    words = response(index, "string=carpal+fracture&searchType=words")

    assert exact["pageSize"] == 25
    assert exact["pageNumber"] == 1
    assert exact["result"]["classType"] == "searchResults"
    assert exact["result"]["results"][0] == {
        "ui": "C0000008",
        "rootSource": "SNOMEDCT_US",
        "uri": "https://uts-ws.nlm.nih.gov/rest/content/2025AB/CUI/C0000008",
        "name": "Fracture of carpal bone",
        "semanticTypes": ["Injury or Poisoning"],
    }
    assert result_uis(words) == ["C0000008"]


def test_umls_compat_truncation_and_normalized_search_types(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    right = response(index, "string=bronch&searchType=rightTruncation")
    left = response(index, "string=itis&searchType=leftTruncation")
    normalized = response(index, "string=insulin&searchType=normalizedString")

    assert {"C0000003", "C0000004"} <= set(result_uis(right))
    assert {"C0000003", "C0000005"} <= set(result_uis(left))
    assert result_uis(normalized) == ["C0000006"]


def test_umls_compat_source_identifier_lookup_and_return_code(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    source_ui = response(
        index,
        "string=9468002&inputType=sourceUi&searchType=exact&sabs=SNOMEDCT_US",
    )
    source_code = response(
        index,
        "string=fracture+of+carpal+bone&searchType=exact&sabs=SNOMEDCT_US&returnIdType=code",
    )
    source_concept = response(
        index,
        "string=fracture+of+carpal+bone&searchType=exact&sabs=SNOMEDCT_US&returnIdType=sourceConcept",
    )
    source_aui = response(
        index,
        "string=fracture+of+carpal+bone&searchType=exact&sabs=SNOMEDCT_US&returnIdType=aui",
    )

    assert result_uis(source_ui) == ["C0000008"]
    assert source_code["result"]["results"][0]["ui"] == "9468002"
    assert source_code["result"]["results"][0]["rootSource"] == "SNOMEDCT_US"
    assert source_code["result"]["results"][0]["name"] == "Fracture of carpal bone"
    assert source_concept["result"]["results"][0]["ui"] == "9468002"
    assert source_aui["result"]["results"][0]["ui"] == "A0000008"


def test_umls_compat_semantic_type_and_group_filters(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    disease_by_tui = response(index, "string=bronch&searchType=rightTruncation&semanticTypes=T047")
    anatomy_by_group = response(index, "string=bronch&searchType=rightTruncation&semanticGroups=Anatomy")
    gene_or_protein = response(
        index,
        "string=ins&searchType=rightTruncation&semanticTypes=Gene+or+Genome|Amino+Acid,+Peptide,+or+Protein",
    )

    assert result_uis(disease_by_tui) == ["C0000003"]
    assert result_uis(anatomy_by_group) == ["C0000004"]
    assert set(result_uis(gene_or_protein)) == {"C0000006", "C0000009"}


def test_umls_compat_include_suppressible_controls_suppressed_rows(tmp_path: Path) -> None:
    index = build_index(tmp_path)

    hidden_default = response(index, "string=hidden+fever&searchType=exact")
    hidden_included = response(
        index,
        "string=hidden+fever&searchType=exact&includeSuppressible=true",
    )
    old_default = response(index, "string=old+fever&searchType=exact")
    old_suppressible_only = response(
        index,
        "string=old+fever&searchType=exact&includeSuppressible=true",
    )
    old_included = response(
        index,
        "string=old+fever&searchType=exact&includeObsolete=true",
    )

    assert hidden_default["result"]["results"] == []
    assert result_uis(hidden_included) == ["C0000007"]
    assert old_default["result"]["results"] == []
    assert old_suppressible_only["result"]["results"] == []
    assert result_uis(old_included) == ["C0000010"]
