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

from qe_evidence_vectors.drug_enrichment import (
    DRUG_MAPPING_SABS,
    OPEN_DRUG_ENRICHMENT_SOURCE_POLICY,
    build_drug_enrichment_documents,
    is_ehr_like_source,
    load_drug_target_specs,
)
from qe_evidence_vectors.embeddings import HashingEmbedder, embed_documents
from qe_evidence_vectors.schema import write_jsonl


DEFAULT_TARGETS = ROOT / "config" / "drug_enrichment_targets.txt"
DEFAULT_CODE_INDEX = ROOT / "build" / "cui_code_index.sqlite"
DEFAULT_OUT_DIR = ROOT / "build" / "drug_enrichment"
DEFAULT_CORPUS_PATHS = [
    ROOT / "build" / "pubmed_scaling_chunk_004_drug_safety_therapeutics_corpus.jsonl",
    ROOT / "build" / "europepmc_scaling_chunk_004_drug_safety_therapeutics_corpus.jsonl",
    ROOT / "build" / "pubmed_biomedicine_expanded_corpus.jsonl",
    ROOT / "build" / "europepmc_biomedicine_expanded_corpus.jsonl",
    ROOT / "build" / "europepmc_biomedicine_topics_corpus.jsonl",
    ROOT / "build" / "pubmed_bulk_recent_1321_1320_corpus.jsonl",
    ROOT / "build" / "pubmed_bulk_recent_1325_1324_corpus.jsonl",
    ROOT / "build" / "pubmed_bulk_recent_1327_1326_corpus.jsonl",
    ROOT / "build" / "pubmed_bulk_recent_1329_1328_corpus.jsonl",
    ROOT / "build" / "pubmed_bulk_recent_1331_1330_corpus.jsonl",
    ROOT / "build" / "pubmed_bulk_recent_next2_corpus.jsonl",
    ROOT
    / "build"
    / "profile_evidence_literature_expanded"
    / "literature_expanded_chemicals_drugs_evidence.jsonl",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build local drug-enrichment concept document and vector shards."
    )
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--code-index", type=Path, default=DEFAULT_CODE_INDEX)
    parser.add_argument("--corpus", type=Path, action="append", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--max-mentions-per-cui", type=int, default=80)
    parser.add_argument("--max-labels", type=int, default=24)
    parser.add_argument("--mapping-sab", action="append", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.targets.exists():
        raise SystemExit(f"missing target CUI file: {args.targets}")
    if not args.code_index.exists():
        raise SystemExit(f"missing code index: {args.code_index}")
    corpus_paths = args.corpus if args.corpus is not None else DEFAULT_CORPUS_PATHS
    existing_corpus_paths = [path for path in corpus_paths if path.exists()]
    excluded_corpus_paths = [path for path in existing_corpus_paths if is_ehr_like_source(path)]
    open_corpus_paths = [path for path in existing_corpus_paths if not is_ehr_like_source(path)]
    if not open_corpus_paths:
        raise SystemExit("no existing corpus paths were found")
    target_specs = load_drug_target_specs(args.targets)
    target_cuis = [spec.cui for spec in target_specs]
    target_aliases_by_cui = {spec.cui: spec.aliases for spec in target_specs}
    documents = build_drug_enrichment_documents(
        target_cuis=target_cuis,
        target_aliases_by_cui=target_aliases_by_cui,
        code_index_path=args.code_index,
        corpus_paths=open_corpus_paths,
        mapping_sabs=args.mapping_sab or DRUG_MAPPING_SABS,
        max_mentions_per_cui=args.max_mentions_per_cui,
        max_labels=args.max_labels,
    )
    vectors = embed_documents(
        documents,
        HashingEmbedder(dim=args.dim),
        include_document_metadata=True,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    docs_path = args.out_dir / "drug_enrichment_concept_documents.jsonl"
    vectors_path = args.out_dir / "drug_enrichment_concept_vectors.hashing.jsonl"
    manifest_path = args.out_dir / "manifest.json"
    write_jsonl(docs_path, documents)
    write_jsonl(vectors_path, vectors)
    manifest = {
        "targets": str(args.targets),
        "target_cuis": target_cuis,
        "code_index": str(args.code_index),
        "mapping_sabs": list(args.mapping_sab or DRUG_MAPPING_SABS),
        "corpus_paths": [str(path) for path in open_corpus_paths],
        "excluded_corpus_paths": [str(path) for path in excluded_corpus_paths],
        "source_policy": OPEN_DRUG_ENRICHMENT_SOURCE_POLICY,
        "documents": str(docs_path),
        "vectors": str(vectors_path),
        "concepts": len(documents),
        "vector_dim": args.dim,
        "source": "local_drug_enrichment",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {len(documents)} drug enrichment document(s) to {docs_path} "
        f"and {len(vectors)} vector(s) to {vectors_path}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
