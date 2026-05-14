#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


DEFAULT_ARTIFACTS = [
    ("docs", "build/public/public_concept_documents.jsonl", "public_generated", "Public rebuild concept documents generated from public corpora and locally licensed vocabulary files."),
    ("vectors", "build/public/public_concept_vectors.hashing.jsonl", "public_generated", "Public rebuild hashing vectors paired with the public concept documents."),
    ("extension_docs", "build/new_umls_iterations/iteration_002_existing_data/extension_concept_documents.cumulative.jsonl", "local_generated", "Locally generated NEW####### extension concept documents."),
    ("extension_vectors", "build/new_umls_iterations/iteration_002_existing_data/extension_concept_vectors.cumulative.hashing.jsonl", "local_generated", "Locally generated extension concept vectors."),
    ("wikipedia_docs", "build/wikipedia_enrichment/wikipedia_concept_documents.jsonl", "public_generated", "Wikipedia-derived enrichment documents."),
    ("wikipedia_vectors", "build/wikipedia_enrichment/wikipedia_concept_vectors.hashing.jsonl", "public_generated", "Wikipedia-derived enrichment vectors."),
    ("drug_docs", "build/drug_enrichment/drug_enrichment_concept_documents.jsonl", "public_generated", "Open drug enrichment documents."),
    ("drug_vectors", "build/drug_enrichment/drug_enrichment_concept_vectors.hashing.jsonl", "public_generated", "Open drug enrichment vectors."),
    ("open_image_docs", "build/open_image_enrichment/open_image_concept_documents.jsonl", "public_generated", "Open image enrichment documents."),
    ("open_image_vectors", "build/open_image_enrichment/open_image_concept_vectors.hashing.jsonl", "public_generated", "Open image enrichment vectors."),
    ("openalex_docs", "build/openalex_cited_evidence/openalex_top_cited_concept_documents.jsonl", "public_generated", "OpenAlex top-cited evidence documents."),
    ("openalex_vectors", "build/openalex_cited_evidence/openalex_top_cited_concept_vectors.hashing.jsonl", "public_generated", "OpenAlex top-cited evidence vectors."),
    ("permitted_source_docs", "build/public/permitted_sources_concept_documents.jsonl", "public_generated", "Bounded ClinicalTrials.gov, MedlinePlus, MedlinePlus Genetics, DailyMed, Bookshelf OA, reusable reference-page, and OBO ontology concept documents."),
    ("permitted_source_vectors", "build/public/permitted_sources_concept_vectors.hashing.jsonl", "public_generated", "Hashing vectors for bounded permitted public source documents."),
    ("label_index", "build/umls_biomedicine_search_label_index.sqlite", "licensed_generated", "UMLS-derived label fallback index. Requires a local UMLS release."),
    ("code_index", "build/cui_code_index.sqlite", "licensed_generated", "UMLS-derived CUI/code resolver index. Requires a local UMLS release."),
    ("semantic_type_index", "build/umls_semantic_types.sqlite", "licensed_generated", "UMLS MRSTY-derived semantic type index. Requires a local UMLS release."),
    ("relation_index", "build/umls_related_concepts.sqlite", "licensed_generated", "UMLS MRREL-derived related concept index. Requires a local UMLS release."),
    ("research_relation_index", "build/umls_research_relations.sqlite", "licensed_generated", "UMLS MRREL/MRSTY-derived cross-semantic relation index. Requires a local UMLS release."),
    ("relationship_edge_index", "build/relationship_edges.sqlite", "public_or_local_generated", "Mined universal relationship edge index. Inputs determine redistributability."),
    ("definition_index", "build/umls_definitions.sqlite", "licensed_generated", "UMLS MRDEF-derived definition index. Requires a local UMLS release."),
    ("external_cui_vector_index", "build/external_cui_vector_neighbors.sqlite", "third_party_generated", "External CUI vector nearest-neighbor index; redistribution depends on source embedding licenses."),
    ("hpo_obo", "data/external/hpo/hp.obo", "public_external", "HPO ontology file used for phenotype labels and UMLS xrefs."),
    ("hpo_phenotype_annotations", "data/external/hpo/phenotype.hpoa", "public_external_with_source_caveats", "HPO disease-phenotype annotation file used for opt-in research-relation augmentation."),
    ("hpo_genes_to_phenotype", "data/external/hpo/genes_to_phenotype.txt", "public_external_with_source_caveats", "HPO gene-phenotype annotation file used for opt-in research-relation augmentation."),
    ("active_label_supplement", "config/active_label_supplement.tsv", "repo_config", "Curated active label supplement checked into the repo."),
    ("paragraph_queries", "config/search_quality_paragraph_queries.tsv", "repo_config", "Paragraph benchmark queries checked into the repo."),
    ("acceptable_alternatives", "config/search_quality_acceptable_cui_alternatives.tsv", "repo_config", "Acceptable benchmark alternatives checked into the repo."),
    ("useful_extra_cuis", "config/search_quality_useful_extra_cuis.tsv", "repo_config", "Useful extra CUI audit calibration checked into the repo."),
]


