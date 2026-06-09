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
DEFAULT_DAILYMED_DRUGS = (
    "metformin",
    "insulin",
    "osimertinib",
    "sumatriptan",
    "pantoprazole",
    "cephalexin",
    "amoxicillin",
    "warfarin",
    "semaglutide",
    "acetaminophen",
)
DEFAULT_REFERENCE_PAGE_SOURCES = ("nci", "cdc", "fda", "niddk")
DEFAULT_BOOKSHELF_OA_TERMS = (
    "clinical guidelines",
    "expert panel report",
    "evidence report",
    "guidelines for the diagnosis",
    "patient safety",
)
DEFAULT_HPO_OBO = "http://purl.obolibrary.org/obo/hp.obo"
DEFAULT_MONDO_OBO = "http://purl.obolibrary.org/obo/mondo.obo"
DEFAULT_HPO_RELATION_DIR = ROOT / "data" / "external" / "hpo"
REFERENCE_PAGE_SOURCE_CHOICES = (
    "nci",
    "cdc",
    "fda",
    "niddk",
    "merck_manual_professional",
    "msd_manual_professional",
    "aafp",
    "medscape",
    "bmj_best_practice",
    "nice_cks",
    "ncbi_bookshelf_statpearls",
    "patient_info_professional",
    "gpnotebook",
    "wikem",
)
BIOMEDICINE_PROFILES = (
    "clinical",
    "chemicals-drugs",
    "genes-proteins",
    "anatomy",
    "procedures-devices",
    "organisms",
    "labs-measurements",
)


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


def safe_profile_name(profile: str) -> str:
    return profile.replace("-", "_")


