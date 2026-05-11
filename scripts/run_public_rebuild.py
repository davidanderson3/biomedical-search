#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOPICS = ROOT / "config" / "pubmed_biomedicine_topics.tsv"
DEFAULT_ACTIVE_LABEL_SUPPLEMENT = ROOT / "config" / "active_label_supplement.tsv"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def resolve_path(path: Path) -> Path:
    path = path.expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def command_string(command: list[str]) -> str:
    return shlex.join(command)


def run_command(command: list[str], *, dry_run: bool) -> None:
    print(command_string(command), flush=True)
    if dry_run:
        return
    subprocess.run(command, cwd=ROOT, check=True)


def write_text(path: Path, text: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def require_file(path: Path, label: str, *, dry_run: bool) -> None:
    if dry_run:
        return
    if not path.exists():
        raise SystemExit(f"missing {label}: {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the public-first reproducible rebuild using public corpora and "
            "locally licensed UMLS files. Does not use MIMIC or other EHR data."
        )
    )
    parser.add_argument(
        "--umls-meta",
        type=Path,
        required=True,
        help="Local UMLS META directory containing MRCONSO.RRF, MRSTY.RRF, MRREL.RRF, MRDEF.RRF, and MRSAB.RRF.",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "build" / "public")
    parser.add_argument("--index-dir", type=Path, help="SQLite index output directory. Defaults to <out-dir>/indexes.")
    parser.add_argument("--topics", type=Path, default=DEFAULT_TOPICS)
    parser.add_argument("--python", default=sys.executable, help="Python executable used for child commands.")
    parser.add_argument("--pubmed-retmax", type=int, default=500)
    parser.add_argument("--europepmc-max-records", type=int, default=500)
    parser.add_argument("--pmc-max-records", type=int, default=200)
    parser.add_argument("--pmc-max-chars", type=int, help="Optional character cap per PMC OA full-text article.")
    parser.add_argument("--email", help="Optional NCBI contact email metadata.")
    parser.add_argument("--tool", default="query_expansion_public_rebuild")
    parser.add_argument("--matcher", choices=["sqlite", "trie"], default="sqlite")
    parser.add_argument("--max-docs", type=int, help="Optional corpus document cap for smoke builds.")
    parser.add_argument("--provider", choices=["hashing", "sentence-transformers", "transformers-cls", "bert-cls", "sapbert"], default="hashing")
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--top-k", type=int, default=60)
    parser.add_argument("--loinc-dir", type=Path, help="Optional LOINC release path to include in the manifest.")
    parser.add_argument(
        "--snomed-zip",
        type=Path,
        action="append",
        default=[],
        help="Optional SNOMED release archive to include in the manifest. Repeat as needed.",
    )
    parser.add_argument("--skip-fetch", action="store_true", help="Reuse already fetched public corpus files.")
    parser.add_argument("--skip-evaluation", action="store_true", help="Build artifacts but skip paragraph quality evaluation and audit.")
    parser.add_argument("--no-hash-small-files", action="store_true", help="Do not hash small files in the final manifest.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them.")
    return parser.parse_args()


