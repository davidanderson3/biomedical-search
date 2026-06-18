from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from umls_resolver import (
    UMLSResolver,
    audit_index,
    build_index,
    iter_system_code_mentions,
    make_handler,
)


def mrconso_atom(
    cui: str,
    atom_id: int,
    sab: str,
    tty: str,
    code: str,
    label: str,
    *,
    scui: str = "",
    sdui: str = "",
    ispref: str = "Y",
    suppress: str = "N",
) -> str:
    fields = [
        cui,
        "ENG",
        "P",
        f"L{atom_id:07d}",
        "PF",
        f"S{atom_id:07d}",
        ispref,
        f"A{atom_id:07d}",
        "",
        scui,
        sdui,
        sab,
        tty,
        code,
        label,
        "0",
        suppress,
        "",
    ]
    return "|".join(fields) + "|\n"


def build_sample_index(tmp_path: Path) -> Path:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrsty = tmp_path / "MRSTY.RRF"
    mrconso.write_text(
        "".join(
            [
                mrconso_atom(
                    "C0004238",
                    1,
                    "MSH",
                    "MH",
                    "D001281",
                    "Atrial Fibrillation",
                    sdui="D001281",
                ),
                mrconso_atom(
                    "C0004238",
                    2,
                    "ICD10CM",
                    "PT",
                    "I48.91",
                    "Unspecified atrial fibrillation",
                    scui="I48.91",
                    ispref="N",
                ),
                mrconso_atom(
                    "C0004238",
                    3,
                    "SNOMEDCT_US",
                    "PT",
                    "49436004",
                    "Atrial fibrillation",
                    scui="49436004",
                ),
                mrconso_atom(
                    "C0011849",
                    4,
                    "SNOMEDCT_US",
                    "PT",
                    "73211009",
                    "Diabetes mellitus",
                    scui="73211009",
                ),
                mrconso_atom(
                    "C0011849",
                    5,
                    "ICD10CM",
                    "PT",
                    "E11.9",
                    "Type 2 diabetes mellitus without complications",
                    scui="E11.9",
                ),
                mrconso_atom(
                    "C3899401",
                    6,
                    "LNC",
                    "LA",
                    "LA17084-7",
                    "Positive",
                    sdui="LA17084-7",
                ),
            ]
        ),
        encoding="utf-8",
    )
    mrsty.write_text(
        "C0004238|T047|B2.2.1.2.1|Disease or Syndrome|AT1|\n"
        "C0011849|T047|B2.2.1.2.1|Disease or Syndrome|AT2|\n"
        "C3899401|T033|B2.2.1.2.1|Finding|AT3|\n",
        encoding="utf-8",
    )
    index = tmp_path / "umls_resolver.sqlite"
    stats = build_index(mrconso=mrconso, mrsty=mrsty, index=index)
    assert stats["labels"] == 6
    assert stats["codes"] == 6
    assert stats["semantic_types"] == 3
    return index


def test_resolver_builds_from_mrconso_and_resolves_long_text(tmp_path: Path) -> None:
    index = build_sample_index(tmp_path)
    resolver = UMLSResolver(index)
    try:
        payload = resolver.resolve(
            "Assessment: persistent atrial fibrillation. The chart also lists diabetes mellitus.",
            limit=10,
        )
    finally:
        resolver.close()

    cuis = [item["cui"] for item in payload["results"]]
    assert cuis[:2] == ["C0004238", "C0011849"]
    afib = payload["results"][0]
    assert afib["name"] == "Atrial Fibrillation"
    assert any(code["system"] == "ICD10CM" and code["code"] == "I48.91" for code in afib["codes"])
    assert afib["semantic_types"] == [{"tui": "T047", "name": "Disease or Syndrome"}]
    assert any(match["type"] == "text" and match["text"].lower() == "atrial fibrillation" for match in afib["matches"])


def test_resolver_accepts_cuis_codes_aliases_and_umls_atom_ids(tmp_path: Path) -> None:
    index = build_sample_index(tmp_path)
    resolver = UMLSResolver(index)
    try:
        payload = resolver.resolve(
            "C0004238 ICD10CM:I48.91 SNOMED CT US 49436004 LOINC LA17084-7 AUI:A0000001",
            limit=10,
        )
    finally:
        resolver.close()

    by_cui = {item["cui"]: item for item in payload["results"]}
    assert {"C0004238", "C3899401"} <= set(by_cui)
    match_types = {match["type"] for match in by_cui["C0004238"]["matches"]}
    assert {"cui", "system_code", "identifier"} <= match_types
    assert any(code["system"] == "SNOMEDCT_US" and code["code"] == "49436004" for code in by_cui["C0004238"]["codes"])
    assert any(code["system"] == "LNC" and code["code"] == "LA17084-7" for code in by_cui["C3899401"]["codes"])


def test_system_code_parser_handles_common_copied_forms() -> None:
    mentions = list(
        iter_system_code_mentions(
            "ICD 10 CM I48.91; SNOMED CT US 49436004; RxNorm:6809; LOINC LA17084-7"
        )
    )

    assert ("ICD10CM", "I48.91") in {(item["system"], item["code"]) for item in mentions}
    assert ("SNOMEDCT_US", "49436004") in {(item["system"], item["code"]) for item in mentions}
    assert ("RXNORM", "6809") in {(item["system"], item["code"]) for item in mentions}
    assert ("LNC", "LA17084-7") in {(item["system"], item["code"]) for item in mentions}