UMLS_META_FILES = [
    ("umls_mrconso", "MRCONSO.RRF", "umls_license", "UMLS concept names and source atoms."),
    ("umls_mrsty", "MRSTY.RRF", "umls_license", "UMLS semantic type assignments."),
    ("umls_mrrel", "MRREL.RRF", "umls_license", "UMLS source and Metathesaurus relationships."),
    ("umls_mrdef", "MRDEF.RRF", "umls_license", "UMLS concept definitions."),
    ("umls_mrsab", "MRSAB.RRF", "umls_license", "UMLS source metadata, including restriction levels."),
]


LOINC_RELATIVE_FILES = [
    ("loinc_table", "LoincTable/Loinc.csv", "loinc_terms", "LOINC observation table."),
    ("loinc_part", "AccessoryFiles/PartFile/Part.csv", "loinc_terms", "LOINC part table."),
    (
        "loinc_part_link",
        "AccessoryFiles/PartFile/LoincPartLink_Primary.csv",
        "loinc_terms",
        "LOINC term-to-part links.",
    ),
    (
        "loinc_group",
        "AccessoryFiles/GroupFile/Group.csv",
        "loinc_terms",
        "LOINC group metadata when present in the local release.",
    ),
]


def sha256_file(path: Path, *, max_bytes: int | None) -> str:
    hasher = hashlib.sha256()
    remaining = max_bytes
    with path.open("rb") as handle:
        while True:
            chunk_size = 1024 * 1024
            if remaining is not None:
                if remaining <= 0:
                    break
                chunk_size = min(chunk_size, remaining)
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            if remaining is not None:
                remaining -= len(chunk)
    return hasher.hexdigest()


