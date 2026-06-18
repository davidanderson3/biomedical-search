#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_META = ROOT / "build" / "umls_rrf_subset" / "META"
POLICY_GUIDE = "/Users/andersondm2/umls-shrink/SCRIPT_CUTS.md"

REQUIRED_RRF_FILES = {
    "MRCONSO.RRF",
    "MRSTY.RRF",
    "MRREL.RRF",
    "MRDEF.RRF",
    "MRSAB.RRF",
    "MRFILES.RRF",
    "MRCOLS.RRF",
}

DEFAULT_RRF_FILES = REQUIRED_RRF_FILES | {
    "MRDOC.RRF",
    "MRHIER.RRF",
    "MRSAT.RRF",
}

REMOVED_RRF_FILES = {
    "AMBIGLUI.RRF",
    "AMBIGSUI.RRF",
    "MRCXT.RRF",
    "MRHIST.RRF",
    "MRMAP.RRF",
    "MRSMAP.RRF",
}

MDR_SAB_FIELD = {
    "MRREL.RRF": 10,
    "MRSAT.RRF": 9,
    "MRHIER.RRF": 4,
}


def is_word_index_rrf(name: str) -> bool:
    return name.startswith("MRX") and name.endswith(".RRF")


def is_appledouble(name: str) -> bool:
    return name.startswith("._")


def is_mdr_translation(value: bytes) -> bool:
    return value.startswith(b"MDR") and value != b"MDR"


def copy_payload_metadata(src: Path, dst: Path) -> None:
    try:
        shutil.copystat(src, dst)
    except OSError:
        pass