def test_quality_gate_respects_suppressed_atom_policy(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        mrconso_atom(
            "C9999999",
            1,
            "SNOMEDCT_US",
            "PT",
            "999999",
            "Retired test concept",
            scui="999999",
            suppress="O",
        ),
        encoding="utf-8",
    )

    default_index = tmp_path / "default.sqlite"
    default_stats = build_index(mrconso=mrconso, index=default_index)
    resolver = UMLSResolver(default_index)
    try:
        assert default_stats["source_atoms"] == 0
        assert default_stats["skipped_suppressed_atoms"] == 1
        assert resolver.resolve("Retired test concept 999999")["results"] == []
    finally:
        resolver.close()

    suppressed_index = tmp_path / "suppressed.sqlite"
    suppressed_stats = build_index(
        mrconso=mrconso,
        index=suppressed_index,
        include_suppressed=True,
    )
    resolver = UMLSResolver(suppressed_index)
    try:
        payload = resolver.resolve("SNOMED:999999")
        assert suppressed_stats["source_atoms"] == 1
        assert payload["results"][0]["cui"] == "C9999999"
        assert payload["results"][0]["matches"][0]["type"] == "system_code"
    finally:
        resolver.close()


def test_quality_gate_dedupes_codes_and_prefers_best_display_name(tmp_path: Path) -> None:
    mrconso = tmp_path / "MRCONSO.RRF"
    mrconso.write_text(
        "".join(
            [
                mrconso_atom(
                    "C0018801",
                    1,
                    "SNOMEDCT_US",
                    "FN",
                    "703272007",
                    "Heart failure with reduced ejection fraction (disorder)",
                    scui="703272007",
                    ispref="N",
                ),
                mrconso_atom(
                    "C0018801",
                    2,
                    "SNOMEDCT_US",
                    "SY",
                    "703272007",
                    "HFrEF - heart failure with reduced ejection fraction",
                    scui="703272007",
                    ispref="N",
                ),
                mrconso_atom(
                    "C0018801",
                    3,
                    "SNOMEDCT_US",
                    "PT",
                    "703272007",
                    "Heart failure with reduced ejection fraction",
                    scui="703272007",
                ),
                mrconso_atom(
                    "C0018801",
                    4,
                    "MSH",
                    "MH",
                    "D000001",
                    "Heart Failure, Systolic",
                    sdui="D000001",
                ),
            ]
        ),
        encoding="utf-8",
    )
    index = tmp_path / "dedupe.sqlite"
    build_index(mrconso=mrconso, index=index)
    resolver = UMLSResolver(index)
    try:
        payload = resolver.resolve("SNOMED CT US 703272007", limit=5)
    finally:
        resolver.close()

    result = payload["results"][0]
    snomed_rows = [
        code
        for code in result["codes"]
        if code["system"] == "SNOMEDCT_US" and code["code"] == "703272007"
    ]
    assert result["cui"] == "C0018801"
    assert result["name"] == "Heart Failure, Systolic"
    assert len(snomed_rows) == 1
    assert snomed_rows[0]["tty"] == "PT"


def test_quality_gate_handles_long_noisy_text_and_output_limits(tmp_path: Path) -> None:
    index = build_sample_index(tmp_path)
    noisy_text = " ".join(["unrelated clinical text"] * 500)
    resolver = UMLSResolver(index)
    try:
        payload = resolver.resolve(
            f"{noisy_text} ICD 10 CM I48.91 {noisy_text}",
            limit=1,
            code_limit=1,
        )
    finally:
        resolver.close()

    assert payload["result_count"] == 1
    assert payload["results"][0]["cui"] == "C0004238"
    assert len(payload["results"][0]["codes"]) == 1
    assert payload["results"][0]["matches"][0]["type"] == "system_code"


def test_http_api_resolves_get_and_post_requests(tmp_path: Path) -> None:
    index = build_sample_index(tmp_path)
    resolver = UMLSResolver(index)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(resolver))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    try:
        with urllib.request.urlopen(f"{base_url}/api/resolve?q=ICD10CM:I48.91&code_limit=1") as response:
            get_payload = json.loads(response.read().decode("utf-8"))
        request = urllib.request.Request(
            f"{base_url}/api/resolve",
            data=json.dumps({"q": "diabetes mellitus", "limit": 5}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            post_payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        resolver.close()

    assert get_payload["results"][0]["cui"] == "C0004238"
    assert len(get_payload["results"][0]["codes"]) == 1
    assert post_payload["results"][0]["cui"] == "C0011849"


def test_builtin_audit_enforces_real_index_quality_canaries(tmp_path: Path) -> None:
    index = build_sample_index(tmp_path)

    passing = audit_index(
        index,
        min_labels=6,
        min_codes=6,
        min_semantic_types=3,
        required_sabs=["MSH", "SNOMEDCT_US", "ICD10CM", "LNC"],
    )
    failing = audit_index(
        index,
        required_sabs=["RXNORM"],
        canaries=[("atrial fibrillation", "C0011849")],
    )

    assert passing["ok"] is True
    assert passing["failures"] == []
    assert failing["ok"] is False
    failure_names = {failure["name"] for failure in failing["failures"]}
    assert "required_sab:RXNORM" in failure_names
    assert "canary:atrial fibrillation" in failure_names
