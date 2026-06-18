#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LEVEL_ZERO_VECTOR_STEMS = [
    "scaling_chunk_001_gap_topics",
    "scaling_chunk_002_common_clinical",
    "scaling_chunk_003_abbreviation_language",
    "scaling_chunk_004_drug_safety_therapeutics",
    "scaling_chunk_005_diagnostics_procedures_devices",
]

FULL_VECTOR_STEMS = [
    "scaling_chunk_001_gap_topics",
    "scaling_chunk_002_common_clinical",
    "scaling_chunk_003_abbreviation_language",
    "scaling_chunk_004_drug_safety_therapeutics",
    "scaling_chunk_005_diagnostics_procedures_devices",
    "pubmed_bulk_recent_baseline",
    "pubmed_bulk_recent_next2",
    "pubmed_bulk_recent_1331_1330",
    "pubmed_bulk_recent_1329_1328",
    "pubmed_bulk_recent_1327_1326",
    "pubmed_bulk_recent_1325_1324",
    "pubmed_bulk_recent_1323_1322",
    "pubmed_bulk_recent_1321_1320",
]

PROFILE_ALIASES = {
    "full": "full",
    "public-slim": "public-slim",
    "level-zero": "level-zero",
    "level-0": "level-zero",
    "category-zero": "level-zero",
    "category-0": "level-zero",
}

PROFILE_CHOICES = tuple(PROFILE_ALIASES)

REQUIRED_INDEXES = [
    "search_quality_provenance.sqlite",
    "umls_biomedicine_search_label_index.sqlite",
    "umls_semantic_types.sqlite",
    "umls_related_concepts.sqlite",
    "umls_definitions.sqlite",
    "umls_research_relations.sqlite",
    "relationship_edges.sqlite",
]

FULL_PROFILE_CODE_INDEXES = [
    "cui_code_index.runtime.sqlite",
]

ELASTICSEARCH_SNAPSHOT_DIR = "elasticsearch_snapshots/qe-public-search-sapbert"

PRUNED_RRF_SUBSET_FILES = [
    "umls_rrf_subset/rrf_subset_manifest.json",
    "umls_rrf_subset/META/MRCONSO.RRF",
    "umls_rrf_subset/META/MRSTY.RRF",
    "umls_rrf_subset/META/MRREL.RRF",
    "umls_rrf_subset/META/MRDEF.RRF",
    "umls_rrf_subset/META/MRSAB.RRF",
    "umls_rrf_subset/META/MRHIER.RRF",
    "umls_rrf_subset/META/MRSAT.RRF",
    "umls_rrf_subset/META/MRFILES.RRF",
    "umls_rrf_subset/META/MRCOLS.RRF",
]

SAPBERT_MODEL_FILES = [
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "vocab.txt",
]


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[install {timestamp}] {message}", flush=True)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_profile(profile: str) -> str:
    normalized = PROFILE_ALIASES.get(str(profile or "").strip().lower())
    if not normalized:
        choices = ", ".join(PROFILE_CHOICES)
        raise SystemExit(f"Unknown PUBLIC_SEARCH_PAYLOAD_PROFILE {profile!r}; expected one of: {choices}")
    return normalized


def profile_vector_stems(profile: str) -> list[str]:
    if normalize_profile(profile) == "level-zero":
        return list(LEVEL_ZERO_VECTOR_STEMS)
    return list(FULL_VECTOR_STEMS)


def vector_present(build_dir: Path, stem: str) -> bool:
    compact_dir = build_dir / "compact_vectors"
    compact = compact_dir / f"{stem}_sapbert_cls.manifest.json"
    compact_vectors = compact_dir / f"{stem}_sapbert_cls.vectors.f32"
    compact_metadata = compact_dir / f"{stem}_sapbert_cls.metadata.jsonl.gz"
    return compact.exists() and compact_vectors.exists() and compact_metadata.exists()


def document_present(build_dir: Path, stem: str) -> bool:
    jsonl = build_dir / f"{stem}_concept_documents.jsonl"
    return Path(f"{jsonl}.gz").exists()


def code_index_present(build_dir: Path) -> bool:
    return any((build_dir / name).exists() for name in FULL_PROFILE_CODE_INDEXES)


