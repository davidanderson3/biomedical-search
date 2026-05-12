#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qe_evidence_vectors.documents import build_documents, evidence_from_jsonl, iter_documents_jsonl
from qe_evidence_vectors.document_sqlite import build_documents_sqlite
from qe_evidence_vectors.extension_concepts import build_extension_concept_artifacts
from qe_evidence_vectors.compact_vectors import write_compact_vectors
from qe_evidence_vectors.definition_index import build_definition_index
from qe_evidence_vectors.elastic_client import (
    add_alias,
    create_index,
    delete_docs_by_cui,
    load_bulk_files,
    resolve_bulk_paths,
    search_knn,
)
from qe_evidence_vectors.elastic_export import (
    elastic_mapping,
    vector_dims,
    write_elastic_bulk,
    write_elastic_bulk_sharded,
    write_elastic_mapping,
)
from qe_evidence_vectors.embeddings import (
    DEFAULT_BIOMEDICAL_BERT_MODEL,
    iter_embed_documents,
    make_embedder,
)
from qe_evidence_vectors.evidence import iter_filtered_evidence_files
from qe_evidence_vectors.external_cui_vectors import build_external_cui_vector_index
from qe_evidence_vectors.corpus import merge_corpus_documents, read_tabular_corpus
from qe_evidence_vectors.code_index import build_code_index
from qe_evidence_vectors.fetchers import (
    fetch_europepmc_documents,
    fetch_europepmc_topic_documents,
    fetch_pmc_oa_documents,
    fetch_pmc_oa_topic_documents,
    fetch_pubmed_documents,
    fetch_pubmed_topic_documents,
    read_pubmed_topics,
)
from qe_evidence_vectors.ingest import read_query_log_tsv, read_snippet_tsv
from qe_evidence_vectors.label_index import LabelIndex, build_label_index
from qe_evidence_vectors.linker import iter_linked_corpus_evidence
from qe_evidence_vectors.profile_workflow import build_profile_indexes, link_profile_shards
from qe_evidence_vectors.pubmed_bulk import (
    DEFAULT_PUBMED_BULK_LATEST_BASELINE,
    DEFAULT_PUBMED_BULK_YEAR,
    download_pubmed_bulk_files,
    recent_baseline_files,
    write_bulk_manifest,
    write_pubmed_bulk_corpus,
)
from qe_evidence_vectors.provenance_index import build_provenance_index
from qe_evidence_vectors.relation_index import build_relation_index
from qe_evidence_vectors.relationship_edge_index import build_relationship_edge_index
from qe_evidence_vectors.research_relations import build_research_relation_index
from qe_evidence_vectors.schema import write_jsonl
from qe_evidence_vectors.search import search_vector_file
from qe_evidence_vectors.semantic_type_index import build_semantic_type_index
from qe_evidence_vectors.semantic_profiles import biomedicine_profile_names, profile_names
from qe_evidence_vectors.trie_linker import LabelTrie, iter_linked_corpus_evidence_trie


def cmd_fetch_pubmed(args: argparse.Namespace) -> int:
    documents = fetch_pubmed_documents(
        term=args.term,
        retmax=args.retmax,
        email=args.email,
        api_key=args.api_key,
        tool=args.tool,
        batch_size=args.batch_size,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} PubMed corpus documents to {args.out}")
    return 0


def cmd_fetch_pubmed_topics(args: argparse.Namespace) -> int:
    topics = read_pubmed_topics(args.topics, default_retmax=args.retmax)
    documents = fetch_pubmed_topic_documents(
        topics,
        default_retmax=args.retmax,
        email=args.email,
        api_key=args.api_key,
        tool=args.tool,
        batch_size=args.batch_size,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} de-duplicated PubMed corpus documents from {len(topics):,} topics to {args.out}")
    return 0


def cmd_download_pubmed_baseline(args: argparse.Namespace) -> int:
    files = recent_baseline_files(
        year=args.year,
        latest_number=args.latest_number,
        count=args.count,
        out_dir=args.out_dir,
    )
    results = download_pubmed_bulk_files(
        files,
        skip_existing=not args.force,
        verify_md5=not args.no_verify_md5,
    )
    if args.manifest:
        write_bulk_manifest(args.manifest, results)
    total_bytes = sum(int(result["bytes"]) for result in results)
    print(
        f"Downloaded/verified {len(results):,} PubMed baseline file(s), "
        f"{total_bytes / (1024 * 1024):.1f} MiB, newest-first from "
        f"pubmed{args.year % 100:02d}n{args.latest_number:04d}"
    )
    for result in results:
        print(f"{result['name']}\t{result['bytes']:,}\t{result['local_path']}")
    return 0


def cmd_ingest_pubmed_baseline(args: argparse.Namespace) -> int:
    count = write_pubmed_bulk_corpus(
        args.input,
        args.out,
        max_docs=args.max_docs,
    )
    print(f"Wrote {count:,} PubMed bulk baseline corpus documents to {args.out}")
    return 0


def cmd_fetch_europepmc(args: argparse.Namespace) -> int:
    documents = fetch_europepmc_documents(
        query=args.query,
        max_records=args.max_records,
        page_size=args.page_size,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} Europe PMC corpus documents to {args.out}")
    return 0


def cmd_fetch_europepmc_topics(args: argparse.Namespace) -> int:
    topics = read_pubmed_topics(args.topics, default_retmax=args.max_records)
    documents = fetch_europepmc_topic_documents(
        topics,
        default_max_records=args.max_records,
        page_size=args.page_size,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} de-duplicated Europe PMC corpus documents from {len(topics):,} topics to {args.out}")
    return 0


def cmd_fetch_pmc_oa(args: argparse.Namespace) -> int:
    documents = fetch_pmc_oa_documents(
        query=args.query,
        max_records=args.max_records,
        email=args.email,
        api_key=args.api_key,
        tool=args.tool,
        batch_size=args.batch_size,
        max_chars=args.max_chars,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} PMC OA full-text corpus documents to {args.out}")
    return 0


def cmd_fetch_pmc_oa_topics(args: argparse.Namespace) -> int:
    topics = read_pubmed_topics(args.topics, default_retmax=args.max_records)
    documents = fetch_pmc_oa_topic_documents(
        topics,
        default_max_records=args.max_records,
        email=args.email,
        api_key=args.api_key,
        tool=args.tool,
        batch_size=args.batch_size,
        max_chars=args.max_chars,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} de-duplicated PMC OA full-text corpus documents from {len(topics):,} topics to {args.out}")
    return 0


def cmd_ingest_tabular_corpus(args: argparse.Namespace) -> int:
    documents = read_tabular_corpus(
        args.input,
        source=args.source,
        text_columns=args.text_column,
        id_columns=args.id_column,
        title_columns=args.title_column,
        delimiter=args.delimiter,
        max_rows=args.max_rows,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} tabular corpus documents to {args.out}")
    return 0


def cmd_ingest_mimic_structured(args: argparse.Namespace) -> int:
    from qe_evidence_vectors.mimic_structured import iter_mimic_structured_documents

    documents = iter_mimic_structured_documents(
        args.root,
        sources=set(args.source) if args.source else None,
        source_prefix=args.source_prefix,
        max_rows_per_table=args.max_rows_per_table,
        max_examples_per_group=args.max_examples_per_group,
        note_corpus_paths=args.note_corpus,
        max_notes_per_admission=args.max_notes_per_admission,
        max_note_examples_per_group=args.max_note_examples_per_group,
        note_context_chars=args.note_context_chars,
    )
    count = write_jsonl(args.out, documents)
    print(f"Wrote {count:,} MIMIC structured corpus documents to {args.out}")
    return 0


