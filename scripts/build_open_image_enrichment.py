#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.embeddings import HashingEmbedder, embed_documents
from qe_evidence_vectors.open_image_enrichment import (
    DEFAULT_USER_AGENT,
    build_open_image_documents,
    image_targets_from_documents,
    load_image_targets,
    resolve_open_images_for_targets,
)
from qe_evidence_vectors.schema import write_jsonl


DEFAULT_OUT_DIR = ROOT / "build" / "open_image_enrichment"
DEFAULT_TARGETS = ROOT / "config" / "open_image_enrichment_seed_targets.txt"
DEFAULT_DOC_PATHS = [
    ROOT / "build" / "public" / "public_concept_documents.jsonl",
    ROOT / "build" / "scaling_chunk_001_gap_topics_concept_documents.jsonl",
    ROOT / "build" / "scaling_chunk_002_common_clinical_concept_documents.jsonl",
    ROOT / "build" / "scaling_chunk_003_abbreviation_language_concept_documents.jsonl",
    ROOT / "build" / "scaling_chunk_004_drug_safety_therapeutics_concept_documents.jsonl",
    ROOT / "build" / "scaling_chunk_005_diagnostics_procedures_devices_concept_documents.jsonl",
    ROOT
    / "build"
    / "new_umls_iterations"
    / "iteration_002_existing_data"
    / "extension_concept_documents.cumulative.jsonl",
    ROOT / "build" / "wikipedia_enrichment" / "wikipedia_concept_documents.jsonl",
    ROOT / "build" / "drug_enrichment" / "drug_enrichment_concept_documents.jsonl",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build open-license image metadata concept documents from Wikidata P2892/P18 "
            "and strict Wikimedia Commons search fallback."
        )
    )
    parser.add_argument("--targets", type=Path, default=None)
    parser.add_argument("--docs", type=Path, nargs="+", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--limit", type=int, default=250, help="0 means no limit")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=80)
    parser.add_argument("--max-images-per-cui", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.78)
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--no-commons-search-fallback", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets_path = args.targets
    if targets_path:
        targets = load_image_targets(targets_path)
        if args.offset:
            targets = targets[args.offset :]
        if args.limit:
            targets = targets[: args.limit]
    else:
        doc_paths = args.docs or [path for path in DEFAULT_DOC_PATHS if path.exists()]
        if not doc_paths:
            raise SystemExit("no target file or concept document paths were found")
        targets = image_targets_from_documents(
            doc_paths,
            limit=args.limit,
            offset=args.offset,
        )
    if not targets:
        raise SystemExit("no image targets found")

    images_by_cui = resolve_open_images_for_targets(
        targets,
        batch_size=args.batch_size,
        max_images_per_cui=args.max_images_per_cui,
        min_score=args.min_score,
        commons_search_fallback=not args.no_commons_search_fallback,
        sleep_seconds=args.sleep_seconds,
        user_agent=args.user_agent,
    )
    documents = build_open_image_documents(
        targets,
        images_by_cui=images_by_cui,
        max_images_per_cui=args.max_images_per_cui,
    )
    vectors = embed_documents(
        documents,
        HashingEmbedder(dim=args.dim),
        include_document_metadata=True,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    docs_path = args.out_dir / "open_image_concept_documents.jsonl"
    vectors_path = args.out_dir / "open_image_concept_vectors.hashing.jsonl"
    manifest_path = args.out_dir / "manifest.json"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, vectors)
    manifest = {
        "targets": str(targets_path) if targets_path else "",
        "doc_paths": [str(path) for path in (args.docs or DEFAULT_DOC_PATHS) if Path(path).exists()],
        "documents": str(docs_path),
        "vectors": str(vectors_path),
        "target_count": len(targets),
        "concepts_with_images": len(documents),
        "images": sum(len(document.metadata.get("images") or []) for document in documents),
        "vector_dim": args.dim,
        "source": "wikimedia_open_images",
        "wikidata_property": "P2892",
        "image_property": "P18",
        "commons_search_fallback": not args.no_commons_search_fallback,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(documents)} open image document(s) with "
        f"{manifest['images']} image(s) to {docs_path} and {len(vectors)} vector(s) to {vectors_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