def sapbert_model_present(build_dir: Path) -> bool:
    model_dir = build_dir / "models" / "sapbert"
    return all((model_dir / name).exists() for name in SAPBERT_MODEL_FILES)


def elasticsearch_snapshot_present(build_dir: Path) -> bool:
    snapshot_dir = build_dir / ELASTICSEARCH_SNAPSHOT_DIR
    return snapshot_dir.is_dir() and any(path.is_file() for path in snapshot_dir.rglob("*"))


def compact_vector_stem(path: Path) -> str | None:
    name = path.name
    for suffix in (
        "_sapbert_cls.manifest.json",
        "_sapbert_cls.vectors.f32",
        "_sapbert_cls.metadata.jsonl.gz",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def concept_document_stem(path: Path) -> str | None:
    name = path.name
    for suffix in ("_concept_documents.jsonl.gz", "_concept_documents.jsonl"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def unexpected_runtime_files(build_dir: Path, *, profile: str) -> list[str]:
    profile = normalize_profile(profile)
    if profile != "level-zero":
        return []

    allowed_stems = set(LEVEL_ZERO_VECTOR_STEMS)
    unexpected: list[str] = []
    compact_dir = build_dir / "compact_vectors"
    if compact_dir.exists():
        for path in sorted(compact_dir.glob("*_sapbert_cls.*")):
            stem = compact_vector_stem(path)
            if stem and stem not in allowed_stems:
                unexpected.append(str(path.relative_to(build_dir)))
    for path in sorted(build_dir.glob("*_concept_documents.jsonl*")):
        stem = concept_document_stem(path)
        if stem and stem not in allowed_stems:
            unexpected.append(str(path.relative_to(build_dir)))
    for path in sorted(build_dir.glob("cui_code_index.runtime.sqlite*")):
        unexpected.append(str(path.relative_to(build_dir)))
    if (build_dir / "umls_rrf_subset").exists():
        unexpected.append("umls_rrf_subset/")
    full_snapshot = build_dir / ELASTICSEARCH_SNAPSHOT_DIR
    if full_snapshot.exists():
        unexpected.append(f"{ELASTICSEARCH_SNAPSHOT_DIR}/")
    return unexpected


def missing_runtime_files(build_dir: Path, *, profile: str) -> list[str]:
    profile = normalize_profile(profile)
    missing: list[str] = []
    for stem in profile_vector_stems(profile):
        if not vector_present(build_dir, stem):
            missing.append(f"compact_vectors/{stem}_sapbert_cls.manifest.json")
        if not document_present(build_dir, stem):
            missing.append(f"{stem}_concept_documents.jsonl.gz")
    for name in REQUIRED_INDEXES:
        path = build_dir / name
        if not path.exists():
            missing.append(name)
    if not sapbert_model_present(build_dir):
        missing.append("models/sapbert/{config.json,model.safetensors,tokenizer_config.json,special_tokens_map.json,vocab.txt}")
    if profile != "level-zero" and not elasticsearch_snapshot_present(build_dir):
        missing.append(f"{ELASTICSEARCH_SNAPSHOT_DIR}/{{packaged search database files}}")
    if profile == "full" and not code_index_present(build_dir):
        missing.append("cui_code_index.runtime.sqlite")
    if profile == "full":
        for name in PRUNED_RRF_SUBSET_FILES:
            if not (build_dir / name).exists():
                missing.append(name)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the public search data files are present under build/."
    )
    parser.add_argument(
        "--build-dir",
        type=Path,
        default=Path(os.environ.get("PUBLIC_SEARCH_PAYLOAD_BUILD_DIR", ROOT / "build")),
        help="Directory that should contain the packaged search data files.",
    )
    parser.add_argument(
        "--repo-id",
        default=os.environ.get("PUBLIC_SEARCH_PAYLOAD_REPO", ""),
        help="Optional Hugging Face dataset repo id containing the packaged search data files.",
    )
    parser.add_argument(
        "--repo-type",
        default=os.environ.get("PUBLIC_SEARCH_PAYLOAD_REPO_TYPE", "dataset"),
        help="Hugging Face repo type for --repo-id.",
    )
    parser.add_argument(
        "--profile",
        choices=PROFILE_CHOICES,
        default=os.environ.get("PUBLIC_SEARCH_PAYLOAD_PROFILE", "full"),
        help=(
            "Search data profile. level-zero/category-zero uses the curated level-zero shard set; "
            "public-slim omits the CUI/code resolver and raw RRF subset; full requires the "
            "compact runtime resolver and raw RRF subset."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=truthy(os.environ.get("PUBLIC_SEARCH_PAYLOAD_OFFLINE"))
        or truthy(os.environ.get("HF_HUB_OFFLINE")),
        help="Only verify that the payload is already present.",
    )
    parser.add_argument(
        "--strict-profile",
        action="store_true",
        default=truthy(os.environ.get("PUBLIC_SEARCH_PAYLOAD_STRICT_PROFILE")),
        help="Fail if profile-incompatible payload files are present.",
    )
    args = parser.parse_args()

    build_dir = args.build_dir.expanduser()
    profile = normalize_profile(args.profile)
    unexpected = unexpected_runtime_files(build_dir, profile=profile) if args.strict_profile else []
    if unexpected:
        preview = ", ".join(unexpected[:5])
        if len(unexpected) > 5:
            preview += f", ... ({len(unexpected)} unexpected)"
        raise SystemExit(
            f"Search data contains files that do not belong in the {profile} release: {preview}"
        )

    missing = missing_runtime_files(build_dir, profile=profile)
    if not missing:
        log(f"Search data files found in {build_dir}; continuing.")
        return 0

    if args.offline or not args.repo_id:
        preview = ", ".join(missing[:5])
        if len(missing) > 5:
            preview += f", ... ({len(missing)} missing)"
        log(
            f"Search data is missing {len(missing)} required file(s), "
            "but no download repo is configured."
        )
        raise SystemExit(
            "Search data files are incomplete and no download location is configured. "
            f"Missing: {preview}"
        )

    try:
        from huggingface_hub import snapshot_download
    except Exception as exc:
        raise SystemExit(
            "huggingface-hub is required to download the public search data files"
        ) from exc

    log(
        f"Search data is missing {len(missing)} required file(s); "
        f"downloading packaged search files from {args.repo_type} repo {args.repo_id!r}. "
        "This can take a while the first time, but it avoids rebuilding the data on this computer."
    )
    build_dir.mkdir(parents=True, exist_ok=True)
    allow_patterns = [
        "search_quality_provenance.sqlite",
        "umls_biomedicine_search_label_index.sqlite",
        "umls_semantic_types.sqlite",
        "umls_related_concepts.sqlite",
        "umls_definitions.sqlite",
        "umls_research_relations.sqlite",
        "relationship_edges.sqlite",
        "release_manifest.json",
        "runtime_payload_manifest.json",
        "models/sapbert/*",
    ]
    if profile != "level-zero":
        allow_patterns.append("elasticsearch_snapshots/**")
    for stem in profile_vector_stems(profile):
        allow_patterns.extend(
            [
                f"compact_vectors/{stem}_sapbert_cls.manifest.json",
                f"compact_vectors/{stem}_sapbert_cls.vectors.f32",
                f"compact_vectors/{stem}_sapbert_cls.metadata.jsonl.gz",
                f"{stem}_concept_documents.jsonl.gz",
            ]
        )
    if profile == "full":
        allow_patterns.extend(FULL_PROFILE_CODE_INDEXES)
        allow_patterns.extend(
            [
                "umls_rrf_subset/rrf_subset_manifest.json",
                "umls_rrf_subset/META/*.RRF",
            ]
        )

    snapshot_download(
        repo_id=args.repo_id,
        repo_type=args.repo_type,
        local_dir=build_dir,
        allow_patterns=allow_patterns,
    )

    log("Search data download finished; checking that all required files are present.")
    unexpected = unexpected_runtime_files(build_dir, profile=profile) if args.strict_profile else []
    if unexpected:
        preview = ", ".join(unexpected[:5])
        if len(unexpected) > 5:
            preview += f", ... ({len(unexpected)} unexpected)"
        raise SystemExit(
            f"Search data download finished but files that do not belong in the {profile} release are present: {preview}"
        )
    missing = missing_runtime_files(build_dir, profile=profile)
    if missing:
        preview = ", ".join(missing[:5])
        if len(missing) > 5:
            preview += f", ... ({len(missing)} missing)"
        raise SystemExit(f"Search data download finished but required files are still missing: {preview}")

    log(f"Search data files are ready in {build_dir}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