def public_rebuild_commands(args: argparse.Namespace) -> tuple[list[list[str]], dict[str, Path]]:
    umls_meta = resolve_path(args.umls_meta)
    out_dir = resolve_path(args.out_dir)
    index_dir = resolve_path(args.index_dir) if args.index_dir else out_dir / "indexes"
    topics = resolve_path(args.topics)
    mrconso = umls_meta / "MRCONSO.RRF"
    mrsty = umls_meta / "MRSTY.RRF"
    mrrel = umls_meta / "MRREL.RRF"
    mrdef = umls_meta / "MRDEF.RRF"
    provider_key = args.provider.replace("-", "_")

    paths = {
        "umls_meta": umls_meta,
        "topics": topics,
        "pubmed_corpus": out_dir / "pubmed_topics_corpus.jsonl",
        "europepmc_corpus": out_dir / "europepmc_topics_corpus.jsonl",
        "pmc_oa_corpus": out_dir / "pmc_oa_topics_corpus.jsonl",
        "label_index": index_dir / "umls_biomedicine_search_label_index.sqlite",
        "code_index": index_dir / "cui_code_index.sqlite",
        "semantic_type_index": index_dir / "umls_semantic_types.sqlite",
        "evidence": out_dir / "public_corpus_evidence.jsonl",
        "docs_sqlite": out_dir / "public_docs.sqlite",
        "docs": out_dir / "public_concept_documents.jsonl",
        "vectors": out_dir / f"public_concept_vectors.{provider_key}.jsonl",
        "provenance_index": index_dir / "search_quality_provenance.sqlite",
        "relation_index": index_dir / "umls_related_concepts.sqlite",
        "research_relation_index": index_dir / "umls_research_relations.sqlite",
        "definition_index": index_dir / "umls_definitions.sqlite",
        "eval_dir": out_dir / "paragraph_quality_eval",
        "manifest": out_dir / "reproducibility_manifest.json",
        "commands": out_dir / "rebuild_commands.json",
        "server_command": out_dir / "server_command.txt",
    }

    commands: list[list[str]] = []
    if not args.skip_fetch:
        pubmed = [
            args.python,
            "scripts/evidence_vectors.py",
            "fetch-pubmed-topics",
            "--topics",
            rel(topics),
            "--retmax",
            str(args.pubmed_retmax),
            "--out",
            rel(paths["pubmed_corpus"]),
            "--tool",
            args.tool,
        ]
        europepmc = [
            args.python,
            "scripts/evidence_vectors.py",
            "fetch-europepmc-topics",
            "--topics",
            rel(topics),
            "--max-records",
            str(args.europepmc_max_records),
            "--out",
            rel(paths["europepmc_corpus"]),
        ]
        pmc = [
            args.python,
            "scripts/evidence_vectors.py",
            "fetch-pmc-oa-topics",
            "--topics",
            rel(topics),
            "--max-records",
            str(args.pmc_max_records),
            "--out",
            rel(paths["pmc_oa_corpus"]),
            "--tool",
            args.tool,
        ]
        if args.email:
            pubmed.extend(["--email", args.email])
            pmc.extend(["--email", args.email])
        if args.pmc_max_chars:
            pmc.extend(["--max-chars", str(args.pmc_max_chars)])
        commands.extend([pubmed, europepmc, pmc])

    commands.extend(
        [
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-label-index",
                "--mrconso",
                str(mrconso),
                "--mrsty",
                str(mrsty),
                "--profile",
                "biomedicine",
                "--out",
                rel(paths["label_index"]),
                "--replace",
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-code-index",
                "--mrconso",
                str(mrconso),
                "--out",
                rel(paths["code_index"]),
                "--replace",
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-semantic-type-index",
                "--mrsty",
                str(mrsty),
                "--out",
                rel(paths["semantic_type_index"]),
                "--replace",
            ],
        ]
    )

    link = [
        args.python,
        "scripts/evidence_vectors.py",
        "link-corpus",
        "--corpus",
        rel(paths["pubmed_corpus"]),
        rel(paths["europepmc_corpus"]),
        rel(paths["pmc_oa_corpus"]),
        "--label-index",
        rel(paths["label_index"]),
        "--out",
        rel(paths["evidence"]),
        "--matcher",
        args.matcher,
    ]
    if args.max_docs:
        link.extend(["--max-docs", str(args.max_docs)])
    commands.append(link)

    commands.extend(
        [
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-docs-sqlite",
                "--evidence",
                rel(paths["evidence"]),
                "--sqlite",
                rel(paths["docs_sqlite"]),
                "--mrconso",
                str(mrconso),
                "--out",
                rel(paths["docs"]),
                "--replace",
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "embed",
                "--docs",
                rel(paths["docs"]),
                "--out",
                rel(paths["vectors"]),
                "--provider",
                args.provider,
                "--dim",
                str(args.dim),
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-provenance-index",
                "--evidence",
                rel(paths["evidence"]),
                "--docs",
                rel(paths["docs"]),
                "--sqlite",
                rel(paths["provenance_index"]),
                "--replace",
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-relation-index",
                "--mrrel",
                str(mrrel),
                "--mrconso",
                str(mrconso),
                "--docs",
                rel(paths["docs"]),
                "--out",
                rel(paths["relation_index"]),
                "--replace",
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-research-relation-index",
                "--mrrel",
                str(mrrel),
                "--mrconso",
                str(mrconso),
                "--mrsty",
                str(mrsty),
                "--docs",
                rel(paths["docs"]),
                "--out",
                rel(paths["research_relation_index"]),
                "--replace",
            ],
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-definition-index",
                "--mrdef",
                str(mrdef),
                "--docs",
                rel(paths["docs"]),
                "--out",
                rel(paths["definition_index"]),
                "--replace",
            ],
        ]
    )

    if not args.skip_evaluation:
        commands.extend(
            [
                [
                    args.python,
                    "scripts/evaluate_paragraph_quality.py",
                    "--vectors",
                    rel(paths["vectors"]),
                    "--docs",
                    rel(paths["docs"]),
                    "--label-index",
                    rel(paths["label_index"]),
                    "--code-index",
                    rel(paths["code_index"]),
                    "--semantic-type-index",
                    rel(paths["semantic_type_index"]),
                    "--relation-index",
                    rel(paths["relation_index"]),
                    "--research-relation-index",
                    rel(paths["research_relation_index"]),
                    "--definition-index",
                    rel(paths["definition_index"]),
                    "--active-label-supplement",
                    rel(DEFAULT_ACTIVE_LABEL_SUPPLEMENT),
                    "--output-dir",
                    rel(paths["eval_dir"]),
                    "--top-k",
                    str(args.top_k),
                ],
                [
                    args.python,
                    "scripts/audit_paragraph_precision.py",
                    "--payloads",
                    rel(paths["eval_dir"] / "paragraph_search_payloads.jsonl"),
                    "--output-dir",
                    rel(paths["eval_dir"]),
                    "--top-n",
                    "10",
                ],
            ]
        )

    manifest = [
        args.python,
        "scripts/reproducibility_manifest.py",
        "--umls-meta",
        str(umls_meta),
        "--out",
        rel(paths["manifest"]),
    ]
    if args.loinc_dir:
        manifest.extend(["--loinc-dir", str(resolve_path(args.loinc_dir))])
    for snomed_zip in args.snomed_zip:
        manifest.extend(["--snomed-zip", str(resolve_path(snomed_zip))])
    if not args.no_hash_small_files:
        manifest.append("--hash-small-files")
    commands.append(manifest)
    return commands, paths