def profile_evidence_paths(out_dir: Path, run_name: str) -> list[Path]:
    return [
        out_dir / f"{run_name}_{safe_profile_name(profile)}_evidence.jsonl"
        for profile in BIOMEDICINE_PROFILES
    ]


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
            "locally licensed UMLS files. Does not use EHR data."
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
    parser.add_argument("--clinicaltrials-query", default="cancer OR diabetes OR migraine OR sepsis OR pneumonia")
    parser.add_argument("--clinicaltrials-max-records", type=int, default=100)
    parser.add_argument("--clinicaltrials-page-size", type=int, default=25)
    parser.add_argument(
        "--clinicaltrials-registry-context",
        action="store_true",
        help="Include protocol/eligibility registry text. Default is posted outcome results only.",
    )
    parser.add_argument("--medlineplus-max-records", type=int, default=0, help="0 means no limit; default is the full MedlinePlus feed")
    parser.add_argument("--medlineplus-source-url", help="Optional pinned MedlinePlus health topic XML or ZIP URL.")
    medlineplus_language_group = parser.add_mutually_exclusive_group()
    medlineplus_language_group.add_argument(
        "--include-medlineplus-spanish",
        dest="include_medlineplus_spanish",
        action="store_true",
        default=True,
        help="Include Spanish MedlinePlus health topics. This is the default for full MedlinePlus snapshots.",
    )
    medlineplus_language_group.add_argument(
        "--english-medlineplus-only",
        dest="include_medlineplus_spanish",
        action="store_false",
        help="Exclude Spanish MedlinePlus health topics.",
    )
    parser.add_argument("--medlineplus-genetics-max-records", type=int, default=500, help="0 means no limit")
    parser.add_argument("--medlineplus-genetics-source-url", default="https://medlineplus.gov/download/ghr-summaries.xml")
    parser.add_argument("--dailymed-drug", action="append", dest="dailymed_drug_names", help="DailyMed drug-name subset seed. Repeat as needed.")
    parser.add_argument("--dailymed-setid", action="append", default=[], help="DailyMed SPL set ID. Repeat as needed.")
    parser.add_argument("--dailymed-mrsat", type=Path, help="Optional UMLS MRSAT.RRF path used to extract DailyMed SPL set IDs.")
    parser.add_argument("--dailymed-max-setids-from-mrsat", type=int, default=50)
    parser.add_argument("--dailymed-max-records", type=int, default=20, help="0 means no limit")
    parser.add_argument("--dailymed-max-labels-per-drug", type=int, default=1)
    parser.add_argument("--dailymed-max-chars", type=int, default=20000)
    parser.add_argument("--bookshelf-oa-term", action="append", dest="bookshelf_oa_terms", help="NLM LitArch Bookshelf OA title/publisher filter. Repeat as needed.")
    parser.add_argument("--bookshelf-oa-accession-id", action="append", default=[], help="Bookshelf accession ID such as NBK7232. Repeat as needed.")
    parser.add_argument("--bookshelf-oa-file-list-url", default="https://ftp.ncbi.nlm.nih.gov/pub/litarch/file_list.csv")
    parser.add_argument("--bookshelf-oa-package-base-url", default="https://ftp.ncbi.nlm.nih.gov/pub/litarch/")
    parser.add_argument("--bookshelf-oa-max-books", type=int, default=3, help="0 means no book-package limit")
    parser.add_argument("--bookshelf-oa-max-records", type=int, default=100, help="0 means no corpus-document limit")
    parser.add_argument("--bookshelf-oa-max-chars", type=int, default=30000)
    parser.add_argument("--bookshelf-oa-min-chars", type=int, default=300)
    parser.add_argument("--hpo-source-url", default=DEFAULT_HPO_OBO, help="HPO OBO URL or local OBO file.")
    parser.add_argument("--hpo-max-records", type=int, default=0, help="0 means no HPO term limit")
    parser.add_argument("--mondo-source-url", default=DEFAULT_MONDO_OBO, help="Mondo OBO URL or local OBO file.")
    parser.add_argument("--mondo-max-records", type=int, default=0, help="0 means no Mondo term limit")
    parser.add_argument("--ontology-max-chars", type=int, default=8000)
    parser.add_argument("--include-obsolete-ontology-terms", action="store_true")
    parser.add_argument("--hpo-relation-obo", type=Path, default=DEFAULT_HPO_RELATION_DIR / "hp.obo")
    parser.add_argument("--hpo-relation-phenotype-annotations", type=Path, default=DEFAULT_HPO_RELATION_DIR / "phenotype.hpoa")
    parser.add_argument("--hpo-relation-genes-to-phenotype", type=Path, default=DEFAULT_HPO_RELATION_DIR / "genes_to_phenotype.txt")
    parser.add_argument(
        "--reference-page-source",
        action="append",
        choices=REFERENCE_PAGE_SOURCE_CHOICES,
        help=(
            "Reference page source to fetch. Repeat as needed. Defaults to NCI, CDC, FDA, and NIDDK. "
            "Restricted sources are not included by default."
        ),
    )
    parser.add_argument("--reference-pages-max-records", type=int, default=25)
    parser.add_argument("--reference-pages-max-chars", type=int, default=25000)
    parser.add_argument(
        "--allow-restricted-reference-source",
        action="store_true",
        help="Allow restricted reference pages for a private licensed deployment.",
    )
    parser.add_argument("--email", help="Optional NCBI contact email metadata.")
    parser.add_argument("--tool", default="query_expansion_public_rebuild")
    parser.add_argument("--matcher", choices=["sqlite", "trie"], default="trie")
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
    parser.add_argument("--skip-clinicaltrials", action="store_true")
    parser.add_argument("--skip-medlineplus", action="store_true")
    parser.add_argument("--skip-medlineplus-genetics", action="store_true")
    parser.add_argument("--skip-dailymed", action="store_true")
    parser.add_argument("--skip-bookshelf-oa", action="store_true")
    parser.add_argument("--skip-hpo", action="store_true")
    parser.add_argument("--skip-mondo", action="store_true")
    parser.add_argument(
        "--include-hpo-research-relations",
        action="store_true",
        help=(
            "Augment the research relation index with staged HPO disease/gene/phenotype "
            "annotation files. Treat Orphanet as UMLS/source-code crosswalk coverage, "
            "not a separate fetch target; review HPO/OMIM/Orphanet annotation reuse "
            "terms before redistributing derived artifacts."
        ),
    )
    parser.add_argument("--skip-reference-pages", action="store_true")
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
    public_run_name = "public_corpus"

    paths = {
        "umls_meta": umls_meta,
        "topics": topics,
        "hpo_relation_obo": resolve_path(args.hpo_relation_obo),
        "hpo_relation_phenotype_annotations": resolve_path(args.hpo_relation_phenotype_annotations),
        "hpo_relation_genes_to_phenotype": resolve_path(args.hpo_relation_genes_to_phenotype),
        "pubmed_corpus": out_dir / "pubmed_topics_corpus.jsonl",
        "europepmc_corpus": out_dir / "europepmc_topics_corpus.jsonl",
        "pmc_oa_corpus": out_dir / "pmc_oa_topics_corpus.jsonl",
        "clinicaltrials_corpus": out_dir / "clinicaltrials_subset_corpus.jsonl",
        "medlineplus_corpus": out_dir / "medlineplus_subset_corpus.jsonl",
        "medlineplus_genetics_corpus": out_dir / "medlineplus_genetics_subset_corpus.jsonl",
        "dailymed_corpus": out_dir / "dailymed_subset_corpus.jsonl",
        "bookshelf_oa_corpus": out_dir / "bookshelf_oa_subset_corpus.jsonl",
        "hpo_corpus": out_dir / "hpo_ontology_corpus.jsonl",
        "mondo_corpus": out_dir / "mondo_ontology_corpus.jsonl",
        "reference_page_corpora": {
            source: out_dir / f"{source}_reference_pages_corpus.jsonl"
            for source in (args.reference_page_source or list(DEFAULT_REFERENCE_PAGE_SOURCES))
        },
        "label_index": index_dir / "umls_biomedicine_search_label_index.sqlite",
        "profile_index_dir": index_dir / "profile_indexes",
        "profile_evidence_dir": out_dir / "profile_evidence",
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
        if not args.skip_clinicaltrials:
            clinicaltrials = [
                args.python,
                "scripts/evidence_vectors.py",
                "fetch-clinicaltrials",
                "--query",
                args.clinicaltrials_query,
                "--max-records",
                str(args.clinicaltrials_max_records),
                "--page-size",
                str(args.clinicaltrials_page_size),
                "--out",
                rel(paths["clinicaltrials_corpus"]),
            ]
            if not args.clinicaltrials_registry_context:
                clinicaltrials.append("--outcomes-only")
            commands.append(clinicaltrials)
        if not args.skip_medlineplus:
            medlineplus = [
                args.python,
                "scripts/evidence_vectors.py",
                "fetch-medlineplus",
                "--max-records",
                str(args.medlineplus_max_records),
                "--out",
                rel(paths["medlineplus_corpus"]),
            ]
            if args.medlineplus_source_url:
                medlineplus.extend(["--source-url", args.medlineplus_source_url])
            if args.include_medlineplus_spanish:
                medlineplus.append("--include-spanish")
            commands.append(medlineplus)
        if not args.skip_medlineplus_genetics:
            commands.append(
                [
                    args.python,
                    "scripts/evidence_vectors.py",
                    "fetch-medlineplus-genetics",
                    "--source-url",
                    args.medlineplus_genetics_source_url,
                    "--max-records",
                    str(args.medlineplus_genetics_max_records),
                    "--out",
                    rel(paths["medlineplus_genetics_corpus"]),
                ]
            )
        if not args.skip_dailymed:
            dailymed = [
                args.python,
                "scripts/evidence_vectors.py",
                "fetch-dailymed",
                "--max-records",
                str(args.dailymed_max_records),
                "--max-labels-per-drug",
                str(args.dailymed_max_labels_per_drug),
                "--max-chars",
                str(args.dailymed_max_chars),
                "--out",
                rel(paths["dailymed_corpus"]),
            ]
            for drug_name in args.dailymed_drug_names or list(DEFAULT_DAILYMED_DRUGS):
                dailymed.extend(["--drug-name", drug_name])
            for setid in args.dailymed_setid:
                dailymed.extend(["--setid", setid])
            if args.dailymed_mrsat:
                dailymed.extend(
                    [
                        "--mrsat",
                        str(resolve_path(args.dailymed_mrsat)),
                        "--max-setids-from-mrsat",
                        str(args.dailymed_max_setids_from_mrsat),
                    ]
                )
            commands.append(dailymed)
        if not args.skip_bookshelf_oa:
            bookshelf_oa = [
                args.python,
                "scripts/evidence_vectors.py",
                "fetch-bookshelf-oa",
                "--file-list-url",
                args.bookshelf_oa_file_list_url,
                "--package-base-url",
                args.bookshelf_oa_package_base_url,
                "--max-books",
                str(args.bookshelf_oa_max_books),
                "--max-records",
                str(args.bookshelf_oa_max_records),
                "--max-chars",
                str(args.bookshelf_oa_max_chars),
                "--min-chars",
                str(args.bookshelf_oa_min_chars),
                "--out",
                rel(paths["bookshelf_oa_corpus"]),
            ]
            for term in args.bookshelf_oa_terms or list(DEFAULT_BOOKSHELF_OA_TERMS):
                bookshelf_oa.extend(["--term", term])
            for accession_id in args.bookshelf_oa_accession_id:
                bookshelf_oa.extend(["--accession-id", accession_id])
            commands.append(bookshelf_oa)
        if not args.skip_hpo:
            hpo = [
                args.python,
                "scripts/evidence_vectors.py",
                "fetch-obo-ontology",
                "--source",
                "hpo",
                "--source-url",
                args.hpo_source_url,
                "--max-records",
                str(args.hpo_max_records),
                "--max-chars",
                str(args.ontology_max_chars),
                "--out",
                rel(paths["hpo_corpus"]),
            ]
            if args.include_obsolete_ontology_terms:
                hpo.append("--include-obsolete")
            commands.append(hpo)
        if not args.skip_mondo:
            mondo = [
                args.python,
                "scripts/evidence_vectors.py",
                "fetch-obo-ontology",
                "--source",
                "mondo",
                "--source-url",
                args.mondo_source_url,
                "--max-records",
                str(args.mondo_max_records),
                "--max-chars",
                str(args.ontology_max_chars),
                "--out",
                rel(paths["mondo_corpus"]),
            ]
            if args.include_obsolete_ontology_terms:
                mondo.append("--include-obsolete")
            commands.append(mondo)
        if not args.skip_reference_pages:
            for source, corpus_path in paths["reference_page_corpora"].items():
                commands.append(
                    [
                        args.python,
                        "scripts/evidence_vectors.py",
                        "fetch-reference-pages",
                        "--source",
                        source,
                        "--max-records",
                        str(args.reference_pages_max_records),
                        "--max-chars",
                        str(args.reference_pages_max_chars),
                        "--out",
                        rel(corpus_path),
                    ]
                )
                if args.allow_restricted_reference_source:
                    commands[-1].append("--allow-restricted-reference-source")

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
                "build-profile-indexes",
                "--mrconso",
                str(mrconso),
                "--mrsty",
                str(mrsty),
                "--out-dir",
                rel(paths["profile_index_dir"]),
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

    corpus_paths = [
        rel(paths["pubmed_corpus"]),
        rel(paths["europepmc_corpus"]),
        rel(paths["pmc_oa_corpus"]),
    ]
    if not args.skip_clinicaltrials:
        corpus_paths.append(rel(paths["clinicaltrials_corpus"]))
    if not args.skip_medlineplus:
        corpus_paths.append(rel(paths["medlineplus_corpus"]))
    if not args.skip_medlineplus_genetics:
        corpus_paths.append(rel(paths["medlineplus_genetics_corpus"]))
    if not args.skip_dailymed:
        corpus_paths.append(rel(paths["dailymed_corpus"]))
    if not args.skip_bookshelf_oa:
        corpus_paths.append(rel(paths["bookshelf_oa_corpus"]))
    if not args.skip_hpo:
        corpus_paths.append(rel(paths["hpo_corpus"]))
    if not args.skip_mondo:
        corpus_paths.append(rel(paths["mondo_corpus"]))
    if not args.skip_reference_pages:
        for corpus_path in paths["reference_page_corpora"].values():
            corpus_paths.append(rel(corpus_path))
    link = [
        args.python,
        "scripts/evidence_vectors.py",
        "link-profile-shards",
        "--corpus",
        *corpus_paths,
        "--index-dir",
        rel(paths["profile_index_dir"]),
        "--out-dir",
        rel(paths["profile_evidence_dir"]),
        "--run-name",
        public_run_name,
        "--materialize-corpus",
        "--max-ambiguity",
        "1",
        "--max-mentions-per-cui",
        "8",
        "--matcher",
        args.matcher,
    ]
    if args.max_docs:
        link.extend(["--max-docs", str(args.max_docs)])
    commands.append(link)

    evidence_paths = [
        rel(path) for path in profile_evidence_paths(paths["profile_evidence_dir"], public_run_name)
    ]
    research_relation = [
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
    ]
    commands.extend(
        [
            [
                args.python,
                "scripts/evidence_vectors.py",
                "build-docs-sqlite",
                "--evidence",
                *evidence_paths,
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
                *evidence_paths,
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
            research_relation,
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
    hpo_relation_paths = [
        paths["hpo_relation_obo"],
        paths["hpo_relation_phenotype_annotations"],
        paths["hpo_relation_genes_to_phenotype"],
    ]
    if args.include_hpo_research_relations:
        existing_hpo_relation_paths = [path.exists() for path in hpo_relation_paths]
        if all(existing_hpo_relation_paths) or args.dry_run:
            research_relation.extend(
                [
                    "--hpo-obo",
                    rel(paths["hpo_relation_obo"]),
                    "--hpo-phenotype-annotations",
                    rel(paths["hpo_relation_phenotype_annotations"]),
                    "--hpo-genes-to-phenotype",
                    rel(paths["hpo_relation_genes_to_phenotype"]),
                ]
            )
        elif any(existing_hpo_relation_paths):
            missing = ", ".join(rel(path) for path, exists in zip(hpo_relation_paths, existing_hpo_relation_paths) if not exists)
            raise SystemExit(f"missing staged HPO relation file(s): {missing}")

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