def cmd_ingest_mimic_notes(args: argparse.Namespace) -> int:
    from qe_evidence_vectors.mimic_notes import write_mimic_note_corpora

    results = write_mimic_note_corpora(
        root=args.root,
        out_dir=args.out_dir,
        note_kinds=args.note_kind or None,
        max_discharge_rows=args.max_discharge_rows,
        max_radiology_rows=args.max_radiology_rows,
    )
    total = 0
    for result in results:
        total += result.count
        print(f"Wrote {result.count:,} {result.note_kind} MIMIC-IV-Note documents to {result.path}")
    print(f"Wrote {total:,} total MIMIC-IV-Note corpus documents from {args.root}")
    return 0


def cmd_filter_evidence(args: argparse.Namespace) -> int:
    records = iter_filtered_evidence_files(
        args.evidence,
        include_source=set(args.include_source) if args.include_source else None,
        exclude_source=set(args.exclude_source) if args.exclude_source else None,
        include_evidence_type=set(args.include_evidence_type) if args.include_evidence_type else None,
        exclude_evidence_type=set(args.exclude_evidence_type) if args.exclude_evidence_type else None,
    )
    count = write_jsonl(args.out, records)
    print(f"Wrote {count:,} filtered evidence records to {args.out}")
    return 0


def cmd_build_label_index(args: argparse.Namespace) -> int:
    count = build_label_index(
        mrconso_path=args.mrconso,
        out_path=args.out,
        mrsty_path=args.mrsty,
        semantic_types=args.semantic_type,
        semantic_profiles=args.profile,
        language=args.language,
        include_suppressed=args.include_suppressed,
        include_generic=args.include_generic,
        min_chars=args.min_chars,
        min_tokens=args.min_tokens,
        max_tokens=args.max_tokens,
        replace=args.replace,
    )
    print(f"Indexed {count:,} UMLS labels into {args.out}")
    return 0


def cmd_build_code_index(args: argparse.Namespace) -> int:
    count = build_code_index(
        mrconso_path=args.mrconso,
        out_path=args.out,
        language=args.language,
        include_suppressed=args.include_suppressed,
        replace=args.replace,
        batch_size=args.batch_size,
    )
    print(f"Indexed {count:,} UMLS code mappings into {args.out}")
    return 0


def cmd_build_semantic_type_index(args: argparse.Namespace) -> int:
    count = build_semantic_type_index(
        mrsty_path=args.mrsty,
        out_path=args.out,
        replace=args.replace,
        batch_size=args.batch_size,
    )
    print(f"Indexed {count:,} UMLS semantic type rows into {args.out}")
    return 0


def cmd_list_semantic_profiles(args: argparse.Namespace) -> int:
    for name in profile_names():
        print(name)
    return 0


def cmd_build_profile_indexes(args: argparse.Namespace) -> int:
    results = build_profile_indexes(
        mrconso_path=args.mrconso,
        mrsty_path=args.mrsty,
        out_dir=args.out_dir,
        profiles=args.profile or None,
        prefix=args.prefix,
        language=args.language,
        include_suppressed=args.include_suppressed,
        include_generic=args.include_generic,
        min_chars=args.min_chars,
        min_tokens=args.min_tokens,
        max_tokens=args.max_tokens,
        replace=args.replace,
    )
    for result in results:
        print(f"{result.profile}\t{result.label_count:,}\t{result.path}")
    print(f"Built {len(results):,} profile label indexes in {args.out_dir}")
    return 0


def cmd_link_corpus(args: argparse.Namespace) -> int:
    documents = merge_corpus_documents(args.corpus)
    if args.max_docs is not None:
        documents = itertools.islice(documents, args.max_docs)
    if args.matcher == "trie":
        trie = LabelTrie.from_sqlite(args.label_index, max_label_tokens=args.max_label_tokens)
        evidence = iter_linked_corpus_evidence_trie(
            documents,
            trie,
            max_label_tokens=args.max_label_tokens,
            context_chars=args.context_chars,
            max_ambiguity=args.max_ambiguity,
            max_mentions_per_cui=args.max_mentions_per_cui,
            evidence_tag=args.evidence_tag,
        )
        count = write_jsonl(args.out, evidence)
    else:
        with LabelIndex(args.label_index) as index:
            evidence = iter_linked_corpus_evidence(
                documents,
                index,
                max_label_tokens=args.max_label_tokens,
                context_chars=args.context_chars,
                max_ambiguity=args.max_ambiguity,
                max_mentions_per_cui=args.max_mentions_per_cui,
                evidence_tag=args.evidence_tag,
            )
            count = write_jsonl(args.out, evidence)
    print(f"Linked corpus documents into {count:,} evidence records")
    return 0


def cmd_link_profile_shards(args: argparse.Namespace) -> int:
    results = link_profile_shards(
        corpus_paths=args.corpus,
        index_dir=args.index_dir,
        out_dir=args.out_dir,
        profiles=args.profile or None,
        index_prefix=args.index_prefix,
        index_suffix=args.index_suffix,
        run_name=args.run_name,
        max_label_tokens=args.max_label_tokens,
        context_chars=args.context_chars,
        max_ambiguity=args.max_ambiguity,
        max_mentions_per_cui=args.max_mentions_per_cui,
        max_docs=args.max_docs,
        materialize_corpus=args.materialize_corpus,
        matcher=args.matcher,
        tag_evidence=not args.no_evidence_tag,
    )
    total = 0
    for result in results:
        total += result.evidence_count
        print(f"{result.profile}\t{result.evidence_count:,}\t{result.evidence_path}")
    print(f"Linked {total:,} evidence records across {len(results):,} profile shards")
    return 0


def cmd_ingest_query_log(args: argparse.Namespace) -> int:
    records = list(
        read_query_log_tsv(
            args.input,
            default_source=args.source,
            default_evidence_type=args.evidence_type,
        )
    )
    count = write_jsonl(args.out, records)
    print(f"Wrote {count:,} query-log evidence records to {args.out}")
    return 0


def cmd_ingest_snippets(args: argparse.Namespace) -> int:
    records = list(
        read_snippet_tsv(
            args.input,
            default_source=args.source,
            default_evidence_type=args.evidence_type,
        )
    )
    count = write_jsonl(args.out, records)
    print(f"Wrote {count:,} snippet evidence records to {args.out}")
    return 0


def cmd_build_docs(args: argparse.Namespace) -> int:
    evidence = []
    for path in args.evidence:
        evidence.extend(evidence_from_jsonl(path))
    documents = build_documents(
        evidence,
        mrconso_path=args.mrconso,
        max_labels=args.max_labels,
        max_items_per_doc=args.max_items_per_doc,
    )
    count = write_jsonl(args.out, documents)
    print(f"Built {count:,} concept evidence documents from {len(evidence):,} evidence records")
    return 0


def cmd_build_docs_sqlite(args: argparse.Namespace) -> int:
    evidence_count, doc_count = build_documents_sqlite(
        evidence_paths=args.evidence,
        out_path=args.out,
        sqlite_path=args.sqlite,
        mrconso_path=args.mrconso,
        max_labels=args.max_labels,
        max_items_per_doc=args.max_items_per_doc,
        include_source=set(args.include_source) if args.include_source else None,
        exclude_source=set(args.exclude_source) if args.exclude_source else None,
        include_evidence_type=set(args.include_evidence_type) if args.include_evidence_type else None,
        exclude_evidence_type=set(args.exclude_evidence_type) if args.exclude_evidence_type else None,
        replace=args.replace,
    )
    print(
        f"Built {doc_count:,} concept evidence documents from "
        f"{evidence_count:,} evidence records using {args.sqlite}"
    )
    return 0