def artifact_row(
    name: str,
    relative_path: str,
    license_class: str,
    note: str,
    *,
    hash_small_files: bool,
    full_hash: bool,
    small_file_limit: int,
) -> dict:
    path = ROOT / relative_path
    exists = path.exists()
    row = {
        "name": name,
        "path": relative_path,
        "exists": exists,
        "license_class": license_class,
        "note": note,
    }
    if not exists:
        return row
    stat = path.stat()
    row["bytes"] = stat.st_size
    row["modified_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    if full_hash:
        row["sha256"] = sha256_file(path, max_bytes=None)
        row["hash"] = "sha256"
    elif hash_small_files and stat.st_size <= small_file_limit:
        row["sha256"] = sha256_file(path, max_bytes=None)
        row["hash"] = "sha256"
    else:
        row["hash"] = "skipped"
    return row


def source_input_row(
    name: str,
    path: Path,
    license_class: str,
    note: str,
    *,
    hash_small_files: bool,
    full_hash: bool,
    small_file_limit: int,
) -> dict:
    path = path.expanduser()
    if not path.is_absolute():
        path = ROOT / path
    try:
        relative_path = str(path.relative_to(ROOT))
    except ValueError:
        relative_path = str(path)
    return artifact_row(
        name,
        relative_path,
        license_class,
        note,
        hash_small_files=hash_small_files,
        full_hash=full_hash,
        small_file_limit=small_file_limit,
    )


def directory_row(name: str, path: Path, license_class: str, note: str) -> dict:
    path = path.expanduser()
    if not path.is_absolute():
        path = ROOT / path
    try:
        relative_path = str(path.relative_to(ROOT))
    except ValueError:
        relative_path = str(path)
    row = {
        "name": name,
        "path": relative_path,
        "exists": path.exists(),
        "license_class": license_class,
        "note": note,
    }
    if path.exists():
        row["kind"] = "directory" if path.is_dir() else "file"
        if path.is_dir():
            row["immediate_entries"] = len(list(path.iterdir()))
        else:
            stat = path.stat()
            row["bytes"] = stat.st_size
            row["modified_utc"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    return row


def source_input_rows(args: argparse.Namespace) -> list[dict]:
    rows: list[dict] = []
    if args.umls_meta:
        rows.append(
            directory_row(
                "umls_meta_dir",
                args.umls_meta,
                "umls_license",
                "Local UMLS META directory. Do not redistribute raw files without license permission.",
            )
        )
        for name, filename, license_class, note in UMLS_META_FILES:
            rows.append(
                source_input_row(
                    name,
                    args.umls_meta / filename,
                    license_class,
                    note,
                    hash_small_files=args.hash_small_files,
                    full_hash=args.full_hash,
                    small_file_limit=args.small_file_limit,
                )
            )
    if args.loinc_dir:
        rows.append(
            directory_row(
                "loinc_dir",
                args.loinc_dir,
                "loinc_terms",
                "Local LOINC release directory. Redistribution depends on LOINC terms.",
            )
        )
        for name, relative_path, license_class, note in LOINC_RELATIVE_FILES:
            rows.append(
                source_input_row(
                    name,
                    args.loinc_dir / relative_path,
                    license_class,
                    note,
                    hash_small_files=args.hash_small_files,
                    full_hash=args.full_hash,
                    small_file_limit=args.small_file_limit,
                )
            )
    for index, snomed_zip in enumerate(args.snomed_zip or [], start=1):
        rows.append(
            source_input_row(
                f"snomed_release_zip_{index}",
                snomed_zip,
                "snomed_license",
                "Local SNOMED CT release archive. Redistribution depends on deployment/license terms.",
                hash_small_files=args.hash_small_files,
                full_hash=args.full_hash,
                small_file_limit=args.small_file_limit,
            )
        )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a reproducibility manifest for local search artifacts.")
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "reproducibility_manifest.json")
    parser.add_argument(
        "--umls-meta",
        type=Path,
        help="Optional local UMLS META directory containing MRCONSO.RRF, MRSTY.RRF, MRREL.RRF, MRDEF.RRF, and MRSAB.RRF.",
    )
    parser.add_argument(
        "--loinc-dir",
        type=Path,
        default=ROOT / "Loinc_2.82" if (ROOT / "Loinc_2.82").exists() else None,
        help="Optional local LOINC release directory. Defaults to ./Loinc_2.82 when present.",
    )
    parser.add_argument(
        "--snomed-zip",
        type=Path,
        action="append",
        default=None,
        help="Optional local SNOMED CT release archive. Repeat for multiple archives.",
    )
    parser.add_argument("--hash-small-files", action="store_true", help="SHA-256 hash files up to --small-file-limit bytes.")
    parser.add_argument("--small-file-limit", type=int, default=10_000_000)
    parser.add_argument("--full-hash", action="store_true", help="Hash every listed artifact, including large generated files.")
    args = parser.parse_args()
    if args.snomed_zip is None:
        args.snomed_zip = sorted(ROOT.glob("SnomedCT_*.zip"))
    return args


def main() -> int:
    args = parse_args()
    source_inputs = source_input_rows(args)
    artifacts = [
        artifact_row(
            name,
            relative_path,
            license_class,
            note,
            hash_small_files=args.hash_small_files,
            full_hash=args.full_hash,
            small_file_limit=args.small_file_limit,
        )
        for name, relative_path, license_class, note in DEFAULT_ARTIFACTS
    ]
    manifest = {
        "schema": "query-expansion-reproducibility-manifest-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        },
        "hash_policy": (
            "full_hash"
            if args.full_hash
            else ("small_files" if args.hash_small_files else "sizes_and_timestamps_only")
        ),
        "source_inputs": source_inputs,
        "artifacts": artifacts,
        "summary": {
            "listed": len(artifacts),
            "present": sum(1 for item in artifacts if item.get("exists")),
            "missing": sum(1 for item in artifacts if not item.get("exists")),
            "bytes_present": sum(int(item.get("bytes") or 0) for item in artifacts),
            "source_inputs_listed": len(source_inputs),
            "source_inputs_present": sum(1 for item in source_inputs if item.get("exists")),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