def read_rrf_rows(path: Path) -> list[list[str]]:
    rows: list[list[str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for line in handle:
            rows.append(line.rstrip("\n").split("|")[:-1])
    return rows


def write_rrf_rows(path: Path, rows: Iterable[list[str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write("|".join(row) + "|\n")


def count_rows(path: Path) -> int:
    rows = 0
    with path.open("rb") as handle:
        for _line in handle:
            rows += 1
    return rows


def selected_rrf_files(
    source_meta: Path,
    *,
    all_active_rrf: bool,
    include_rrf: Iterable[str],
) -> tuple[set[str], list[str]]:
    source_rrfs = {
        path.name
        for path in source_meta.glob("*.RRF")
        if not is_appledouble(path.name)
    }
    if all_active_rrf:
        selected = {
            name
            for name in source_rrfs
            if name not in REMOVED_RRF_FILES and not is_word_index_rrf(name)
        }
    else:
        selected = {name for name in DEFAULT_RRF_FILES if name in source_rrfs}
        selected.update(name for name in include_rrf if name in source_rrfs)

    missing_required = sorted(REQUIRED_RRF_FILES - source_rrfs)
    if missing_required:
        raise FileNotFoundError(
            "source META is missing required RRF file(s): "
            + ", ".join(missing_required)
        )
    skipped_missing = sorted(DEFAULT_RRF_FILES - source_rrfs)
    return selected, skipped_missing


def drop_reason_for_line(
    filename: str,
    line: bytes,
    *,
    attribute_cut: bool,
) -> str:
    fields = line.split(b"|")
    sab_index = MDR_SAB_FIELD.get(filename)
    if sab_index is not None and len(fields) > sab_index:
        if is_mdr_translation(fields[sab_index]):
            return "mdr_translation"
    if filename == "MRREL.RRF":
        if len(fields) > 10 and fields[3] == b"SY" and fields[10] == b"RXNORM":
            return "rxnorm_sy"
    if filename == "MRSAT.RRF":
        if len(fields) > 4 and fields[4] == b"RUI":
            return "rui_attribute"
        if attribute_cut and len(fields) > 10:
            atn = fields[8]
            sab = fields[9]
            if atn == b"SUBSET_MEMBER":
                return "subset_member_attribute"
            if sab == b"MTHSPL" and atn != b"NDC":
                return "mthspl_non_ndc"
            if sab == b"NCBI":
                return "ncbi_attribute"
            if sab == b"RXNORM" and atn in {b"RXAUI", b"RXCUI"}:
                return "rxnorm_rxaui_rxcui"
            if sab == b"MEDCIN":
                return "medcin_attribute"
            if sab == b"CHV":
                return "chv_attribute"
    return ""


def copy_filtered_rrf(
    src: Path,
    dst: Path,
    *,
    attribute_cut: bool,
) -> dict[str, int | dict[str, int]]:
    stats: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    with src.open("rb") as infile, dst.open("wb") as outfile:
        for line in infile:
            stats["scanned_rows"] += 1
            reason = drop_reason_for_line(src.name, line, attribute_cut=attribute_cut)
            if reason:
                stats["dropped_rows"] += 1
                stats["dropped_bytes"] += len(line)
                reasons[reason] += 1
                continue
            outfile.write(line)
            stats["kept_rows"] += 1
            stats["kept_bytes"] += len(line)
    copy_payload_metadata(src, dst)
    return {**dict(stats), "drop_reasons": dict(sorted(reasons.items()))}


def copy_rrf(src: Path, dst: Path) -> dict[str, int]:
    shutil.copyfile(src, dst)
    copy_payload_metadata(src, dst)
    return {"kept_rows": count_rows(dst), "kept_bytes": dst.stat().st_size}


def rewrite_mrcols(source: Path, target: Path, present_files: set[str]) -> dict[str, int]:
    kept: list[list[str]] = []
    dropped = 0
    for row in read_rrf_rows(source):
        if len(row) > 6 and row[6] not in present_files:
            dropped += 1
            continue
        kept.append(row)
    write_rrf_rows(target, kept)
    return {"kept_rows": len(kept), "dropped_rows": dropped}


def rewrite_mrdoc(source: Path, target: Path) -> dict[str, int]:
    kept: list[list[str]] = []
    dropped = 0
    for row in read_rrf_rows(source):
        if len(row) > 1 and row[0] == "ATN" and row[1] == "SUBSET_MEMBER":
            dropped += 1
            continue
        kept.append(row)
    write_rrf_rows(target, kept)
    return {"kept_rows": len(kept), "dropped_rows": dropped}


def rewrite_mrsab(source: Path, target: Path) -> dict[str, int]:
    rows: list[list[str]] = []
    changed = 0
    for row in read_rrf_rows(source):
        if len(row) > 18 and row[18]:
            before = row[18].split(",")
            after = [value for value in before if value != "SUBSET_MEMBER"]
            if after != before:
                changed += 1
                row = list(row)
                row[18] = ",".join(after)
        rows.append(row)
    write_rrf_rows(target, rows)
    return {"kept_rows": len(rows), "rows_changed": changed}


def rewrite_mrfiles(source_meta: Path, target_meta: Path, present_files: set[str]) -> dict[str, int]:
    source_rows = read_rrf_rows(source_meta / "MRFILES.RRF")
    rows: list[list[str]] = []
    for source_row in source_rows:
        if not source_row:
            continue
        row = list(source_row)
        while len(row) < 6:
            row.append("")
        filename = row[0]
        if filename == "MRFILES.RRF":
            rows.append(row)
            continue
        if filename in present_files and (target_meta / filename).exists():
            path = target_meta / filename
            row[4] = str(count_rows(path))
            row[5] = str(path.stat().st_size)
            rows.append(row)

    if not any(row and row[0] == "MRFILES.RRF" for row in rows):
        raise ValueError("source MRFILES.RRF does not describe MRFILES.RRF")

    mrfiles_row = next(row for row in rows if row[0] == "MRFILES.RRF")
    for _ in range(10):
        mrfiles_row[4] = str(len(rows))
        content = "".join("|".join(row) + "|\n" for row in rows)
        size = len(content.encode("utf-8"))
        if mrfiles_row[5] == str(size):
            break
        mrfiles_row[5] = str(size)

    target = target_meta / "MRFILES.RRF"
    target.write_text(content, encoding="utf-8")
    return {"kept_rows": len(rows), "kept_bytes": target.stat().st_size}


def remove_existing_output(out_meta: Path) -> None:
    if not out_meta.exists():
        return
    if out_meta.is_dir():
        shutil.rmtree(out_meta)
    else:
        out_meta.unlink()


def build_subset(
    *,
    source_meta: Path,
    out_meta: Path,
    replace: bool = False,
    all_active_rrf: bool = False,
    include_rrf: Iterable[str] = (),
    attribute_cut: bool = False,
) -> dict[str, object]:
    source_meta = source_meta.expanduser().resolve()
    out_meta = out_meta.expanduser()
    if not source_meta.exists():
        raise FileNotFoundError(source_meta)
    if out_meta.exists() and not replace:
        raise FileExistsError(f"{out_meta} already exists; pass --replace to overwrite")
    remove_existing_output(out_meta)
    out_meta.mkdir(parents=True, exist_ok=True)

    selected, skipped_missing = selected_rrf_files(
        source_meta,
        all_active_rrf=all_active_rrf,
        include_rrf=include_rrf,
    )
    present_files = set(selected)
    present_files.add("MRFILES.RRF")

    file_stats: dict[str, object] = {}
    for filename in sorted(selected):
        if filename == "MRFILES.RRF":
            continue
        source = source_meta / filename
        target = out_meta / filename
        if filename == "MRCOLS.RRF":
            file_stats[filename] = rewrite_mrcols(source, target, present_files)
        elif filename == "MRDOC.RRF":
            file_stats[filename] = rewrite_mrdoc(source, target)
        elif filename == "MRSAB.RRF":
            file_stats[filename] = rewrite_mrsab(source, target)
        elif filename in MDR_SAB_FIELD or filename == "MRSAT.RRF":
            file_stats[filename] = copy_filtered_rrf(
                source,
                target,
                attribute_cut=attribute_cut,
            )
        else:
            file_stats[filename] = copy_rrf(source, target)

    file_stats["MRFILES.RRF"] = rewrite_mrfiles(source_meta, out_meta, present_files)

    generated_utc = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, object] = {
        "generated_utc": generated_utc,
        "source_meta": str(source_meta),
        "output_meta": str(out_meta),
        "policy_guide": POLICY_GUIDE,
        "all_active_rrf": all_active_rrf,
        "attribute_cut": attribute_cut,
        "included_rrf_files": sorted(path.name for path in out_meta.glob("*.RRF")),
        "skipped_missing_optional_files": skipped_missing,
        "omitted_rrf_policy": {
            "word_indexes": "MRX*.RRF",
            "mapping_subset_tables": ["MRMAP.RRF", "MRSMAP.RRF"],
            "ambiguous_string_tables": ["AMBIGLUI.RRF", "AMBIGSUI.RRF"],
            "deprecated_tables": ["MRCXT.RRF", "MRHIST.RRF"],
        },
        "row_filter_policy": {
            "MRREL.RRF": [
                "drop SAB values that start with MDR but are not exactly MDR",
                "drop REL=SY rows from SAB=RXNORM",
            ],
            "MRSAT.RRF": [
                "drop SAB values that start with MDR but are not exactly MDR",
                "drop STYPE=RUI relationship attributes",
            ],
            "MRHIER.RRF": [
                "drop SAB values that start with MDR but are not exactly MDR",
            ],
            "attribute_cut_optional": attribute_cut,
        },
        "metadata_policy": {
            "MRCOLS.RRF": "keep rows only for RRF files present in this subset",
            "MRDOC.RRF": "drop ATN SUBSET_MEMBER documentation rows",
            "MRSAB.RRF": "remove SUBSET_MEMBER from source attribute-list fields",
            "MRFILES.RRF": "refresh row counts and byte sizes for included files",
        },
        "files": file_stats,
        "license_note": (
            "This is still UMLS-licensed source data. Include it only in distributions "
            "whose recipients are authorized to receive the corresponding UMLS release."
        ),
    }
    manifest_path = out_meta.parent / "rrf_subset_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a pruned UMLS RRF subset for the licensed search distribution."
    )
    parser.add_argument(
        "--source-meta",
        type=Path,
        required=True,
        help="Local licensed UMLS META directory to copy from.",
    )
    parser.add_argument(
        "--out-meta",
        type=Path,
        default=DEFAULT_OUT_META,
        help="Output META directory. Defaults to build/umls_rrf_subset/META.",
    )
    parser.add_argument("--replace", action="store_true", help="Overwrite an existing output META directory.")
    parser.add_argument(
        "--all-active-rrf",
        action="store_true",
        help="Keep every non-MRX, non-deprecated RRF instead of the default runtime subset.",
    )
    parser.add_argument(
        "--include-rrf",
        action="append",
        default=[],
        help="Additional RRF filename to include when not using --all-active-rrf. Repeat as needed.",
    )
    parser.add_argument(
        "--attribute-cut",
        action="store_true",
        help="Also apply the optional MRSAT attribute cuts from SCRIPT_CUTS.md.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_subset(
        source_meta=args.source_meta,
        out_meta=args.out_meta,
        replace=args.replace,
        all_active_rrf=args.all_active_rrf,
        include_rrf=args.include_rrf,
        attribute_cut=args.attribute_cut,
    )
    print(
        json.dumps(
            {
                "output_meta": manifest["output_meta"],
                "included_rrf_files": manifest["included_rrf_files"],
                "manifest": str(Path(str(manifest["output_meta"])).parent / "rrf_subset_manifest.json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