def cmd_build_extension_concepts(args: argparse.Namespace) -> int:
    include_status = set(args.include_status) if args.include_status else None
    doc_count, evidence_count = build_extension_concept_artifacts(
        input_path=args.input,
        out_docs=args.out_docs,
        out_evidence=args.out_evidence,
        out_registry=args.out_registry,
        namespace=args.namespace,
        view=args.view,
        default_source=args.default_source,
        max_items_per_doc=args.max_items_per_doc,
        min_evidence=args.min_evidence,
        include_status=include_status,
    )
    print(
        f"Built {doc_count:,} extension concept document(s) and "
        f"{evidence_count:,} evidence record(s)"
    )
    return 0


def cmd_build_relation_index(args: argparse.Namespace) -> int:
    stats = build_relation_index(
        mrrel_path=args.mrrel,
        mrconso_path=args.mrconso,
        out_path=args.out,
        doc_paths=args.docs,
        max_relations_per_cui=args.max_relations_per_cui,
        include_inverse=not args.no_inverse,
        include_suppressed=args.include_suppressed,
        replace=args.replace,
    )
    print(
        f"Indexed {stats['relations']:,} related-concept links for "
        f"{stats['sources_with_relations']:,}/{stats['source_cuis']:,} source CUIs "
        f"into {args.out}"
    )
    return 0


def cmd_build_research_relation_index(args: argparse.Namespace) -> int:
    hpo_paths = [
        args.hpo_obo,
        args.hpo_phenotype_annotations,
        args.hpo_genes_to_phenotype,
    ]
    if any(hpo_paths) and not all(hpo_paths):
        raise SystemExit(
            "--hpo-obo, --hpo-phenotype-annotations, and --hpo-genes-to-phenotype "
            "must be supplied together"
        )
    stats = build_research_relation_index(
        mrrel_path=args.mrrel,
        mrconso_path=args.mrconso,
        mrsty_path=args.mrsty,
        out_path=args.out,
        doc_paths=args.docs,
        max_relations_per_category=args.max_relations_per_category,
        include_inverse=not args.no_inverse,
        include_suppressed=args.include_suppressed,
        hpo_obo_path=args.hpo_obo,
        hpo_phenotype_annotations_path=args.hpo_phenotype_annotations,
        hpo_genes_to_phenotype_path=args.hpo_genes_to_phenotype,
        replace=args.replace,
    )
    hpo_suffix = f" including {stats.get('hpo_relations', 0):,} HPO links" if stats.get("hpo_relations") else ""
    print(
        f"Indexed {stats['relations']:,} research cross-type links across "
        f"{stats['categories']:,} target categories for "
        f"{stats['sources_with_relations']:,}/{stats['source_cuis']:,} source CUIs "
        f"into {args.out}{hpo_suffix}"
    )
    return 0


def cmd_build_relationship_edge_index(args: argparse.Namespace) -> int:
    stats = build_relationship_edge_index(
        edge_paths=args.edges,
        out_path=args.out,
        replace=args.replace,
    )
    print(
        f"Indexed {stats['edges']:,} relationship edge(s) from "
        f"{stats['input_rows']:,} JSONL row(s) into {args.out}"
    )
    return 0


def cmd_build_definition_index(args: argparse.Namespace) -> int:
    stats = build_definition_index(
        mrdef_path=args.mrdef,
        out_path=args.out,
        doc_paths=args.docs,
        max_definitions_per_cui=args.max_definitions_per_cui,
        include_suppressed=args.include_suppressed,
        replace=args.replace,
    )
    print(
        f"Indexed {stats['definitions_indexed']:,} MRDEF definition(s) for "
        f"{stats['cuis_with_definitions']:,}/{stats['source_cuis']:,} source CUIs "
        f"into {args.out}"
    )
    return 0


def cmd_build_external_cui_vector_index(args: argparse.Namespace) -> int:
    source_names = list(args.source_name or [])
    data_formats = list(args.format or [])
    if source_names and len(source_names) != len(args.input):
        raise SystemExit("--source-name must be repeated once per --input")
    if data_formats and len(data_formats) != len(args.input):
        raise SystemExit("--format must be repeated once per --input")
    inputs = []
    for index, path in enumerate(args.input):
        source_name = source_names[index] if source_names else Path(path).stem
        data_format = data_formats[index] if data_formats else "auto"
        inputs.append((path, source_name, data_format))
    stats = build_external_cui_vector_index(
        inputs=inputs,
        out_path=args.out,
        doc_paths=args.docs,
        mrconso_path=args.mrconso,
        code_index_path=args.code_index,
        eager_code_sabs=args.eager_code_sab,
        top_k=args.top_k,
        block_size=args.block_size,
        max_vectors=args.max_vectors,
        max_source_cuis=args.max_source_cuis,
        replace=args.replace,
        commit_every=args.commit_every,
    )
    print(
        f"Indexed {stats['neighbors']:,} external embedding neighbors for "
        f"{stats['source_cuis']:,} source CUIs across {stats['sources']:,} source file(s) "
        f"and {stats['vectors']:,} overlapping UMLS-format vectors into {args.out}"
    )
    return 0


def cmd_build_provenance_index(args: argparse.Namespace) -> int:
    stats = build_provenance_index(
        evidence_paths=args.evidence,
        sqlite_path=args.sqlite,
        document_paths=args.docs,
        replace=args.replace,
        batch_size=args.batch_size,
        sources_per_text=args.sources_per_text,
        max_document_items=args.max_document_items,
    )
    print(
        f"Indexed {stats['source_refs']:,} source refs from {stats['input_rows']:,} "
        f"evidence rows into {args.sqlite}"
    )
    print(f"Indexed {stats['doc_text_keys']:,} evidence text keys across {stats['docs']:,} concept docs")
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    if args.max_docs is not None and args.sample_docs is not None:
        raise ValueError("use only one of --max-docs or --sample-docs")
    embedder = make_embedder(
        args.provider,
        model=args.model,
        dim=args.dim,
        local_files_only=args.local_files_only,
        max_seq_length=args.max_seq_length,
        device=args.device,
    )
    documents = iter_documents_jsonl(args.docs)
    if args.max_docs is not None:
        documents = itertools.islice(documents, args.max_docs)
    elif args.sample_docs is not None:
        documents = iter(_reservoir_sample(documents, args.sample_docs, seed=args.seed))
    vectors = iter_embed_documents(
        documents,
        embedder,
        batch_size=args.batch_size,
        include_document_metadata=args.include_document_metadata,
        vector_precision=None if args.vector_precision < 0 else args.vector_precision,
        omit_text=args.omit_text,
    )
    count = write_jsonl(args.out, vectors)
    print(
        f"Wrote {count:,} vectors to {args.out} "
        f"using {embedder.provider_name}:{embedder.model_name}"
    )
    return 0


def cmd_compact_vectors(args: argparse.Namespace) -> int:
    manifest = write_compact_vectors(vectors_path=args.vectors, out_prefix=args.out_prefix)
    print(
        f"Wrote {manifest['count']:,} compact {manifest['dims']}-dim vectors to "
        f"{manifest['vectors']} with metadata {manifest['metadata']}"
    )
    return 0


def _reservoir_sample(iterable, sample_size: int, *, seed: int):
    if sample_size <= 0:
        raise ValueError("sample size must be positive")
    rng = random.Random(seed)
    sample = []
    for index, item in enumerate(iterable):
        if index < sample_size:
            sample.append(item)
            continue
        replacement = rng.randint(0, index)
        if replacement < sample_size:
            sample[replacement] = item
    return sample


def cmd_search(args: argparse.Namespace) -> int:
    embedder = make_embedder(
        args.provider,
        model=args.model,
        dim=args.dim,
        local_files_only=args.local_files_only,
        max_seq_length=args.max_seq_length,
        device=args.device,
    )
    hits = search_vector_file(args.vectors, args.query, embedder, top_k=args.top_k)
    for rank, hit in enumerate(hits, start=1):
        print(f"{rank}\t{hit.score:.4f}\t{hit.cui}\t{hit.view}\t{hit.doc_id}")
    return 0


