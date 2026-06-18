from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_pruned_umls_rrf_subset.py"


def load_builder_module():
    spec = importlib.util.spec_from_file_location("build_pruned_umls_rrf_subset", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def row(fields: list[str]) -> str:
    return "|".join(fields) + "|\n"


def write_rrf(path: Path, rows: list[list[str]]) -> None:
    path.write_text("".join(row(fields) for fields in rows), encoding="utf-8")


def mrrel_row(rel: str, sab: str, rui: str) -> list[str]:
    return [
        "C0000001",
        "A0000001",
        "CUI",
        rel,
        "C0000002",
        "A0000002",
        "CUI",
        "related_to",
        rui,
        "",
        sab,
        sab,
        "",
        "",
        "N",
        "",
    ]


def mrsat_row(stype: str, atn: str, sab: str, atv: str = "value") -> list[str]:
    return [
        "C0000001",
        "L0000001",
        "S0000001",
        "AT0000001",
        stype,
        "CODE",
        "ATUI",
        "SATUI",
        atn,
        sab,
        atv,
        "N",
        "",
    ]


def write_tiny_meta(meta: Path) -> None:
    meta.mkdir(parents=True)
    filenames = [
        "MRFILES.RRF",
        "MRCOLS.RRF",
        "MRDOC.RRF",
        "MRSAB.RRF",
        "MRCONSO.RRF",
        "MRSTY.RRF",
        "MRREL.RRF",
        "MRDEF.RRF",
        "MRSAT.RRF",
        "MRHIER.RRF",
        "MRXW_ENG.RRF",
        "MRMAP.RRF",
        "AMBIGSUI.RRF",
        "MRHIST.RRF",
    ]
    write_rrf(
        meta / "MRFILES.RRF",
        [[name, f"{name} description", "fmt", "class", "0", "0"] for name in filenames],
    )
    write_rrf(
        meta / "MRCOLS.RRF",
        [
            ["CUI", "desc", "", "", "", "", "MRCONSO.RRF"],
            ["REL", "desc", "", "", "", "", "MRREL.RRF"],
            ["PTR", "desc", "", "", "", "", "MRHIER.RRF"],
            ["ATN", "desc", "", "", "", "", "MRSAT.RRF"],
            ["MAPSETCUI", "desc", "", "", "", "", "MRMAP.RRF"],
            ["SUI", "desc", "", "", "", "", "AMBIGSUI.RRF"],
            ["WD", "desc", "", "", "", "", "MRXW_ENG.RRF"],
            ["HIST", "desc", "", "", "", "", "MRHIST.RRF"],
        ],
    )
    write_rrf(
        meta / "MRDOC.RRF",
        [
            ["ATN", "SUBSET_MEMBER", "expanded_form", "Subset member"],
            ["REL", "RO", "expanded_form", "other relationship"],
        ],
    )
    mrsab = ["" for _ in range(25)]
    mrsab[3] = "SNOMEDCT_US"
    mrsab[18] = "SUBSET_MEMBER,NDC,DA"
    write_rrf(meta / "MRSAB.RRF", [mrsab])
    write_rrf(
        meta / "MRCONSO.RRF",
        [
            [
                "C0000001",
                "ENG",
                "P",
                "L0000001",
                "PF",
                "S0000001",
                "Y",
                "A0000001",
                "",
                "SCUI",
                "SDUI",
                "SNOMEDCT_US",
                "PT",
                "CODE",
                "Example label",
                "0",
                "N",
                "",
            ]
        ],
    )
    write_rrf(meta / "MRSTY.RRF", [["C0000001", "T047", "B2.2.1.2.1", "Disease or Syndrome", "ATUI"]])
    write_rrf(
        meta / "MRREL.RRF",
        [
            mrrel_row("RO", "SNOMEDCT_US", "RKEEP1"),
            mrrel_row("RO", "MDRSPA", "RDROP_MDR"),
            mrrel_row("SY", "RXNORM", "RDROP_RXNORM_SY"),
            mrrel_row("RO", "MDR", "RKEEP_MDR"),
        ],
    )
    write_rrf(meta / "MRDEF.RRF", [["C0000001", "A0000001", "ATUI", "SATUI", "MSH", "Definition", "N"]])
    write_rrf(
        meta / "MRSAT.RRF",
        [
            mrsat_row("CUI", "NDC", "MTHSPL", "12345"),
            mrsat_row("RUI", "SOURCEUI", "SNOMEDCT_US"),
            mrsat_row("CUI", "SOURCEUI", "MDRSPA"),
            mrsat_row("CUI", "SUBSET_MEMBER", "MTH"),
            mrsat_row("CUI", "SOURCEUI", "NCBI"),
        ],
    )
    write_rrf(
        meta / "MRHIER.RRF",
        [
            ["C0000001", "A0000001", "CXN", "PAUI", "SNOMEDCT_US", "isa", "PTR", "HCD", ""],
            ["C0000001", "A0000001", "CXN", "PAUI", "MDRSPA", "isa", "PTR", "HCD", ""],
        ],
    )
    for name in ["MRXW_ENG.RRF", "MRMAP.RRF", "AMBIGSUI.RRF", "MRHIST.RRF"]:
        write_rrf(meta / name, [["omitted"]])


def test_pruned_rrf_subset_applies_distribution_cuts(tmp_path: Path) -> None:
    builder = load_builder_module()
    source_meta = tmp_path / "source" / "META"
    out_meta = tmp_path / "build" / "umls_rrf_subset" / "META"
    write_tiny_meta(source_meta)

    manifest = builder.build_subset(
        source_meta=source_meta,
        out_meta=out_meta,
        replace=True,
        attribute_cut=True,
    )

    included = set(manifest["included_rrf_files"])
    assert {"MRCONSO.RRF", "MRSTY.RRF", "MRREL.RRF", "MRDEF.RRF", "MRSAB.RRF"} <= included
    assert "MRSAT.RRF" in included
    assert "MRHIER.RRF" in included
    assert "MRXW_ENG.RRF" not in included
    assert "MRMAP.RRF" not in included
    assert "AMBIGSUI.RRF" not in included
    assert "MRHIST.RRF" not in included

    mrrel = (out_meta / "MRREL.RRF").read_text(encoding="utf-8")
    assert "RKEEP1" in mrrel
    assert "RKEEP_MDR" in mrrel
    assert "RDROP_MDR" not in mrrel
    assert "RDROP_RXNORM_SY" not in mrrel

    mrsat = (out_meta / "MRSAT.RRF").read_text(encoding="utf-8")
    assert "12345" in mrsat
    assert "RUI" not in mrsat
    assert "MDRSPA" not in mrsat
    assert "SUBSET_MEMBER" not in mrsat
    assert "NCBI" not in mrsat

    mrhier = (out_meta / "MRHIER.RRF").read_text(encoding="utf-8")
    assert "SNOMEDCT_US" in mrhier
    assert "MDRSPA" not in mrhier

    assert "SUBSET_MEMBER" not in (out_meta / "MRDOC.RRF").read_text(encoding="utf-8")
    mrsab = (out_meta / "MRSAB.RRF").read_text(encoding="utf-8")
    assert "NDC,DA" in mrsab
    assert "SUBSET_MEMBER" not in mrsab

    mrcols = (out_meta / "MRCOLS.RRF").read_text(encoding="utf-8")
    assert "MRCONSO.RRF" in mrcols
    assert "MRMAP.RRF" not in mrcols
    assert "AMBIGSUI.RRF" not in mrcols
    assert "MRXW_ENG.RRF" not in mrcols
    assert "MRHIST.RRF" not in mrcols
    assert "MRHIER.RRF" in mrcols
    assert "MRSAT.RRF" in mrcols

    mrfiles = (out_meta / "MRFILES.RRF").read_text(encoding="utf-8")
    assert "MRCONSO.RRF" in mrfiles
    assert "MRMAP.RRF" not in mrfiles
    assert "AMBIGSUI.RRF" not in mrfiles
    assert "MRXW_ENG.RRF" not in mrfiles
    assert "MRHIST.RRF" not in mrfiles
    assert "MRHIER.RRF" in mrfiles
    assert "MRSAT.RRF" in mrfiles

    manifest_path = out_meta.parent / "rrf_subset_manifest.json"
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert written_manifest["attribute_cut"] is True
    assert written_manifest["files"]["MRREL.RRF"]["drop_reasons"] == {
        "mdr_translation": 1,
        "rxnorm_sy": 1,
    }
    assert written_manifest["files"]["MRSAT.RRF"]["drop_reasons"] == {
        "mdr_translation": 1,
        "ncbi_attribute": 1,
        "rui_attribute": 1,
        "subset_member_attribute": 1,
    }
