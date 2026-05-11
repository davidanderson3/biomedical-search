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
from qe_evidence_vectors.schema import write_jsonl
from qe_evidence_vectors.wikipedia_enrichment import (
    build_wikipedia_documents,
    load_wikipedia_specs,
)

DEFAULT_CONFIG = ROOT / "config" / "wikipedia_concept_enrichment.json"
DEFAULT_OUT_DIR = ROOT / "build" / "wikipedia_enrichment"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build local Wikipedia-backed concept document and vector shards."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--dim", type=int, default=384)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = load_wikipedia_specs(args.config)
    documents = build_wikipedia_documents(specs)
    vectors = embed_documents(
        documents,
        HashingEmbedder(dim=args.dim),
        include_document_metadata=True,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    docs_path = args.out_dir / "wikipedia_concept_documents.jsonl"
    vectors_path = args.out_dir / "wikipedia_concept_vectors.hashing.jsonl"
    manifest_path = args.out_dir / "manifest.json"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, vectors)
    manifest = {
        "config": str(args.config),
        "documents": str(docs_path),
        "vectors": str(vectors_path),
        "concepts": len(documents),
        "vector_dim": args.dim,
        "source": "wikipedia",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(documents)} Wikipedia concept document(s) to {docs_path} "
        f"and {len(vectors)} vector(s) to {vectors_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