def cmd_export_elastic(args: argparse.Namespace) -> int:
    dims = vector_dims(args.vectors)
    mapping = elastic_mapping(
        dims=dims,
        vector_field=args.vector_field,
        similarity=args.similarity,
        index_vectors=not args.no_index_vectors,
        shards=args.shards,
        replicas=args.replicas,
    )
    write_elastic_mapping(args.out_mapping, mapping)
    if args.bulk_docs_per_file:
        count, bulk_paths = write_elastic_bulk_sharded(
            args.out_bulk,
            args.vectors,
            index=args.index,
            docs_per_file=args.bulk_docs_per_file,
            vector_field=args.vector_field,
            op_type=args.op_type,
        )
        bulk_target = f"{len(bulk_paths):,} bulk files under {Path(args.out_bulk).parent}"
    else:
        count = write_elastic_bulk(
            args.out_bulk,
            args.vectors,
            index=args.index,
            vector_field=args.vector_field,
            op_type=args.op_type,
        )
        bulk_target = args.out_bulk
    print(
        f"Wrote Elasticsearch mapping for {dims}-dim vectors to {args.out_mapping}; "
        f"wrote {count:,} bulk documents to {bulk_target}"
    )
    return 0


def cmd_load_elastic(args: argparse.Namespace) -> int:
    bulk_paths = resolve_bulk_paths(args.bulk)
    if args.create_index:
        create_index(
            base_url=args.url,
            index=args.index,
            mapping_path=args.mapping,
            delete_existing=args.delete_existing,
        )
    total_items, total_errors = load_bulk_files(base_url=args.url, paths=bulk_paths)
    print(
        f"Loaded {total_items:,} bulk items into {args.index}; "
        f"errors={total_errors:,}"
    )
    if not total_errors and args.marker:
        marker = Path(args.marker).expanduser()
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            f"index={args.index}\nitems={total_items}\nurl={args.url}\n",
            encoding="utf-8",
        )
    if not total_errors and args.delete_bulk_after_load:
        for bulk_path in bulk_paths:
            Path(bulk_path).expanduser().unlink(missing_ok=True)
    return 1 if total_errors else 0


def cmd_alias_elastic(args: argparse.Namespace) -> int:
    response = add_alias(base_url=args.url, index=args.index, alias=args.alias)
    acknowledged = response.get("acknowledged")
    print(f"Added alias {args.alias} -> {args.index}; acknowledged={acknowledged}")
    return 0


def cmd_delete_elastic_cuis(args: argparse.Namespace) -> int:
    response = delete_docs_by_cui(base_url=args.url, index=args.index, cuis=args.cui)
    deleted = response.get("deleted", 0)
    version_conflicts = response.get("version_conflicts", 0)
    print(
        f"Deleted {deleted:,} documents from {args.index} for "
        f"{len(set(args.cui)):,} CUI(s); version_conflicts={version_conflicts:,}"
    )
    return 0