def server_command(args: argparse.Namespace, paths: dict[str, Path]) -> list[str]:
    return [
        args.python,
        "scripts/search_quality_server.py",
        "--port",
        "8766",
        "--vectors",
        rel(paths["vectors"]),
        "--docs",
        rel(paths["docs"]),
        "--label-index",
        rel(paths["label_index"]),
        "--code-index",
        rel(paths["code_index"]),
        "--semantic-type-index",
        rel(paths["semantic_type_index"]),
        "--relation-index",
        rel(paths["relation_index"]),
        "--research-relation-index",
        rel(paths["research_relation_index"]),
        "--definition-index",
        rel(paths["definition_index"]),
        "--provenance-index",
        rel(paths["provenance_index"]),
        "--active-label-supplement",
        rel(DEFAULT_ACTIVE_LABEL_SUPPLEMENT),
    ]


def main() -> int:
    args = parse_args()
    args.umls_meta = resolve_path(args.umls_meta)
    args.out_dir = resolve_path(args.out_dir)
    args.index_dir = resolve_path(args.index_dir) if args.index_dir else args.out_dir / "indexes"
    args.topics = resolve_path(args.topics)

    for label, path in {
        "UMLS META directory": args.umls_meta,
        "MRCONSO.RRF": args.umls_meta / "MRCONSO.RRF",
        "MRSTY.RRF": args.umls_meta / "MRSTY.RRF",
        "MRREL.RRF": args.umls_meta / "MRREL.RRF",
        "MRDEF.RRF": args.umls_meta / "MRDEF.RRF",
        "topics TSV": args.topics,
        "active label supplement": DEFAULT_ACTIVE_LABEL_SUPPLEMENT,
    }.items():
        require_file(path, label, dry_run=args.dry_run)

    commands, paths = public_rebuild_commands(args)
    run_server = server_command(args, paths)
    if not args.dry_run:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        args.index_dir.mkdir(parents=True, exist_ok=True)
        command_plan = {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "commands": commands,
            "server_command": run_server,
        }
        paths["commands"].write_text(json.dumps(command_plan, indent=2) + "\n", encoding="utf-8")

    for command in commands:
        run_command(command, dry_run=args.dry_run)

    write_text(paths["server_command"], command_string(run_server) + "\n", dry_run=args.dry_run)
    print("\nServer command:")
    print(command_string(run_server))
    print("\nAfter starting the server, open http://127.0.0.1:8766/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