def cmd_search_elastic(args: argparse.Namespace) -> int:
    embedder = make_embedder(
        args.provider,
        model=args.model,
        dim=args.dim,
        local_files_only=args.local_files_only,
        max_seq_length=args.max_seq_length,
        device=args.device,
    )
    vector = embedder.embed([args.query])[0]
    hits = search_knn(
        base_url=args.url,
        index=args.index,
        vector=vector,
        vector_field=args.vector_field,
        k=args.k,
        num_candidates=args.num_candidates,
    )
    for rank, hit in enumerate(hits, start=1):
        source = hit.get("_source", {})
        print(
            f"{rank}\t{hit.get('_score', 0):.4f}\t"
            f"{source.get('cui', '')}\t{source.get('view', '')}\t"
            f"{source.get('doc_id', hit.get('_id', ''))}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build evidence-backed vector inputs for UMLS CUIs and reviewed extension concepts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    pubmed_parser = subparsers.add_parser("fetch-pubmed")
    pubmed_parser.add_argument("--term", required=True, help="PubMed search term")
    pubmed_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    pubmed_parser.add_argument("--retmax", type=int, default=100)
    pubmed_parser.add_argument(
        "--email",
        help="Optional NCBI contact email metadata; data is still written to --out.",
    )
    pubmed_parser.add_argument(
        "--api-key",
        help="NCBI E-utilities API key. Defaults to the NCBI or APIKEY environment variable.",
    )
    pubmed_parser.add_argument("--tool", default="query_expansion_vectors")
    pubmed_parser.add_argument("--batch-size", type=int, default=100)
    pubmed_parser.set_defaults(func=cmd_fetch_pubmed)

    pubmed_topics_parser = subparsers.add_parser("fetch-pubmed-topics")
    pubmed_topics_parser.add_argument("--topics", required=True, help="TSV with topic, term, and optional retmax columns")
    pubmed_topics_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    pubmed_topics_parser.add_argument("--retmax", type=int, default=500, help="Default records per topic")
    pubmed_topics_parser.add_argument(
        "--email",
        help="Optional NCBI contact email metadata; data is still written to --out.",
    )
    pubmed_topics_parser.add_argument(
        "--api-key",
        help="NCBI E-utilities API key. Defaults to the NCBI or APIKEY environment variable.",
    )
    pubmed_topics_parser.add_argument("--tool", default="query_expansion_vectors")
    pubmed_topics_parser.add_argument("--batch-size", type=int, default=100)
    pubmed_topics_parser.set_defaults(func=cmd_fetch_pubmed_topics)

    pubmed_baseline_download_parser = subparsers.add_parser("download-pubmed-baseline")
    pubmed_baseline_download_parser.add_argument(
        "--year",
        type=int,
        default=DEFAULT_PUBMED_BULK_YEAR,
        help="PubMed baseline production year.",
    )
    pubmed_baseline_download_parser.add_argument(
        "--latest-number",
        type=int,
        default=DEFAULT_PUBMED_BULK_LATEST_BASELINE,
        help=(
            "Highest baseline shard number to start from. For 2026, NLM released "
            f"up to {DEFAULT_PUBMED_BULK_LATEST_BASELINE}."
        ),
    )
    pubmed_baseline_download_parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of high-numbered baseline shards to download, newest-first.",
    )
    pubmed_baseline_download_parser.add_argument("--out-dir", default="data/pubmed/baseline")
    pubmed_baseline_download_parser.add_argument("--manifest", help="Optional JSON manifest output")
    pubmed_baseline_download_parser.add_argument("--force", action="store_true", help="Redownload existing files")
    pubmed_baseline_download_parser.add_argument("--no-verify-md5", action="store_true")
    pubmed_baseline_download_parser.set_defaults(func=cmd_download_pubmed_baseline)

    pubmed_baseline_ingest_parser = subparsers.add_parser("ingest-pubmed-baseline")
    pubmed_baseline_ingest_parser.add_argument("--input", required=True, nargs="+", help="PubMed baseline XML/XML.GZ files")
    pubmed_baseline_ingest_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    pubmed_baseline_ingest_parser.add_argument("--max-docs", type=int, help="Parse only the first N citation records")
    pubmed_baseline_ingest_parser.set_defaults(func=cmd_ingest_pubmed_baseline)

    europepmc_parser = subparsers.add_parser("fetch-europepmc")
    europepmc_parser.add_argument("--query", required=True, help="Europe PMC search query")
    europepmc_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    europepmc_parser.add_argument("--max-records", type=int, default=100)
    europepmc_parser.add_argument("--page-size", type=int, default=100)
    europepmc_parser.set_defaults(func=cmd_fetch_europepmc)

    europepmc_topics_parser = subparsers.add_parser("fetch-europepmc-topics")
    europepmc_topics_parser.add_argument("--topics", required=True, help="TSV with topic, term, and optional retmax columns")
    europepmc_topics_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    europepmc_topics_parser.add_argument("--max-records", type=int, default=500, help="Default records per topic")
    europepmc_topics_parser.add_argument("--page-size", type=int, default=100)
    europepmc_topics_parser.set_defaults(func=cmd_fetch_europepmc_topics)

    pmc_oa_parser = subparsers.add_parser("fetch-pmc-oa")
    pmc_oa_parser.add_argument("--query", required=True, help="PMC search query; open_access[filter] is added automatically")
    pmc_oa_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    pmc_oa_parser.add_argument("--max-records", type=int, default=100)
    pmc_oa_parser.add_argument(
        "--email",
        help="Optional NCBI contact email metadata; data is still written to --out.",
    )
    pmc_oa_parser.add_argument(
        "--api-key",
        help="NCBI E-utilities API key. Defaults to the NCBI or APIKEY environment variable.",
    )
    pmc_oa_parser.add_argument("--tool", default="query_expansion_vectors")
    pmc_oa_parser.add_argument("--batch-size", type=int, default=50)
    pmc_oa_parser.add_argument("--max-chars", type=int, help="Optional maximum full-text characters retained per article")
    pmc_oa_parser.set_defaults(func=cmd_fetch_pmc_oa)

    pmc_oa_topics_parser = subparsers.add_parser("fetch-pmc-oa-topics")
    pmc_oa_topics_parser.add_argument("--topics", required=True, help="TSV with topic, term, and optional retmax columns")
    pmc_oa_topics_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    pmc_oa_topics_parser.add_argument("--max-records", type=int, default=200, help="Default records per topic")
    pmc_oa_topics_parser.add_argument(
        "--email",
        help="Optional NCBI contact email metadata; data is still written to --out.",
    )
    pmc_oa_topics_parser.add_argument(
        "--api-key",
        help="NCBI E-utilities API key. Defaults to the NCBI or APIKEY environment variable.",
    )
    pmc_oa_topics_parser.add_argument("--tool", default="query_expansion_vectors")
    pmc_oa_topics_parser.add_argument("--batch-size", type=int, default=50)
    pmc_oa_topics_parser.add_argument("--max-chars", type=int, help="Optional maximum full-text characters retained per article")
    pmc_oa_topics_parser.set_defaults(func=cmd_fetch_pmc_oa_topics)

    tabular_parser = subparsers.add_parser("ingest-tabular-corpus")
    tabular_parser.add_argument("--input", required=True, help="Input CSV/TSV, optionally .gz")
    tabular_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    tabular_parser.add_argument("--source", required=True, help="Corpus source name, e.g. mimic_iv_ed")
    tabular_parser.add_argument(
        "--text-column",
        action="append",
        required=True,
        help="Column containing real-world text. Repeat to concatenate columns.",
    )
    tabular_parser.add_argument(
        "--id-column",
        action="append",
        default=[],
        help="Column used to build stable document ids. Repeat as needed.",
    )
    tabular_parser.add_argument(
        "--title-column",
        action="append",
        default=[],
        help="Optional title/header column. Repeat to concatenate columns.",
    )
    tabular_parser.add_argument("--delimiter", help="Override delimiter, e.g. ',' or tab")
    tabular_parser.add_argument("--max-rows", type=int)
    tabular_parser.set_defaults(func=cmd_ingest_tabular_corpus)

    mimic_structured_parser = subparsers.add_parser("ingest-mimic-structured")
    mimic_structured_parser.add_argument("--root", required=True, help="MIMIC-IV root containing hosp/ and icu/")
    mimic_structured_parser.add_argument("--out", required=True, help="Output corpus JSONL")
    mimic_structured_parser.add_argument(
        "--source-prefix",
        default="mimic_demo",
        help="Prefix for emitted source names, e.g. mimic_demo or mimic_iv.",
    )
    mimic_structured_parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Structured source to include after applying --source-prefix. Repeat as needed. Defaults to all non-DRG structured sources.",
    )
    mimic_structured_parser.add_argument("--max-rows-per-table", type=int)
    mimic_structured_parser.add_argument("--max-examples-per-group", type=int, default=8)
    mimic_structured_parser.add_argument(
        "--note-corpus",
        action="append",
        default=[],
        help=(
            "Optional MIMIC-IV-Note corpus JSONL produced by ingest-mimic-notes. "
            "Repeat to coordinate structured events with discharge and radiology notes by hadm_id."
        ),
    )
    mimic_structured_parser.add_argument("--max-notes-per-admission", type=int, default=3)
    mimic_structured_parser.add_argument("--max-note-examples-per-group", type=int, default=4)
    mimic_structured_parser.add_argument("--note-context-chars", type=int, default=240)
    mimic_structured_parser.set_defaults(func=cmd_ingest_mimic_structured)

    mimic_notes_parser = subparsers.add_parser("ingest-mimic-notes")
    mimic_notes_parser.add_argument(
        "--root",
        required=True,
        help="MIMIC-IV-Note root containing note/discharge.csv.gz and note/radiology.csv.gz",
    )
    mimic_notes_parser.add_argument("--out-dir", required=True, help="Output directory for per-note-source corpus JSONL files")
    mimic_notes_parser.add_argument(
        "--note-kind",
        action="append",
        default=[],
        choices=["discharge", "radiology"],
        help="Note kind to include. Repeat as needed. Defaults to discharge and radiology.",
    )
    mimic_notes_parser.add_argument("--max-discharge-rows", type=int, help="Optional cap for discharge.csv.gz rows")
    mimic_notes_parser.add_argument("--max-radiology-rows", type=int, help="Optional cap for radiology.csv.gz rows")
    mimic_notes_parser.set_defaults(func=cmd_ingest_mimic_notes)

    label_parser = subparsers.add_parser("build-label-index")
    label_parser.add_argument("--mrconso", required=True, help="Path to MRCONSO.RRF")
    label_parser.add_argument("--out", required=True, help="Output SQLite label index")
    label_parser.add_argument("--mrsty", help="Optional MRSTY.RRF for semantic-type filtering")
    label_parser.add_argument(
        "--semantic-type",
        action="append",
        default=[],
        help="TUI or semantic type name to include. Repeat as needed.",
    )
    label_parser.add_argument(
        "--profile",
        action="append",
        default=[],
        choices=profile_names(),
        help="Semantic profile to include. Repeat as needed.",
    )
    label_parser.add_argument("--language", default="ENG")
    label_parser.add_argument("--include-suppressed", action="store_true")
    label_parser.add_argument("--include-generic", action="store_true")
    label_parser.add_argument("--min-chars", type=int, default=3)
    label_parser.add_argument("--min-tokens", type=int, default=1)
    label_parser.add_argument("--max-tokens", type=int, default=8)
    label_parser.add_argument("--replace", action="store_true")
    label_parser.set_defaults(func=cmd_build_label_index)

    code_parser = subparsers.add_parser("build-code-index")
    code_parser.add_argument("--mrconso", required=True, help="Path to MRCONSO.RRF")
    code_parser.add_argument("--out", required=True, help="Output SQLite CUI/code index")
    code_parser.add_argument("--language", default="ENG")
    code_parser.add_argument("--include-suppressed", action="store_true")
    code_parser.add_argument("--replace", action="store_true")
    code_parser.add_argument("--batch-size", type=int, default=50_000)
    code_parser.set_defaults(func=cmd_build_code_index)

    semantic_type_parser = subparsers.add_parser("build-semantic-type-index")
    semantic_type_parser.add_argument("--mrsty", required=True, help="Path to MRSTY.RRF")
    semantic_type_parser.add_argument("--out", required=True, help="Output SQLite semantic type index")
    semantic_type_parser.add_argument("--replace", action="store_true")
    semantic_type_parser.add_argument("--batch-size", type=int, default=50_000)
    semantic_type_parser.set_defaults(func=cmd_build_semantic_type_index)

    relation_parser = subparsers.add_parser("build-relation-index")
    relation_parser.add_argument("--mrrel", required=True, help="Path to MRREL.RRF")
    relation_parser.add_argument("--mrconso", required=True, help="Path to MRCONSO.RRF")
    relation_parser.add_argument("--docs", required=True, nargs="+", help="Concept document JSONL files")
    relation_parser.add_argument("--out", required=True, help="Output SQLite related-concepts index")
    relation_parser.add_argument("--max-relations-per-cui", type=int, default=16)
    relation_parser.add_argument(
        "--no-inverse",
        action="store_true",
        help="Only index rows where the hit CUI appears as MRREL CUI1.",
    )
    relation_parser.add_argument("--include-suppressed", action="store_true")
    relation_parser.add_argument("--replace", action="store_true")
    relation_parser.set_defaults(func=cmd_build_relation_index)

    research_relation_parser = subparsers.add_parser("build-research-relation-index")
    research_relation_parser.add_argument("--mrrel", required=True, help="Path to MRREL.RRF")
    research_relation_parser.add_argument("--mrconso", required=True, help="Path to MRCONSO.RRF")
    research_relation_parser.add_argument("--mrsty", required=True, help="Path to MRSTY.RRF")
    research_relation_parser.add_argument("--docs", required=True, nargs="+", help="Concept document JSONL files")
    research_relation_parser.add_argument("--out", required=True, help="Output SQLite research relation index")
    research_relation_parser.add_argument("--max-relations-per-category", type=int, default=12)
    research_relation_parser.add_argument("--hpo-obo", help="Optional HPO hp.obo path for phenotype labels/xrefs")
    research_relation_parser.add_argument(
        "--hpo-phenotype-annotations",
        help="Optional HPO phenotype.hpoa path for disease-phenotype links",
    )
    research_relation_parser.add_argument(
        "--hpo-genes-to-phenotype",
        help="Optional HPO genes_to_phenotype.txt path for gene-disease-phenotype links",
    )
    research_relation_parser.add_argument(
        "--no-inverse",
        action="store_true",
        help="Only index rows where the hit CUI appears as MRREL CUI1.",
    )
    research_relation_parser.add_argument("--include-suppressed", action="store_true")
    research_relation_parser.add_argument("--replace", action="store_true")
    research_relation_parser.set_defaults(func=cmd_build_research_relation_index)

    relationship_edge_parser = subparsers.add_parser("build-relationship-edge-index")
    relationship_edge_parser.add_argument(
        "--edges",
        required=True,
        nargs="+",
        help="Mined universal relationship-edge JSONL files, such as OHDSI aggregate edges.",
    )
    relationship_edge_parser.add_argument("--out", required=True, help="Output SQLite relationship-edge index")
    relationship_edge_parser.add_argument("--replace", action="store_true")
    relationship_edge_parser.set_defaults(func=cmd_build_relationship_edge_index)

    definition_parser = subparsers.add_parser("build-definition-index")
    definition_parser.add_argument("--mrdef", required=True, help="Path to MRDEF.RRF")
    definition_parser.add_argument("--docs", required=True, nargs="+", help="Concept document JSONL files")
    definition_parser.add_argument("--out", required=True, help="Output SQLite definition index")
    definition_parser.add_argument("--max-definitions-per-cui", type=int, default=3)
    definition_parser.add_argument("--include-suppressed", action="store_true")
    definition_parser.add_argument("--replace", action="store_true")
    definition_parser.set_defaults(func=cmd_build_definition_index)

    external_vector_parser = subparsers.add_parser("build-external-cui-vector-index")
    external_vector_parser.add_argument(
        "--input",
        required=True,
        action="append",
        help="External CUI embedding file. Repeat for BioConceptVec/cui2vec or other sources.",
    )
    external_vector_parser.add_argument(
        "--source-name",
        action="append",
        default=[],
        help="Display/provenance name for an input file. Repeat once per --input.",
    )
    external_vector_parser.add_argument(
        "--format",
        action="append",
        default=[],
        choices=["auto", "json", "csv", "tsv", "word2vec"],
        help="Input format. Repeat once per --input. Defaults to auto.",
    )
    external_vector_parser.add_argument(
        "--docs",
        required=True,
        nargs="+",
        help="Concept document JSONL files; source CUIs are restricted to CUI overlap with these docs.",
    )
    external_vector_parser.add_argument(
        "--mrconso",
        help=(
            "Optional MRCONSO.RRF used to map BioConceptVec source IDs such as "
            "MESH/OMIM identifiers back to CUIs."
        ),
    )
    external_vector_parser.add_argument(
        "--code-index",
        help=(
            "Optional SQLite code index built with build-code-index. When supplied, "
            "BioConceptVec source-code identifiers are resolved through SAB/code, SCUI, and SDUI."
        ),
    )
    external_vector_parser.add_argument(
        "--eager-code-sab",
        action="append",
        default=["MSH", "OMIM", "GO", "HGNC", "NCI", "MEDLINEPLUS"],
        help=(
            "SAB to preload from --code-index for fast BioConceptVec source-code mapping. "
            "Repeat as needed."
        ),
    )
    external_vector_parser.add_argument("--out", required=True, help="Output SQLite external neighbor index")
    external_vector_parser.add_argument("--top-k", type=int, default=8)
    external_vector_parser.add_argument("--block-size", type=int, default=64)
    external_vector_parser.add_argument(
        "--max-vectors",
        type=int,
        help="Optional cap for debugging/smoke tests before indexing a full external embedding.",
    )
    external_vector_parser.add_argument(
        "--max-source-cuis",
        type=int,
        help="Optional cap on source CUIs for debugging/smoke tests.",
    )
    external_vector_parser.add_argument("--commit-every", type=int, default=500)
    external_vector_parser.add_argument("--replace", action="store_true")
    external_vector_parser.set_defaults(func=cmd_build_external_cui_vector_index)

    profiles_parser = subparsers.add_parser("list-semantic-profiles")
    profiles_parser.set_defaults(func=cmd_list_semantic_profiles)

    profile_indexes_parser = subparsers.add_parser("build-profile-indexes")
    profile_indexes_parser.add_argument("--mrconso", required=True, help="Path to MRCONSO.RRF")
    profile_indexes_parser.add_argument("--mrsty", required=True, help="Path to MRSTY.RRF")
    profile_indexes_parser.add_argument("--out-dir", required=True, help="Directory for profile SQLite indexes")
    profile_indexes_parser.add_argument(
        "--profile",
        action="append",
        default=[],
        choices=profile_names(),
        help=(
            "Profile to build. Repeat as needed. Defaults to the production "
            f"biomedicine shards: {', '.join(biomedicine_profile_names())}."
        ),
    )
    profile_indexes_parser.add_argument("--prefix", default="umls")
    profile_indexes_parser.add_argument("--language", default="ENG")
    profile_indexes_parser.add_argument("--include-suppressed", action="store_true")
    profile_indexes_parser.add_argument("--include-generic", action="store_true")
    profile_indexes_parser.add_argument("--min-chars", type=int, default=3)
    profile_indexes_parser.add_argument("--min-tokens", type=int, default=2)
    profile_indexes_parser.add_argument("--max-tokens", type=int, default=8)
    profile_indexes_parser.add_argument("--replace", action="store_true")
    profile_indexes_parser.set_defaults(func=cmd_build_profile_indexes)

    link_parser = subparsers.add_parser("link-corpus")
    link_parser.add_argument("--corpus", required=True, nargs="+", help="Corpus JSONL files")
    link_parser.add_argument("--label-index", required=True, help="SQLite label index")
    link_parser.add_argument("--out", required=True, help="Output evidence JSONL")
    link_parser.add_argument("--max-label-tokens", type=int, default=8)
    link_parser.add_argument("--context-chars", type=int, default=320)
    link_parser.add_argument("--max-ambiguity", type=int, default=1)
    link_parser.add_argument("--max-mentions-per-cui", type=int, default=8)
    link_parser.add_argument("--max-docs", type=int)
    link_parser.add_argument("--matcher", choices=["sqlite", "trie"], default="sqlite")
    link_parser.add_argument(
        "--evidence-tag",
        default="",
        help="Optional tag inserted into evidence_type, e.g. clinical -> pubmed_clinical_context.",
    )
    link_parser.set_defaults(func=cmd_link_corpus)

    link_profiles_parser = subparsers.add_parser("link-profile-shards")
    link_profiles_parser.add_argument("--corpus", required=True, nargs="+", help="Corpus JSONL files")
    link_profiles_parser.add_argument("--index-dir", required=True, help="Directory containing profile SQLite indexes")
    link_profiles_parser.add_argument("--out-dir", required=True, help="Directory for per-profile evidence JSONL")
    link_profiles_parser.add_argument(
        "--profile",
        action="append",
        default=[],
        choices=profile_names(),
        help=(
            "Profile to link. Repeat as needed. Defaults to the production "
            f"biomedicine shards: {', '.join(biomedicine_profile_names())}."
        ),
    )
    link_profiles_parser.add_argument("--index-prefix", default="umls")
    link_profiles_parser.add_argument("--index-suffix", default="profile_multiword_label_index.sqlite")
    link_profiles_parser.add_argument("--run-name", default="corpus")
    link_profiles_parser.add_argument("--max-label-tokens", type=int, default=8)
    link_profiles_parser.add_argument("--context-chars", type=int, default=320)
    link_profiles_parser.add_argument("--max-ambiguity", type=int, default=1)
    link_profiles_parser.add_argument("--max-mentions-per-cui", type=int, default=8)
    link_profiles_parser.add_argument("--max-docs", type=int)
    link_profiles_parser.add_argument(
        "--materialize-corpus",
        action="store_true",
        help=(
            "Load the merged corpus once and reuse it across profile shards. "
            "Use for bounded chunks that fit in memory; avoid for full PubMed-scale runs."
        ),
    )
    link_profiles_parser.add_argument("--matcher", choices=["sqlite", "trie"], default="trie")
    link_profiles_parser.add_argument(
        "--no-evidence-tag",
        action="store_true",
        help="Do not insert the profile name into evidence_type.",
    )
    link_profiles_parser.set_defaults(func=cmd_link_profile_shards)

    filter_parser = subparsers.add_parser("filter-evidence")
    filter_parser.add_argument("--evidence", required=True, nargs="+", help="Input evidence JSONL files")
    filter_parser.add_argument("--out", required=True, help="Output filtered evidence JSONL")
    filter_parser.add_argument("--include-source", action="append", default=[])
    filter_parser.add_argument("--exclude-source", action="append", default=[])
    filter_parser.add_argument("--include-evidence-type", action="append", default=[])
    filter_parser.add_argument("--exclude-evidence-type", action="append", default=[])
    filter_parser.set_defaults(func=cmd_filter_evidence)

    query_parser = subparsers.add_parser("ingest-query-log")
    query_parser.add_argument("--input", required=True, help="Input TSV with query and cui columns")
    query_parser.add_argument("--out", required=True, help="Output evidence JSONL")
    query_parser.add_argument("--source", required=True, help="Evidence source name")
    query_parser.add_argument("--evidence-type", default="failed_query")
    query_parser.set_defaults(func=cmd_ingest_query_log)

    snippet_parser = subparsers.add_parser("ingest-snippets")
    snippet_parser.add_argument("--input", required=True, help="Input TSV with cui and text columns")
    snippet_parser.add_argument("--out", required=True, help="Output evidence JSONL")
    snippet_parser.add_argument("--source", required=True, help="Default evidence source name")
    snippet_parser.add_argument("--evidence-type", default="reviewed_snippet")
    snippet_parser.set_defaults(func=cmd_ingest_snippets)

    docs_parser = subparsers.add_parser("build-docs")
    docs_parser.add_argument("--evidence", required=True, nargs="+", help="Evidence JSONL files")
    docs_parser.add_argument("--out", required=True, help="Output concept document JSONL")
    docs_parser.add_argument("--mrconso", help="Optional MRCONSO.RRF for labels on evidence-bearing CUIs")
    docs_parser.add_argument("--max-labels", type=int, default=8)
    docs_parser.add_argument("--max-items-per-doc", type=int, default=100)
    docs_parser.set_defaults(func=cmd_build_docs)

    docs_sqlite_parser = subparsers.add_parser("build-docs-sqlite")
    docs_sqlite_parser.add_argument("--evidence", required=True, nargs="+", help="Evidence JSONL files")
    docs_sqlite_parser.add_argument("--out", required=True, help="Output concept document JSONL")
    docs_sqlite_parser.add_argument("--sqlite", required=True, help="SQLite work database for aggregation")
    docs_sqlite_parser.add_argument("--mrconso", help="Optional MRCONSO.RRF for labels on evidence-bearing CUIs")
    docs_sqlite_parser.add_argument("--max-labels", type=int, default=8)
    docs_sqlite_parser.add_argument("--max-items-per-doc", type=int, default=100)
    docs_sqlite_parser.add_argument("--include-source", action="append", default=[])
    docs_sqlite_parser.add_argument("--exclude-source", action="append", default=[])
    docs_sqlite_parser.add_argument("--include-evidence-type", action="append", default=[])
    docs_sqlite_parser.add_argument("--exclude-evidence-type", action="append", default=[])
    docs_sqlite_parser.add_argument("--replace", action="store_true")
    docs_sqlite_parser.set_defaults(func=cmd_build_docs_sqlite)

    extension_parser = subparsers.add_parser("build-extension-concepts")
    extension_parser.add_argument("--input", required=True, help="Reviewed extension concept JSONL")
    extension_parser.add_argument("--out-docs", required=True, help="Output extension concept documents JSONL")
    extension_parser.add_argument("--out-evidence", required=True, help="Output extension concept evidence JSONL")
    extension_parser.add_argument("--out-registry", help="Optional output extension concept registry JSONL")
    extension_parser.add_argument(
        "--namespace",
        default="NEW",
        help="Prefix for generated local ids. The default emits NEW####### local CUIs.",
    )
    extension_parser.add_argument("--view", default="extension_concept")
    extension_parser.add_argument("--default-source", default="reviewed_extension_concept")
    extension_parser.add_argument("--max-items-per-doc", type=int, default=100)
    extension_parser.add_argument(
        "--min-evidence",
        type=int,
        default=1,
        help="Minimum evidence entries required before a concept is emitted.",
    )
    extension_parser.add_argument(
        "--include-status",
        action="append",
        default=[],
        help="Only emit concepts with this review status. Repeat as needed.",
    )
    extension_parser.set_defaults(func=cmd_build_extension_concepts)

    provenance_parser = subparsers.add_parser("build-provenance-index")
    provenance_parser.add_argument("--evidence", required=True, nargs="+", help="Input evidence JSONL files")
    provenance_parser.add_argument("--sqlite", required=True, help="Output SQLite provenance index")
    provenance_parser.add_argument(
        "--docs",
        nargs="+",
        default=[],
        help="Concept document JSONL files; when supplied, only provenance for displayed evidence bullets is indexed.",
    )
    provenance_parser.add_argument("--replace", action="store_true")
    provenance_parser.add_argument("--batch-size", type=int, default=25_000)
    provenance_parser.add_argument(
        "--sources-per-text",
        type=int,
        default=5,
        help="Maximum source citations to retain for each concept-document evidence bullet.",
    )
    provenance_parser.add_argument(
        "--max-document-items",
        type=int,
        default=None,
        help="When --docs is supplied, index only the first N evidence bullets per concept document.",
    )
    provenance_parser.set_defaults(func=cmd_build_provenance_index)

    embed_parser = subparsers.add_parser("embed")
    embed_parser.add_argument("--docs", required=True, help="Concept document JSONL")
    embed_parser.add_argument("--out", required=True, help="Output vector JSONL")
    embedding_providers = ["hashing", "sentence-transformers", "transformers-cls", "bert-cls", "sapbert"]
    embed_parser.add_argument("--provider", choices=embedding_providers, default="hashing")
    embed_parser.add_argument(
        "--model",
        help=(
            "Embedding model name. For transformers-cls/sapbert, defaults to "
            f"{DEFAULT_BIOMEDICAL_BERT_MODEL}."
        ),
    )
    embed_parser.add_argument("--dim", type=int, default=384, help="Hashing-vector dimension")
    embed_parser.add_argument("--batch-size", type=int, default=64)
    embed_parser.add_argument("--max-docs", type=int, help="Embed only the first N documents for quick iteration.")
    embed_parser.add_argument("--sample-docs", type=int, help="Embed a reproducible random sample of N documents.")
    embed_parser.add_argument("--seed", type=int, default=13, help="Seed used with --sample-docs.")
    embed_parser.add_argument(
        "--vector-precision",
        type=int,
        default=6,
        help="Decimal places to keep in JSON vectors. Use -1 for full precision.",
    )
    embed_parser.add_argument(
        "--omit-text",
        action="store_true",
        help="Do not duplicate concept-document text inside vector records.",
    )
    embed_parser.add_argument(
        "--include-document-metadata",
        action="store_true",
        help="Include original concept-document metadata inside each vector record.",
    )
    embed_parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load transformer models only from the local cache.",
    )
    embed_parser.add_argument(
        "--max-seq-length",
        type=int,
        help="Override transformer max sequence length.",
    )
    embed_parser.add_argument(
        "--device",
        default="auto",
        help="Torch device for transformers-cls/sapbert: auto, cpu, mps, or cuda.",
    )
    embed_parser.set_defaults(func=cmd_embed)

    compact_parser = subparsers.add_parser("compact-vectors")
    compact_parser.add_argument("--vectors", required=True, help="Input vector JSONL")
    compact_parser.add_argument("--out-prefix", required=True, help="Output prefix for manifest, metadata, and f32 files")
    compact_parser.set_defaults(func=cmd_compact_vectors)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("--vectors", required=True, help="Vector JSONL")
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--provider", choices=embedding_providers, default="hashing")
    search_parser.add_argument(
        "--model",
        help=(
            "Embedding model name. For transformers-cls/sapbert, defaults to "
            f"{DEFAULT_BIOMEDICAL_BERT_MODEL}."
        ),
    )
    search_parser.add_argument("--dim", type=int, default=384)
    search_parser.add_argument("--top-k", type=int, default=10)
    search_parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load transformer models only from the local cache.",
    )
    search_parser.add_argument(
        "--max-seq-length",
        type=int,
        help="Override transformer max sequence length.",
    )
    search_parser.add_argument(
        "--device",
        default="auto",
        help="Torch device for transformers-cls/sapbert: auto, cpu, mps, or cuda.",
    )
    search_parser.set_defaults(func=cmd_search)

    elastic_parser = subparsers.add_parser("export-elastic")
    elastic_parser.add_argument("--vectors", required=True, help="Vector JSONL")
    elastic_parser.add_argument("--index", required=True, help="Target Elasticsearch index name")
    elastic_parser.add_argument("--out-mapping", required=True, help="Output index mapping JSON")
    elastic_parser.add_argument("--out-bulk", required=True, help="Output bulk NDJSON")
    elastic_parser.add_argument("--vector-field", default="vector")
    elastic_parser.add_argument("--similarity", default="cosine", choices=["cosine", "dot_product", "l2_norm", "max_inner_product"])
    elastic_parser.add_argument("--no-index-vectors", action="store_true")
    elastic_parser.add_argument("--op-type", default="index", choices=["index", "create"])
    elastic_parser.add_argument("--shards", type=int, default=1)
    elastic_parser.add_argument("--replicas", type=int, default=0)
    elastic_parser.add_argument(
        "--bulk-docs-per-file",
        type=int,
        help="Split bulk NDJSON into part files with at most this many documents each.",
    )
    elastic_parser.set_defaults(func=cmd_export_elastic)

    load_elastic_parser = subparsers.add_parser("load-elastic")
    load_elastic_parser.add_argument("--url", default="http://localhost:9200")
    load_elastic_parser.add_argument("--index", required=True)
    load_elastic_parser.add_argument("--mapping", required=True)
    load_elastic_parser.add_argument("--bulk", required=True, nargs="+")
    load_elastic_parser.add_argument("--create-index", action="store_true")
    load_elastic_parser.add_argument("--delete-existing", action="store_true")
    load_elastic_parser.add_argument("--marker", help="Write marker file after a successful load")
    load_elastic_parser.add_argument(
        "--delete-bulk-after-load",
        action="store_true",
        help="Delete temporary bulk NDJSON files after a successful load.",
    )
    load_elastic_parser.set_defaults(func=cmd_load_elastic)

    alias_elastic_parser = subparsers.add_parser("alias-elastic")
    alias_elastic_parser.add_argument("--url", default="http://localhost:9200")
    alias_elastic_parser.add_argument("--index", required=True)
    alias_elastic_parser.add_argument("--alias", required=True)
    alias_elastic_parser.set_defaults(func=cmd_alias_elastic)

    delete_elastic_cuis_parser = subparsers.add_parser("delete-elastic-cuis")
    delete_elastic_cuis_parser.add_argument("--url", default="http://localhost:9200")
    delete_elastic_cuis_parser.add_argument("--index", required=True)
    delete_elastic_cuis_parser.add_argument("--cui", action="append", required=True)
    delete_elastic_cuis_parser.set_defaults(func=cmd_delete_elastic_cuis)

    search_elastic_parser = subparsers.add_parser("search-elastic")
    search_elastic_parser.add_argument("--url", default="http://localhost:9200")
    search_elastic_parser.add_argument("--index", required=True)
    search_elastic_parser.add_argument("--query", required=True)
    search_elastic_parser.add_argument("--vector-field", default="vector")
    search_elastic_parser.add_argument("--k", type=int, default=10)
    search_elastic_parser.add_argument("--num-candidates", type=int, default=100)
    search_elastic_parser.add_argument("--provider", choices=embedding_providers, default="hashing")
    search_elastic_parser.add_argument(
        "--model",
        help=(
            "Embedding model name. For transformers-cls/sapbert, defaults to "
            f"{DEFAULT_BIOMEDICAL_BERT_MODEL}."
        ),
    )
    search_elastic_parser.add_argument("--dim", type=int, default=384)
    search_elastic_parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load transformer models only from the local cache.",
    )
    search_elastic_parser.add_argument(
        "--max-seq-length",
        type=int,
        help="Override transformer max sequence length.",
    )
    search_elastic_parser.add_argument(
        "--device",
        default="auto",
        help="Torch device for transformers-cls/sapbert: auto, cpu, mps, or cuda.",
    )
    search_elastic_parser.set_defaults(func=cmd_search_elastic)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
