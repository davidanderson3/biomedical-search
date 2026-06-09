#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_JSON = ROOT / "build" / "source_dashboard" / "source_evidence_dashboard.json"
DEFAULT_OUT_HTML = ROOT / "docs" / "source_evidence_dashboard.html"


@dataclass
class BundleStats:
    key: str
    label: str
    status: str
    corpus_rows: int = 0
    evidence_rows: int = 0
    document_rows: int = 0
    vector_rows: int = 0
    manifest_count: int = 0
    corpus_files: list[str] = field(default_factory=list)
    evidence_files: list[str] = field(default_factory=list)
    document_files: list[str] = field(default_factory=list)
    vector_files: list[str] = field(default_factory=list)
    manifest_files: list[str] = field(default_factory=list)
    sample_sources: Counter = field(default_factory=Counter)
    sample_metadata_keys: Counter = field(default_factory=Counter)
    updated_at: float = 0.0
    notes: list[str] = field(default_factory=list)

    def stage_count(self) -> int:
        return sum(
            1
            for value in (
                self.corpus_rows,
                self.evidence_rows,
                self.document_rows,
                self.vector_rows,
            )
            if value > 0
        )

    def completion_fraction(self) -> float:
        return round(self.stage_count() / 4, 4)

    def to_json(self) -> dict[str, Any]:
        payload = {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "completion_fraction": self.completion_fraction(),
            "corpus_rows": self.corpus_rows,
            "evidence_rows": self.evidence_rows,
            "document_rows": self.document_rows,
            "vector_rows": self.vector_rows,
            "manifest_count": self.manifest_count,
            "sample_sources": dict(self.sample_sources.most_common(8)),
            "sample_metadata_keys": dict(self.sample_metadata_keys.most_common(12)),
            "updated_at": iso_timestamp(self.updated_at),
            "notes": self.notes,
            "files": {
                "corpus": self.corpus_files,
                "evidence": self.evidence_files,
                "documents": self.document_files,
                "vectors": self.vector_files,
                "manifests": self.manifest_files,
            },
        }
        return payload


@dataclass
class ProductStats:
    key: str
    label: str
    status: str
    corpus_rows: int = 0
    evidence_rows: int = 0
    document_rows: int = 0
    vector_rows: int = 0
    index_rows: int = 0
    bundle_keys: set[str] = field(default_factory=set)
    bundle_statuses: Counter = field(default_factory=Counter)
    files: dict[str, set[str]] = field(
        default_factory=lambda: {
            "corpus": set(),
            "evidence": set(),
            "documents": set(),
            "vectors": set(),
            "manifests": set(),
            "indexes": set(),
        }
    )
    index_artifacts: list[dict[str, Any]] = field(default_factory=list)
    sample_sources: Counter = field(default_factory=Counter)
    updated_at: float = 0.0
    notes: list[str] = field(default_factory=list)

    def stage_count(self) -> int:
        return sum(
            1
            for value in (
                self.corpus_rows,
                self.evidence_rows,
                self.document_rows,
                self.vector_rows,
            )
            if value > 0
        )

    def completion_fraction(self) -> float:
        return round(self.stage_count() / 4, 4)

    def to_json(self, bundle_lookup: dict[str, BundleStats]) -> dict[str, Any]:
        bundles = [
            bundle_lookup[key].to_json()
            for key in sorted(self.bundle_keys)
            if key in bundle_lookup
        ]
        return {
            "key": self.key,
            "label": self.label,
            "status": self.status,
            "completion_fraction": self.completion_fraction(),
            "corpus_rows": self.corpus_rows,
            "evidence_rows": self.evidence_rows,
            "document_rows": self.document_rows,
            "vector_rows": self.vector_rows,
            "index_rows": self.index_rows,
            "bundle_count": len(self.bundle_keys),
            "bundle_statuses": dict(self.bundle_statuses),
            "sample_sources": dict(self.sample_sources.most_common(8)),
            "source_review": product_review_metadata(self),
            "source_quality": product_source_quality(self),
            "updated_at": iso_timestamp(self.updated_at),
            "notes": self.notes,
            "files": {kind: sorted(paths) for kind, paths in self.files.items()},
            "index_artifacts": self.index_artifacts,
            "bundles": bundles,
        }


@dataclass
class CrossSourceConceptSupport:
    cui: str
    label: str
    score: float
    product_count: int
    primary_product_count: int
    reference_product_count: int
    supporting_rows: int
    total_weight: float
    products: list[dict[str, Any]]
    semantic_types: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "cui": self.cui,
            "label": self.label,
            "score": round(self.score, 2),
            "product_count": self.product_count,
            "primary_product_count": self.primary_product_count,
            "reference_product_count": self.reference_product_count,
            "linked_source_items": self.supporting_rows,
            "supporting_rows": self.supporting_rows,
            # Kept for compatibility with older dashboard payload consumers.
            "evidence_rows": self.supporting_rows,
            "total_weight": round(self.total_weight, 2),
            "products": self.products,
            "semantic_types": self.semantic_types,
            "why_supported": cross_source_reason(
                [str(product.get("key")) for product in self.products],
                self.primary_product_count,
                self.reference_product_count,
            ),
            "why_compelling": cross_source_reason(
                [str(product.get("key")) for product in self.products],
                self.primary_product_count,
                self.reference_product_count,
            ),
        }


PRODUCT_LABELS = {
    "pubmed": "PubMed",
    "europepmc": "Europe PMC",
    "pmc_oa": "PMC Open Access",
    "pubtator3": "PubTator3",
    "umls": "UMLS",
    "hpo": "HPO",
    "mondo": "MONDO",
    "openalex": "OpenAlex",
    "clinicaltrials_gov": "ClinicalTrials.gov",
    "dailymed": "DailyMed",
    "medlineplus": "MedlinePlus",
    "medlineplus_genetics": "MedlinePlus Genetics",
    "ncbi_bookshelf_oa": "NCBI Bookshelf OA",
    "cdc": "CDC",
    "fda": "FDA",
    "nci": "NCI",
    "niddk": "NIDDK",
    "wikipedia": "Wikipedia",
    "wikimedia": "Wikimedia",
    "drug_enrichment": "Drug Enrichment",
    "open_image": "Open Images",
    "extension": "Local Extension Concepts",
    "local_search_log": "Local Search Logs",
    "reviewed_notes": "Reviewed Snippets",
    "rxnorm": "RxNorm",
    "atc": "ATC",
    "drugbank": "DrugBank",
    "mthspl": "MTHSPL",
}

PRODUCT_ORDER = {
    # Evidence expansion priority: primary/reusable evidence first, reference
    # products and enrichment/evaluation-only artifacts later.
    "pubmed": 0,
    "pmc_oa": 1,
    "europepmc": 2,
    "pubtator3": 3,
    "dailymed": 4,
    "medlineplus": 5,
    "medlineplus_genetics": 6,
    "ncbi_bookshelf_oa": 7,
    "nci": 8,
    "fda": 9,
    "cdc": 10,
    "niddk": 11,
    "clinicaltrials_gov": 12,
    "hpo": 13,
    "mondo": 14,
    "umls": 15,
    "openalex": 16,
    "local_search_log": 17,
    "reviewed_notes": 18,
    "extension": 19,
    "drug_enrichment": 20,
    "wikipedia": 21,
    "wikimedia": 22,
    "open_image": 23,
}

CROSS_SOURCE_PRODUCT_WEIGHT: dict[str, float] = {
    "pubmed": 4.0,
    "pmc_oa": 4.0,
    "europepmc": 3.5,
    "dailymed": 3.0,
    "medlineplus": 2.75,
    "medlineplus_genetics": 2.75,
    "clinicaltrials_gov": 1.5,
    "ncbi_bookshelf_oa": 2.5,
    "nci": 2.25,
    "fda": 2.25,
    "cdc": 2.0,
    "niddk": 2.0,
    "hpo": 1.25,
    "mondo": 1.25,
}

CROSS_SOURCE_REFERENCE_PRODUCTS = {"hpo", "mondo"}
CROSS_SOURCE_PRIMARY_PRODUCTS = set(CROSS_SOURCE_PRODUCT_WEIGHT) - CROSS_SOURCE_REFERENCE_PRODUCTS
CROSS_SOURCE_EXCLUDED_PRODUCTS = {
    "umls",
    "openalex",
    "wikipedia",
    "wikimedia",
    "open_image",
    "drug_enrichment",
    "extension",
    "local_search_log",
    "reviewed_notes",
    "rxnorm",
    "atc",
    "drugbank",
    "mthspl",
}

DASHBOARD_EXCLUDED_PRODUCTS = {
    "wikipedia",
    "wikimedia",
    "open_image",
}

PUBLIC_NAME_SAB_PRIORITY = {
    "MSH": 0,
    "NCI": 1,
    "MEDLINEPLUS": 2,
    "HPO": 3,
    "RXNORM": 4,
    "GO": 5,
    "HGNC": 6,
    "LNC": 7,
    "CHV": 8,
}

PUBLIC_NAME_TTY_PRIORITY = {
    "MH": 0,
    "PT": 1,
    "PN": 2,
    "HT": 3,
    "SY": 4,
    "ENTRY": 5,
}

CROSS_SOURCE_ACTIONABLE_SEMANTIC_TYPES = {
    "Amino Acid, Peptide, or Protein",
    "Antibiotic",
    "Bacterium",
    "Biologically Active Substance",
    "Body Substance",
    "Cell",
    "Cell Component",
    "Clinical Attribute",
    "Clinical Drug",
    "Diagnostic Procedure",
    "Disease or Syndrome",
    "Enzyme",
    "Gene or Genome",
    "Hazardous or Poisonous Substance",
    "Hormone",
    "Immunologic Factor",
    "Laboratory Procedure",
    "Laboratory or Test Result",
    "Mental or Behavioral Dysfunction",
    "Molecular Function",
    "Neoplastic Process",
    "Organic Chemical",
    "Pathologic Function",
    "Pharmacologic Substance",
    "Sign or Symptom",
    "Therapeutic or Preventive Procedure",
    "Virus",
}

CROSS_SOURCE_GENERIC_SEMANTIC_TYPES = {
    "Body Location or Region",
    "Conceptual Entity",
    "Finding",
    "Functional Concept",
    "Geographic Area",
    "Health Care Activity",
    "Human",
    "Idea or Concept",
    "Intellectual Product",
    "Language",
    "Occupation or Discipline",
    "Organization",
    "Population Group",
    "Qualitative Concept",
    "Quantitative Concept",
    "Research Activity",
    "Spatial Concept",
    "Temporal Concept",
}

CROSS_SOURCE_GENERIC_LABELS = {
    "associated",
    "be",
    "changed status",
    "clinical trials as topic",
    "cells",
    "disease",
    "diseases",
    "do not",
    "exposure",
    "finding",
    "found",
    "healthcare",
    "humans",
    "increased risk",
    "kind",
    "laboratory procedure",
    "more than",
    "pharmaceutical preparations",
    "procedures",
    "diagnosis",
    "reporting",
    "response",
    "sign",
    "signs and symptoms",
    "site",
    "side effect",
    "surgical procedures operative",
    "symptom",
    "syndrome",
    "test",
    "therapeutics",
    "used by",
}


PRODUCT_REVIEW: dict[str, dict[str, str]] = {
    "pubmed": {
        "why": "Core biomedical literature source for clinical concepts, drug and disease associations, guidelines, case reports, and article-level provenance.",
        "evidence": "Current artifacts combine NCBI PubMed bulk baseline shards with smaller topic harvests. Evidence is kept with PubMed/source identifiers, then materialized into concept documents and vectors.",
        "next": "Promote the pilot to systematic coverage by defining the XML file range, refresh cadence, duplicate policy, and acceptance checks against the query evaluation set.",
    },
    "europepmc": {
        "why": "Complements PubMed with public literature records and open full-text opportunities, especially for topic areas where abstract-only evidence is thin.",
        "evidence": "Current artifacts are topic and scaling-chunk harvests selected from source acquisition queries, not a complete Europe PMC baseline.",
        "next": "Decide whether this becomes a systematic product. If yes, define query criteria, open-access/full-text rules, refresh cadence, and per-topic coverage checks.",
    },
    "pmc_oa": {
        "why": "Provides open-access full text for passage-level evidence that is richer than titles and abstracts.",
        "evidence": "Current artifacts come from topic/chunk harvests where PMC Open Access content is available and can be chunked into concept evidence.",
        "next": "Define the OA ingest scope, article license filters, deduplication against PubMed/Europe PMC, and passage-level relevance evaluation.",
    },
    "pubtator3": {
        "why": "NCBI literature-mined biomedical entity and relation annotations for PubMed and PMC content.",
        "evidence": "Current artifacts are a small relation sample from relation2pubtator3.gz, mapped to UMLS CUIs when possible and stored as relationship-edge evidence.",
        "next": "Evaluate the sampled relationship edges, decide which relation/entity types improve search, then expand with explicit caps and monthly refresh metadata.",
    },
    "umls": {
        "why": "Core terminology product for CUI lookup, labels, synonyms, source vocabulary codes, semantic types, definitions, and relationship context.",
        "evidence": "Current artifacts are SQLite reference indexes built from UMLS-derived label, semantic type, definition, and relationship data. They support retrieval and ranking but are not source corpus passages.",
        "next": "Record the UMLS release and level-0/source eligibility policy in the dashboard payload, then split public-display-safe labels from backend-only restricted labels.",
    },
    "hpo": {
        "why": "Authoritative phenotype ontology used for phenotype labels, synonyms, definitions, and disease-phenotype context.",
        "evidence": "Ontology labels, synonyms, definitions, cross-references, and relationships are transformed into reference evidence rather than real-world observational evidence.",
        "next": "Pin the HPO release, validate label/synonym/relationship coverage, and add checks that public display names do not expose restricted preferred names.",
    },
    "mondo": {
        "why": "Disease ontology used for disease normalization, labels, synonyms, definitions, cross-references, and disease hierarchy context.",
        "evidence": "Ontology labels, synonyms, definitions, cross-references, and relationships are transformed into reference evidence rather than real-world observational evidence.",
        "next": "Pin the MONDO release, validate disease synonym and relationship coverage, and check disease-name fallbacks used in public search results.",
    },
    "clinicaltrials_gov": {
        "why": "Useful only when restricted to posted trial outcome results. Trial registration, recruitment, eligibility, and planned endpoint text are context, not evidence that an intervention works.",
        "evidence": "Current artifacts may include legacy registry-context subsets; evidence-bearing rebuilds should use posted outcome-result fields from studies with hasResults and outcomeMeasuresModule.",
        "next": "Rebuild the sample in outcomes-only mode, exclude protocol-only studies from ranking evidence, and evaluate whether extracted outcome values improve treatment and intervention queries.",
    },
    "dailymed": {
        "why": "Public SPL drug-label source for medications, indications, contraindications, warnings, adverse reactions, and dosage context.",
        "evidence": "Current artifacts are subset/demo labels plus selected acquisition rounds, chunked into source-specific concept evidence.",
        "next": "Move to a full DailyMed/SPL ingest, weight label sections, map to RxNorm where possible, and evaluate drug-query retrieval separately.",
    },
    "medlineplus": {
        "why": "NIH consumer health reference source that gives readable disease, drug, and procedure context.",
        "evidence": "Current artifacts include a full MedlinePlus health-topic XML snapshot linked into concept evidence and vectors.",
        "next": "Record the source XML URL/date in release manifests, define refresh cadence, and evaluate whether consumer-language evidence should be ranked separately from literature evidence.",
    },
    "medlineplus_genetics": {
        "why": "NIH genetics reference source for gene, condition, inheritance, and molecular context.",
        "evidence": "Current artifacts are selected genetics pages and acquisition outputs, chunked into concept documents and vectors.",
        "next": "Define full source coverage, gene/condition mapping checks, release/version tracking, and genetics-specific query evaluation.",
    },
    "ncbi_bookshelf_oa": {
        "why": "Open NCBI Bookshelf chapters provide review-style background for biomedical concepts and clinical topics.",
        "evidence": "Current artifacts are open-access subset/demo chapters selected for public demo coverage.",
        "next": "Define which books/chapters qualify, license filters, refresh process, and passage-level relevance checks.",
    },
    "cdc": {
        "why": "Public health reference pages provide guidance and epidemiology context for selected conditions and prevention topics.",
        "evidence": "Current artifacts are curated subset/demo pages and source acquisition outputs.",
        "next": "Build a URL inventory from CDC collections or sitemaps, add page-version tracking, and evaluate public-health queries separately.",
    },
    "fda": {
        "why": "Public regulatory reference pages provide safety, device, drug, and approval context.",
        "evidence": "Current artifacts are curated subset/demo pages and source acquisition outputs.",
        "next": "Define eligible FDA collections, capture stable URLs and dates, and separate regulatory evidence from clinical literature evidence in evaluation.",
    },
    "nci": {
        "why": "Cancer reference source for disease, treatment, staging, and terminology context.",
        "evidence": "Current artifacts are curated subset/demo pages and selected acquisition outputs.",
        "next": "Define the cancer-topic inventory, page freshness checks, and oncology-specific retrieval judgments.",
    },
    "niddk": {
        "why": "NIH reference source for digestive, kidney, endocrine, metabolic, and urologic conditions.",
        "evidence": "Current artifacts are curated subset/demo pages and selected acquisition outputs.",
        "next": "Define the page inventory, update cadence, and source-specific query coverage before treating it as systematic.",
    },
    "openalex": {
        "why": "Citation and metadata enrichment source for identifying high-value literature gaps and prioritizing candidate records.",
        "evidence": "Current artifacts are enrichment snapshots, not primary biomedical source material for source-quality claims.",
        "next": "Use this to drive PubMed/PMC gap-filling, then evaluate the resulting literature evidence rather than ranking OpenAlex text as primary evidence.",
    },
    "wikipedia": {
        "why": "General background enrichment that can expose alternate phrasing and broad topic context.",
        "evidence": "Current artifacts are small enrichment snapshots and should not be treated as authoritative biomedical evidence.",
        "next": "Keep disabled or clearly separated for public demos unless a reviewed use case justifies it.",
    },
    "wikimedia": {
        "why": "Media/background enrichment for non-textual or descriptive context.",
        "evidence": "Current artifacts are enrichment snapshots, not primary biomedical evidence.",
        "next": "Keep separate from search-quality claims and define a media-specific evaluation before expanding.",
    },
    "open_image": {
        "why": "Image enrichment for visual concepts or demonstrations where media context is useful.",
        "evidence": "Current artifacts are enrichment snapshots, not primary biomedical evidence.",
        "next": "Keep separate from evidence ranking unless a reviewed image-retrieval task is added.",
    },
    "extension": {
        "why": "Local extension concepts preserve reviewed additions or public-safe concept material not covered by source products.",
        "evidence": "Evidence is locally generated or curated and should require explicit provenance before source-quality claims.",
        "next": "Add a registry for each extension with provenance, reviewer, public-display eligibility, and expiration/review date.",
    },
    "local_search_log": {
        "why": "Logged local queries help identify coverage gaps and evaluate realistic demo behavior.",
        "evidence": "Evidence is query-derived and should be used for evaluation planning, not as biomedical source evidence.",
        "next": "Convert useful queries into a reviewed benchmark set with expected concepts and source expectations.",
    },
    "reviewed_notes": {
        "why": "Reviewed snippets capture human assessment and qualitative observations about evidence quality.",
        "evidence": "Evidence is manually reviewed local notes, not an external source product.",
        "next": "Attach reviewer, date, source artifact, and decision labels so notes become auditable evaluation data.",
    },
}

STATUS_QUALITY: dict[str, dict[str, str]] = {
    "systematic_pilot": {
        "label": "High / pilot",
        "level": "quality_high",
        "reason": "Authoritative source evidence with provenance, but local coverage and refresh rules are still pilot-stage.",
    },
    "systematic_snapshot": {
        "label": "High",
        "level": "quality_high",
        "reason": "Systematic source snapshot with concrete provenance; ranking impact still needs source-specific evaluation.",
    },
    "ontology_reference": {
        "label": "Reference",
        "level": "quality_reference",
        "reason": "Strong for terminology, labels, definitions, and relationships; not primary clinical or literature evidence.",
    },
    "topic_harvest": {
        "label": "Medium",
        "level": "quality_medium",
        "reason": "Useful evidence from a credible source, but acquisition is topic-limited and incomplete.",
    },
    "subset_demo": {
        "label": "Medium / subset",
        "level": "quality_medium",
        "reason": "Source can be credible, but current artifacts are bounded subsets or demo slices.",
    },
    "mixed_public_bundle": {
        "label": "Mixed",
        "level": "quality_medium",
        "reason": "Combines multiple public products; inspect product-level rows before making source-specific claims.",
    },
    "enrichment_snapshot": {
        "label": "Enrichment",
        "level": "quality_enrichment",
        "reason": "Useful for discovery, prioritization, or background; not primary biomedical evidence.",
    },
    "restricted_private": {
        "label": "Restricted",
        "level": "quality_needs_review",
        "reason": "Not appropriate for public evidence claims without explicit licensing and access controls.",
    },
    "unclassified": {
        "label": "Needs review",
        "level": "quality_needs_review",
        "reason": "Evidence quality cannot be claimed until the source is registered with selection rules and acceptance criteria.",
    },
}

PRODUCT_QUALITY: dict[str, dict[str, str]] = {
    "pubmed": {
        "label": "High / pilot",
        "level": "quality_high",
        "reason": "Peer-reviewed literature metadata with PMID provenance; local ingest is still a baseline pilot plus topic harvests.",
    },
    "europepmc": {
        "label": "High source / partial",
        "level": "quality_medium",
        "reason": "Credible literature source, but current evidence is topic/chunk selected rather than a complete baseline.",
    },
    "pmc_oa": {
        "label": "High source / partial",
        "level": "quality_medium",
        "reason": "Open-access full text can be strong passage evidence; current ingest is topic/chunk limited.",
    },
    "pubtator3": {
        "label": "Literature-mined / sample",
        "level": "quality_medium",
        "reason": "NCBI automated relation annotations are high-value candidates, but they need evaluation before being treated as reviewed relationship evidence.",
    },
    "umls": {
        "label": "Reference",
        "level": "quality_reference",
        "reason": "Core terminology reference for labels, identifiers, definitions, semantic types, and relationships; not outcome evidence.",
    },
    "hpo": {
        "label": "Reference",
        "level": "quality_reference",
        "reason": "Authoritative phenotype ontology; high-quality normalization evidence, not clinical observation.",
    },
    "mondo": {
        "label": "Reference",
        "level": "quality_reference",
        "reason": "Authoritative disease ontology; high-quality normalization evidence, not clinical observation.",
    },
    "clinicaltrials_gov": {
        "label": "Outcomes only / candidate",
        "level": "quality_needs_review",
        "reason": "Posted trial outcomes can be useful candidate evidence; registry/protocol text is not efficacy evidence and should not drive ranking.",
    },
    "dailymed": {
        "label": "Regulatory / subset",
        "level": "quality_medium",
        "reason": "Authoritative SPL drug-label text; current artifacts are selected labels rather than full DailyMed coverage.",
    },
    "medlineplus": {
        "label": "High",
        "level": "quality_high",
        "reason": "Authoritative NLM consumer-health XML snapshot with source provenance; best for patient-language context.",
    },
    "medlineplus_genetics": {
        "label": "High source / subset",
        "level": "quality_medium",
        "reason": "Authoritative genetics summaries, but current coverage is still subset/acquisition based.",
    },
    "ncbi_bookshelf_oa": {
        "label": "High source / subset",
        "level": "quality_medium",
        "reason": "Open NCBI Bookshelf chapters can be strong review-style evidence; current coverage is bounded.",
    },
    "cdc": {
        "label": "Authoritative / subset",
        "level": "quality_medium",
        "reason": "Authoritative public-health pages, currently represented by selected reference pages.",
    },
    "fda": {
        "label": "Authoritative / subset",
        "level": "quality_medium",
        "reason": "Authoritative regulatory pages, currently represented by selected reference pages.",
    },
    "nci": {
        "label": "Authoritative / subset",
        "level": "quality_medium",
        "reason": "Authoritative cancer reference pages, currently represented by selected pages.",
    },
    "niddk": {
        "label": "Authoritative / subset",
        "level": "quality_medium",
        "reason": "Authoritative NIH reference pages, currently represented by selected pages.",
    },
    "openalex": {
        "label": "Enrichment",
        "level": "quality_enrichment",
        "reason": "Citation and metadata enrichment should guide source selection, not act as primary biomedical evidence.",
    },
    "wikipedia": {
        "label": "Background only",
        "level": "quality_enrichment",
        "reason": "Useful for general phrasing, but not authoritative biomedical evidence.",
    },
    "wikimedia": {
        "label": "Background only",
        "level": "quality_enrichment",
        "reason": "Media/background context only; not biomedical evidence.",
    },
    "open_image": {
        "label": "Background only",
        "level": "quality_enrichment",
        "reason": "Image enrichment only; not biomedical evidence.",
    },
    "extension": {
        "label": "Needs provenance",
        "level": "quality_needs_review",
        "reason": "Local extension evidence needs explicit provenance, review ownership, and public-display eligibility.",
    },
    "local_search_log": {
        "label": "Evaluation only",
        "level": "quality_needs_review",
        "reason": "Search logs are useful for benchmark design, not source evidence.",
    },
    "reviewed_notes": {
        "label": "Manual review",
        "level": "quality_needs_review",
        "reason": "Reviewed snippets need reviewer/date/source linkage before becoming auditable evidence.",
    },
}

STATUS_REVIEW: dict[str, dict[str, str]] = {
    "systematic_pilot": {
        "why": "Candidate systematic source with concrete artifacts and enough coverage to evaluate.",
        "evidence": "Evidence is selected from source-specific artifacts and linked into corpus, evidence, document, and vector stages when available.",
        "next": "Define complete source scope, refresh cadence, and acceptance tests before calling it systematic production coverage.",
    },
    "systematic_snapshot": {
        "why": "Systematic source snapshot with concrete artifacts and a defined acquisition point.",
        "evidence": "Evidence is selected from source-specific artifacts and linked into corpus, evidence, document, and vector stages when available.",
        "next": "Track source release/date, rerun evaluations, and document refresh behavior.",
    },
    "mixed_public_bundle": {
        "why": "Public-safe mixed artifact useful for demo assembly and cross-source inspection.",
        "evidence": "Evidence is selected from several permitted public products, so row-level drilldown is required before making source-specific claims.",
        "next": "Break mixed artifacts back into product-specific outputs or keep them only as derived serving artifacts.",
    },
    "enrichment_snapshot": {
        "why": "Supplemental source that may help discover, prioritize, or explain evidence.",
        "evidence": "Evidence is selected from enrichment snapshots and should not be treated as primary biomedical evidence.",
        "next": "Evaluate separately and promote only if the source has a clear product role and source-specific acceptance criteria.",
    },
    "ontology_reference": {
        "why": "Reference source useful for normalization, labels, synonyms, definitions, and relationships.",
        "evidence": "Evidence is selected from ontology/reference records rather than observational or literature evidence.",
        "next": "Pin source releases and validate label, synonym, and relationship coverage.",
    },
    "topic_harvest": {
        "why": "Targeted harvest useful for iteration and gap-filling.",
        "evidence": "Evidence is selected by topic/source-acquisition queries, so it is intentionally incomplete.",
        "next": "Either formalize the product as systematic coverage or label it as a topic-specific supplement.",
    },
    "subset_demo": {
        "why": "Small public source subset useful for demos and pipeline testing.",
        "evidence": "Evidence is selected from curated subsets or small acquisition rounds, not full-source coverage.",
        "next": "Define full-source acquisition and evaluation if the product should support source-quality claims.",
    },
    "unclassified": {
        "why": "Detected artifact without a source registry entry.",
        "evidence": "Evidence selection is inferred from filenames and row metadata.",
        "next": "Add a source registry entry with inclusion rationale, selection rules, and acceptance criteria.",
    },
}


def product_review_metadata(product: ProductStats) -> dict[str, str]:
    review = STATUS_REVIEW.get(product.status, STATUS_REVIEW["unclassified"]).copy()
    review.update(PRODUCT_REVIEW.get(product.key, {}))
    return review


def product_source_quality(product: ProductStats) -> dict[str, str]:
    quality = STATUS_QUALITY.get(product.status, STATUS_QUALITY["unclassified"]).copy()
    quality.update(PRODUCT_QUALITY.get(product.key, {}))
    return quality


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def iso_timestamp(value: float) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(microsecond=0).isoformat()


def count_lines(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def sample_jsonl(path: Path, limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if len(rows) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def normalized_source_key(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    return re.sub(r"[^a-z0-9_]+", "_", text).strip("_")


def product_key_for_source(value: object) -> str:
    source = normalized_source_key(value)
    if not source:
        return ""
    if "mimic" in source:
        return ""
    aliases = {
        "umls_label": "umls",
        "umls_labels": "umls",
        "umls_index": "umls",
        "umls_definition": "umls",
        "umls_definitions": "umls",
        "umls_semantic_type": "umls",
        "umls_semantic_types": "umls",
        "umls_related_concepts": "umls",
        "umls_research_relations": "umls",
        "clinicaltrials": "clinicaltrials_gov",
        "pubtator": "pubtator3",
        "pubtator3_relation_sample": "pubtator3",
        "bookshelf_oa": "ncbi_bookshelf_oa",
        "ncbi_bookshelf": "ncbi_bookshelf_oa",
        "openalex_top_cited": "openalex",
        "openalex_missing_high_citation": "openalex",
        "pmc": "pmc_oa",
        "existing_concept_documents": "extension",
        "extension_concept": "extension",
        "local_extension": "extension",
        "query": "local_search_log",
        "snippet": "reviewed_notes",
    }
    if source in aliases:
        return aliases[source]
    if source.startswith("pubmed_bulk") or source.startswith("pubmed_"):
        return "pubmed"
    if source.startswith("pubtator"):
        return "pubtator3"
    if source.startswith("europepmc"):
        return "europepmc"
    if source.startswith("pmc_oa"):
        return "pmc_oa"
    if source.startswith("openalex"):
        return "openalex"
    if source.startswith("umls_"):
        return "umls"
    if source.startswith("clinicaltrials"):
        return "clinicaltrials_gov"
    if source.startswith("dailymed"):
        return "dailymed"
    if source.startswith("medlineplus_genetics"):
        return "medlineplus_genetics"
    if source.startswith("medlineplus"):
        return "medlineplus"
    if source.startswith("ncbi_bookshelf"):
        return "ncbi_bookshelf_oa"
    for product in (
        "hpo",
        "mondo",
        "cdc",
        "fda",
        "nci",
        "niddk",
        "rxnorm",
        "atc",
        "drugbank",
        "mthspl",
    ):
        if source == product or source.startswith(f"{product}_"):
            return product
    if source.startswith("wikipedia"):
        return "wikipedia"
    if source.startswith("wikimedia"):
        return "wikimedia"
    if source in PRODUCT_LABELS:
        return source
    return ""


def product_label_for_key(key: str) -> str:
    return PRODUCT_LABELS.get(key, key.replace("_", " ").strip().title())


def product_key_for_path(path: Path, root: Path) -> str:
    text = rel(path, root).lower()
    name = path.name.lower()
    parent = path.parent.name.lower()
    if path.suffix == ".sqlite" and (
        name.startswith("umls_")
        or name.startswith("qe_umls_")
        or "/profile_indexes/umls_" in text
    ):
        return "umls"
    if "pubmed_bulk" in text or "/pubmed_" in text or name.startswith("pubmed_"):
        return "pubmed"
    if "pubtator" in text:
        return "pubtator3"
    if "europepmc" in text:
        return "europepmc"
    if "pmc_oa" in text:
        return "pmc_oa"
    if "hpo" in text:
        return "hpo"
    if "mondo" in text:
        return "mondo"
    if "clinicaltrials" in text:
        return "clinicaltrials_gov"
    if "dailymed" in text:
        return "dailymed"
    if "medlineplus_genetics" in text:
        return "medlineplus_genetics"
    if "medlineplus" in text:
        return "medlineplus"
    if "bookshelf_oa" in text or "ncbi_bookshelf" in text:
        return "ncbi_bookshelf_oa"
    if "/cdc" in text or name.startswith("cdc_"):
        return "cdc"
    if "/fda" in text or name.startswith("fda_"):
        return "fda"
    if "/nci" in text or name.startswith("nci_"):
        return "nci"
    if "/niddk" in text or name.startswith("niddk_"):
        return "niddk"
    if "openalex" in text:
        return "openalex"
    if "wikipedia" in text:
        return "wikipedia"
    if "wikimedia" in text:
        return "wikimedia"
    if "drug_enrichment" in text:
        return "drug_enrichment"
    if "open_image" in text:
        return "open_image"
    if "extension" in text or "new_umls_iterations" in text:
        return "extension"
    if parent.startswith("profile_evidence_"):
        return product_key_for_source(parent.removeprefix("profile_evidence_"))
    return product_key_for_source(bundle_key(path, root))


def product_key_from_line_prefix(prefix: bytes, kind: str) -> str:
    if kind in {"documents", "vectors"}:
        match = re.search(rb'"view"\s*:\s*"([^"]+)"', prefix)
        if match:
            return product_key_for_source(match.group(1).decode("utf-8", errors="replace"))
        match = re.search(rb'"doc_id"\s*:\s*"[^":]+:([^"_"]+)', prefix)
        if match:
            return product_key_for_source(match.group(1).decode("utf-8", errors="replace"))
    match = re.search(rb'"source"\s*:\s*"([^"]+)"', prefix)
    if match:
        return product_key_for_source(match.group(1).decode("utf-8", errors="replace"))
    return ""


def product_counts_for_file(path: Path, kind: str, root: Path) -> tuple[Counter, int]:
    counts: Counter = Counter()
    rows = 0
    fallback = product_key_for_path(path, root)
    with path.open("rb") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows += 1
            key = product_key_from_line_prefix(line[:1200], kind) or fallback
            if key:
                counts[key] += 1
    if rows and not counts and fallback:
        counts[fallback] = rows
    return counts, rows


UMLS_INDEX_TABLES = {
    "labels": "Labels",
    "semantic_types": "Semantic types",
    "concept_definitions": "Definitions",
    "related_concepts": "Related concepts",
    "research_relations": "Research relations",
}

UMLS_INDEX_PATTERNS = (
    "build/umls_*label_index.sqlite",
    "build/umls_*multiword_label_index.sqlite",
    "build/profile_indexes/umls_*_profile_multiword_label_index.sqlite",
    "build/umls_semantic_types.sqlite",
    "build/umls_definitions.sqlite",
    "build/umls_related_concepts.sqlite",
    "build/umls_research_relations.sqlite",
)


def discover_umls_index_paths(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in UMLS_INDEX_PATTERNS:
        for path in root.glob(pattern):
            if path.is_file() and path.suffix == ".sqlite":
                paths.add(path)
    return sorted(paths)


def sqlite_table_row_counts(path: Path) -> list[dict[str, Any]]:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        tables = {
            str(row[0])
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }
        rows: list[dict[str, Any]] = []
        for table, label in UMLS_INDEX_TABLES.items():
            if table not in tables:
                continue
            try:
                count = int(conn.execute(f"select count(*) from {table}").fetchone()[0])
            except sqlite3.Error:
                continue
            if count:
                rows.append({"table": table, "label": label, "rows": count})
        return rows
    finally:
        conn.close()


def umls_index_label_for_path(path: Path) -> str:
    name = path.stem
    if name == "umls_definitions":
        return "UMLS definitions index"
    if name == "umls_semantic_types":
        return "UMLS semantic types index"
    if name == "umls_related_concepts":
        return "UMLS related concepts index"
    if name == "umls_research_relations":
        return "UMLS research relations index"
    if "profile_multiword_label_index" in name:
        profile = (
            name.removeprefix("umls_")
            .removesuffix("_profile_multiword_label_index")
            .replace("_", " ")
        )
        return f"UMLS {profile} profile label index"
    return name.replace("_", " ").title()


def bundle_key(path: Path, root: Path) -> str:
    text = rel(path, root)
    name = path.name
    parent = path.parent.name

    source_subset_match = re.search(r"build/public/source_subsets/([^/]+)/", text)
    if source_subset_match:
        source_key = source_subset_match.group(1)
        return {
            "bookshelf_oa": "ncbi_bookshelf_oa",
        }.get(source_key, source_key)

    public_source_match = re.match(
        r"build/public/(bookshelf_oa|cdc|clinicaltrials|dailymed|fda|hpo|medlineplus|medlineplus_genetics|mondo|nci|niddk)",
        text,
    )
    if public_source_match:
        source_key = public_source_match.group(1)
        return {
            "bookshelf_oa": "ncbi_bookshelf_oa",
        }.get(source_key, source_key)

    scaling_match = re.search(
        r"(?:pubmed_|europepmc_|pmc_oa_)?"
        r"(scaling_chunk_\d+_[a-z0-9]+(?:_[a-z0-9]+)*?)"
        r"(?:_corpus|_concept|_materialized|/|$)",
        text,
        flags=re.IGNORECASE,
    )
    if scaling_match:
        return scaling_match.group(1)

    for pattern in (
        r"pubmed_bulk_recent_(baseline|next2|\d+_\d+)",
        r"openalex_top_cited",
        r"permitted_sources",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(0)

    if text.startswith("build/public/"):
        return re.sub(r"(_sample)?_corpus\.jsonl$", "", name)
    if parent.startswith("profile_evidence_"):
        return parent.removeprefix("profile_evidence_")
    if name.endswith("_concept_documents.jsonl"):
        return name.removesuffix("_concept_documents.jsonl")
    if "_concept_vectors" in name:
        return name.split("_concept_vectors", 1)[0]
    if name.endswith("_corpus.jsonl"):
        return name.removesuffix("_corpus.jsonl")
    if name.endswith("_evidence.jsonl"):
        return name.removesuffix("_evidence.jsonl")
    if name.endswith("_manifest.json"):
        return name.removesuffix("_manifest.json")
    return path.stem


def status_for_bundle(key: str, sources: Counter) -> tuple[str, list[str]]:
    text = key.lower()
    source_names = {str(source).lower() for source in sources}
    notes: list[str] = []

    if text in {"medlineplus_full", "medlineplus_all"}:
        notes.append("Full MedlinePlus health-topic XML snapshot with source XML provenance.")
        return "systematic_snapshot", notes
    if text.startswith("pubmed_bulk_recent"):
        notes.append("NCBI PubMed baseline shard with source XML provenance.")
        return "systematic_pilot", notes
    if "permitted_sources" in text:
        notes.append("Mixed public-source bundle; inspect child corpus files before source claims.")
        return "mixed_public_bundle", notes
    if "openalex" in text:
        notes.append("Citation-derived enrichment snapshot; evaluate separately from primary evidence.")
        return "enrichment_snapshot", notes
    if "pubtator" in text:
        notes.append("PubTator3 relation sample; useful for relationship-evidence evaluation, not systematic coverage yet.")
        return "subset_demo", notes
    if any(source in source_names for source in {"hpo", "mondo"}) or text.startswith(("hpo_", "mondo_")):
        notes.append("Ontology/reference text, useful for normalization but not real-world evidence.")
        return "ontology_reference", notes
    public_subset_sources = {
        "cdc",
        "clinicaltrials_gov",
        "dailymed",
        "fda",
        "medlineplus",
        "medlineplus_genetics",
        "nci",
        "ncbi_bookshelf_oa",
        "niddk",
    }
    if (
        "subset" in text
        or text.endswith("_sample")
        or any("subset" in source for source in source_names)
        or bool(source_names & public_subset_sources)
        or text in {"cdc", "clinicaltrials", "dailymed", "fda", "medlineplus", "nci", "niddk"}
    ):
        if "clinicaltrials_gov" in source_names or "clinicaltrials" in text:
            notes.append("ClinicalTrials.gov subset; treat only posted outcome results as evidence-bearing.")
        else:
            notes.append("Subset/demo scale; do not claim systematic source coverage.")
        return "subset_demo", notes
    if "scaling_chunk" in text or "topics" in text or source_names & {"pubmed", "europepmc", "pmc_oa"}:
        notes.append("Topic/chunk harvest; useful for iteration, not systematic corpus coverage.")
        return "topic_harvest", notes
    return "unclassified", ["Needs registry entry before being treated as systematic evidence."]


def label_for_key(key: str) -> str:
    labels = {
        "pubmed_bulk_recent_baseline": "PubMed bulk baseline pilot",
        "pubmed_bulk_recent_next2": "PubMed bulk next two files",
        "permitted_sources": "Permitted public sources bundle",
        "openalex_top_cited": "OpenAlex top-cited enrichment",
    }
    if key in labels:
        return labels[key]
    return key.replace("_", " ").strip().title()


def artifact_kind(path: Path) -> str:
    name = path.name
    parent = path.parent.name
    if name.endswith("_corpus.jsonl"):
        return "corpus"
    if name.endswith("_concept_documents.jsonl"):
        return "documents"
    if "_concept_vectors" in name and name.endswith(".jsonl"):
        return "vectors"
    if name.endswith("_manifest.json") or name == "manifest.json":
        return "manifest"
    if parent.startswith("profile_evidence") or name.endswith("_evidence.jsonl"):
        return "evidence"
    return ""


def discover_artifact_paths(root: Path) -> list[Path]:
    patterns = [
        "build/**/*_corpus.jsonl",
        "build/**/*_evidence.jsonl",
        "build/**/*_concept_documents.jsonl",
        "build/**/*_concept_vectors*.jsonl",
        "build/**/*_manifest.json",
        "build/**/manifest.json",
    ]
    paths: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if path.is_file():
                paths.add(path)
    return sorted(paths)


def normalized_cui(value: object) -> str:
    text = str(value or "").strip().upper()
    if re.fullmatch(r"C\d{7}", text):
        return text
    return ""


def product_key_for_concept_row(row: dict[str, Any], path: Path, root: Path) -> str:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    candidates: list[object] = [
        metadata.get("source_bundle"),
        metadata.get("source_subset_prefix"),
        row.get("source"),
        row.get("view"),
    ]
    sources = row.get("sources")
    if isinstance(sources, list):
        candidates.extend(sources)
    elif sources:
        candidates.append(sources)

    doc_id = str(row.get("doc_id") or "")
    if ":" in doc_id:
        candidates.append(doc_id.split(":", 1)[1])

    for candidate in candidates:
        product = product_key_for_source(candidate)
        if product:
            return product
    return product_key_for_path(path, root)


def numeric_count(value: object, default: int = 0) -> int:
    try:
        return max(int(float(value)), default)
    except (TypeError, ValueError):
        return default


def numeric_weight(value: object, default: float = 0.0) -> float:
    try:
        return max(float(value), default)
    except (TypeError, ValueError):
        return default


def clean_concept_label(value: object, cui: str = "") -> str:
    label = re.sub(r"\s+", " ", str(value or "")).strip()
    if not label:
        return ""
    if cui and label.upper() == cui:
        return ""
    if "^" in label:
        return ""
    if len(label) > 120:
        return ""
    if any(ord(char) < 32 for char in label):
        return ""
    return label


def normalized_label_key(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def cross_source_candidate_is_actionable(label: str, semantic_types: list[str]) -> bool:
    label_key = normalized_label_key(label)
    if not label_key or label_key in CROSS_SOURCE_GENERIC_LABELS:
        return False
    if re.fullmatch(r"c\d{7}", label_key):
        return False
    if "little" in label_key.split():
        return False
    if label_key.endswith(" as topic"):
        return False
    if not semantic_types:
        return True
    if any(sty in CROSS_SOURCE_ACTIONABLE_SEMANTIC_TYPES for sty in semantic_types):
        return True
    if all(sty in CROSS_SOURCE_GENERIC_SEMANTIC_TYPES for sty in semantic_types):
        return False
    return False


def load_display_name_overrides(root: Path) -> dict[str, str]:
    path = root / "config" / "display_name_overrides.tsv"
    overrides: dict[str, str] = {}
    if not path.is_file():
        return overrides
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t", 1)
                if len(parts) != 2 or parts[0].lower() == "cui":
                    continue
                cui = normalized_cui(parts[0])
                label = clean_concept_label(parts[1], cui)
                if cui and label:
                    overrides[cui] = label
    except OSError:
        return {}
    return overrides


def label_sort_key(row: tuple[str, str, str, str, str]) -> tuple[int, int, int, int, int, int, str]:
    label, sab, tty, ispref, _suppress = row
    sab_rank = PUBLIC_NAME_SAB_PRIORITY.get(str(sab).upper(), 999)
    tty_rank = PUBLIC_NAME_TTY_PRIORITY.get(str(tty).upper(), 99)
    preferred_rank = 0 if str(ispref).upper() == "Y" else 1
    upper_penalty = 1 if label.isupper() and len(label) > 6 else 0
    punctuation_penalty = 1 if re.search(r"[,;/]", label) else 0
    return (
        sab_rank,
        tty_rank,
        punctuation_penalty,
        preferred_rank,
        upper_penalty,
        len(label),
        label.lower(),
    )


def load_public_display_labels(root: Path, cuis: list[str]) -> dict[str, str]:
    overrides = load_display_name_overrides(root)
    labels = {cui: label for cui, label in overrides.items() if cui in set(cuis)}
    missing = [cui for cui in cuis if cui not in labels]
    if not missing:
        return labels

    index_path = root / "build" / "umls_biomedicine_search_label_index.sqlite"
    if not index_path.is_file():
        return labels

    try:
        conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return labels

    try:
        for cui in missing:
            try:
                rows = [
                    (
                        clean_concept_label(row[0], cui),
                        str(row[1] or "").upper(),
                        str(row[2] or "").upper(),
                        str(row[3] or "").upper(),
                        str(row[4] or "").upper(),
                    )
                    for row in conn.execute(
                        """
                        select label, sab, tty, ispref, suppress
                        from labels
                        where cui = ? and suppress = 'N'
                        """,
                        (cui,),
                    )
                ]
            except sqlite3.Error:
                continue
            public_rows = [
                row
                for row in rows
                if row[0] and row[1] in PUBLIC_NAME_SAB_PRIORITY
            ]
            if public_rows:
                labels[cui] = sorted(public_rows, key=label_sort_key)[0][0]
    finally:
        conn.close()
    return labels


def load_semantic_types(root: Path, cuis: list[str]) -> dict[str, list[str]]:
    index_path = root / "build" / "umls_semantic_types.sqlite"
    semantic_types: dict[str, list[str]] = defaultdict(list)
    if not cuis or not index_path.is_file():
        return semantic_types
    try:
        conn = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return semantic_types
    try:
        placeholders = ",".join("?" for _ in cuis)
        query = (
            "select cui, sty from semantic_types "
            f"where cui in ({placeholders}) order by cui, sty"
        )
        for cui, sty in conn.execute(query, cuis):
            label = clean_concept_label(sty)
            if label and label not in semantic_types[str(cui)]:
                semantic_types[str(cui)].append(label)
    except sqlite3.Error:
        return semantic_types
    finally:
        conn.close()
    return semantic_types


def cross_source_reason(
    products: list[str],
    primary_product_count: int,
    reference_product_count: int,
) -> str:
    product_set = set(products)
    signals = []
    if product_set & {"pubmed", "pmc_oa", "europepmc"}:
        signals.append("literature")
    if product_set & {"dailymed", "fda"}:
        signals.append("regulatory")
    if product_set & {
        "medlineplus",
        "medlineplus_genetics",
        "ncbi_bookshelf_oa",
        "nci",
        "cdc",
        "niddk",
    }:
        signals.append("authoritative reference")
    if product_set & {"clinicaltrials_gov"}:
        signals.append("posted trial outcomes")
    if reference_product_count:
        signals.append("ontology reference")
    signal_text = " + ".join(signals) if signals else "multiple products"
    return (
        f"Concept is represented in {primary_product_count} primary products"
        f" with {reference_product_count} reference products; spans {signal_text}."
    )


def build_cross_source_concept_support(root: Path, limit: int = 30) -> list[CrossSourceConceptSupport]:
    by_cui: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    skip_names = {
        "permitted_sources_concept_documents.jsonl",
        "permitted_sources_with_extensions_concept_documents.jsonl",
    }

    for path in discover_artifact_paths(root):
        if artifact_kind(path) != "documents" or path.name in skip_names:
            continue
        try:
            handle = path.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                cui = normalized_cui(row.get("cui"))
                if not cui:
                    continue
                product = product_key_for_concept_row(row, path, root)
                if (
                    not product
                    or product in CROSS_SOURCE_EXCLUDED_PRODUCTS
                    or product not in CROSS_SOURCE_PRODUCT_WEIGHT
                ):
                    continue
                metadata = row.get("metadata")
                if not isinstance(metadata, dict):
                    metadata = {}
                evidence_count = numeric_count(row.get("evidence_count"), default=1)
                total_weight = numeric_weight(metadata.get("total_weight"), float(evidence_count))
                current = by_cui[cui].setdefault(
                    product,
                    {
                        "evidence_rows": 0,
                        "total_weight": 0.0,
                        "files": set(),
                    },
                )
                current["evidence_rows"] = max(int(current["evidence_rows"]), evidence_count)
                current["total_weight"] = max(float(current["total_weight"]), total_weight)
                if len(current["files"]) < 3:
                    current["files"].add(rel(path, root))

    candidates: list[tuple[float, str, dict[str, dict[str, Any]]]] = []
    for cui, product_support in by_cui.items():
        products = set(product_support)
        primary_products = products & CROSS_SOURCE_PRIMARY_PRODUCTS
        reference_products = products & CROSS_SOURCE_REFERENCE_PRODUCTS
        if len(products) < 3 or len(primary_products) < 2:
            continue
        evidence_rows = sum(int(row["evidence_rows"]) for row in product_support.values())
        total_weight = sum(float(row["total_weight"]) for row in product_support.values())
        source_score = sum(CROSS_SOURCE_PRODUCT_WEIGHT[product] for product in products)
        score = (
            source_score
            + (len(primary_products) * 1.75)
            + (len(reference_products) * 0.75)
            + (math.log10(evidence_rows + 1) * 2.0)
        )
        candidates.append((score, cui, product_support))

    candidates.sort(
        key=lambda item: (
            item[0],
            len(item[2]),
            sum(int(row["evidence_rows"]) for row in item[2].values()),
        ),
        reverse=True,
    )
    candidate_pool = candidates[: max(limit * 80, limit)]
    pool_cuis = [cui for _score, cui, _support in candidate_pool]
    labels = load_public_display_labels(root, pool_cuis)
    semantic_types = load_semantic_types(root, pool_cuis)

    selected: list[tuple[float, str, dict[str, dict[str, Any]]]] = []
    for candidate in candidate_pool:
        _score, cui, _product_support = candidate
        label = labels.get(cui) or cui
        if cross_source_candidate_is_actionable(label, semantic_types.get(cui, [])):
            selected.append(candidate)
        if len(selected) >= limit:
            break

    rows: list[CrossSourceConceptSupport] = []
    for score, cui, product_support in selected:
        product_rows = []
        for product, support in sorted(
            product_support.items(),
            key=lambda item: (
                -CROSS_SOURCE_PRODUCT_WEIGHT.get(item[0], 0),
                PRODUCT_ORDER.get(item[0], 999),
                item[0],
            ),
        ):
            product_rows.append(
                {
                    "key": product,
                    "label": product_label_for_key(product),
                    "linked_source_items": int(support["evidence_rows"]),
                    "supporting_rows": int(support["evidence_rows"]),
                    "evidence_rows": int(support["evidence_rows"]),
                    "total_weight": round(float(support["total_weight"]), 2),
                    "quality": PRODUCT_QUALITY.get(product, {}).get("label", ""),
                    "files": sorted(support["files"]),
                }
            )
        rows.append(
            CrossSourceConceptSupport(
                cui=cui,
                label=labels.get(cui) or cui,
                score=score,
                product_count=len(product_support),
                primary_product_count=len(set(product_support) & CROSS_SOURCE_PRIMARY_PRODUCTS),
                reference_product_count=len(set(product_support) & CROSS_SOURCE_REFERENCE_PRODUCTS),
                supporting_rows=sum(int(row["evidence_rows"]) for row in product_support.values()),
                total_weight=sum(float(row["total_weight"]) for row in product_support.values()),
                products=product_rows,
                semantic_types=semantic_types.get(cui, [])[:3],
            )
        )
    return rows


def build_bundle_stats(root: Path) -> list[BundleStats]:
    by_key: dict[str, BundleStats] = {}
    for path in discover_artifact_paths(root):
        kind = artifact_kind(path)
        if not kind:
            continue
        key = bundle_key(path, root)
        bundle = by_key.setdefault(
            key,
            BundleStats(
                key=key,
                label=label_for_key(key),
                status="unclassified",
            ),
        )
        bundle.updated_at = max(bundle.updated_at, path.stat().st_mtime)
        relative = rel(path, root)
        if kind == "manifest":
            bundle.manifest_count += 1
            bundle.manifest_files.append(relative)
            continue

        rows = count_lines(path)
        samples = sample_jsonl(path, limit=25)
        for sample in samples:
            source = str(sample.get("source") or "").strip()
            if source:
                bundle.sample_sources[source] += 1
            metadata = sample.get("metadata")
            if isinstance(metadata, dict):
                bundle.sample_metadata_keys.update(str(key) for key in metadata.keys())

        if kind == "corpus":
            bundle.corpus_rows += rows
            bundle.corpus_files.append(relative)
        elif kind == "evidence":
            bundle.evidence_rows += rows
            bundle.evidence_files.append(relative)
        elif kind == "documents":
            bundle.document_rows += rows
            bundle.document_files.append(relative)
        elif kind == "vectors":
            bundle.vector_rows += rows
            bundle.vector_files.append(relative)

    populated_bundles = [
        bundle
        for bundle in by_key.values()
        if bundle.corpus_rows or bundle.evidence_rows or bundle.document_rows or bundle.vector_rows
    ]
    for bundle in populated_bundles:
        status, notes = status_for_bundle(bundle.key, bundle.sample_sources)
        bundle.status = status
        bundle.notes.extend(notes)
        if bundle.vector_rows and bundle.document_rows and bundle.vector_rows != bundle.document_rows:
            bundle.notes.append("Vector and document counts differ.")
        if bundle.evidence_rows and not bundle.corpus_rows:
            bundle.notes.append("Evidence exists without a detected corpus artifact.")
        if bundle.corpus_rows and not bundle.evidence_rows and bundle.status not in {
            "ontology_reference",
            "subset_demo",
        }:
            bundle.notes.append("Corpus exists without detected linked evidence.")
    return sorted(
        populated_bundles,
        key=lambda item: (
            STATUS_ORDER.get(item.status, 99),
            -item.completion_fraction(),
            item.key,
        ),
    )


def product_status(product: ProductStats) -> tuple[str, list[str]]:
    key = product.key
    notes: list[str] = []
    if key == "pubmed":
        notes.append("Includes PubMed bulk baseline shards and smaller topic harvests; drill down to inspect each shard.")
        return "systematic_pilot", notes
    if key in {"hpo", "mondo"}:
        notes.append("Ontology/reference product; useful for normalization, labels, definitions, and relationship context.")
        return "ontology_reference", notes
    if key == "umls":
        notes.append("Reference index product; counts are SQLite index entries, not source corpus passages.")
        return "ontology_reference", notes
    if key in {"europepmc", "pmc_oa"}:
        notes.append("Public literature product currently represented by topic/chunk harvests, not a complete baseline ingest.")
        return "topic_harvest", notes
    if key == "pubtator3":
        notes.append("Small PubTator3 relation sample; relationship edges need evaluation before expansion.")
        return "subset_demo", notes
    if key == "clinicaltrials_gov":
        notes.append("Use for posted outcome-result evidence only; protocol, eligibility, and recruitment text should remain context.")
        return "subset_demo", notes
    if key == "medlineplus" and product.bundle_statuses.get("systematic_snapshot"):
        notes.append("Includes the full MedlinePlus health-topic XML snapshot; drill down for corpus, evidence, and vector artifacts.")
        return "systematic_snapshot", notes
    if key in {
        "cdc",
        "dailymed",
        "fda",
        "medlineplus_genetics",
        "ncbi_bookshelf_oa",
        "nci",
        "niddk",
    }:
        notes.append("Public-source subset product; useful for demos but not systematic source coverage.")
        return "subset_demo", notes
    if key in {"openalex", "wikipedia", "wikimedia", "drug_enrichment", "open_image"}:
        notes.append("Enrichment product; evaluate separately from primary literature evidence.")
        return "enrichment_snapshot", notes
    if product.bundle_statuses:
        status = min(product.bundle_statuses, key=lambda item: STATUS_ORDER.get(item, 99))
        notes.append("Status inferred from contributing artifact bundles.")
        return status, notes
    return "unclassified", ["Needs registry entry before being treated as systematic evidence."]


def products_for_bundle(bundle: BundleStats, root: Path) -> set[str]:
    products: set[str] = set()
    for source in bundle.sample_sources:
        product = product_key_for_source(source)
        if product:
            products.add(product)
    for file_list in (
        bundle.corpus_files,
        bundle.evidence_files,
        bundle.document_files,
        bundle.vector_files,
        bundle.manifest_files,
    ):
        for relative in file_list:
            product = product_key_for_path(root / relative, root)
            if product:
                products.add(product)
    if not products:
        product = product_key_for_source(bundle.key)
        if product:
            products.add(product)
    return products


def build_product_stats(root: Path, bundles: list[BundleStats]) -> list[ProductStats]:
    products: dict[str, ProductStats] = {}

    def get_product(key: str) -> ProductStats:
        normalized = product_key_for_source(key)
        product = products.get(normalized)
        if product is None:
            product = ProductStats(
                key=normalized,
                label=product_label_for_key(normalized),
                status="unclassified",
            )
            products[normalized] = product
        return product

    for path in discover_artifact_paths(root):
        kind = artifact_kind(path)
        if not kind:
            continue
        relative = rel(path, root)
        bundle = bundle_key(path, root)
        updated_at = path.stat().st_mtime
        if kind == "manifest":
            product_key = product_key_for_path(path, root)
            if product_key:
                product = get_product(product_key)
                product.updated_at = max(product.updated_at, updated_at)
                product.files["manifests"].add(relative)
                product.bundle_keys.add(bundle)
            continue

        counts, _rows = product_counts_for_file(path, kind, root)
        samples = sample_jsonl(path, limit=25)
        for product_key, rows in counts.items():
            product = get_product(product_key)
            product.updated_at = max(product.updated_at, updated_at)
            product.files[kind].add(relative)
            product.bundle_keys.add(bundle)
            if kind == "corpus":
                product.corpus_rows += rows
            elif kind == "evidence":
                product.evidence_rows += rows
            elif kind == "documents":
                product.document_rows += rows
            elif kind == "vectors":
                product.vector_rows += rows
        for sample in samples:
            source = str(sample.get("source") or "").strip()
            product_key = product_key_for_source(source)
            if product_key and product_key in products:
                products[product_key].sample_sources[source] += 1

    umls_product = get_product("umls")
    for path in discover_umls_index_paths(root):
        table_counts = sqlite_table_row_counts(path)
        if not table_counts:
            continue
        relative = rel(path, root)
        row_count = sum(int(row["rows"]) for row in table_counts)
        umls_product.index_rows += row_count
        umls_product.files["indexes"].add(relative)
        umls_product.updated_at = max(umls_product.updated_at, path.stat().st_mtime)
        for row in table_counts:
            source_key = f"UMLS {row['label'].lower()}"
            umls_product.sample_sources[source_key] += int(row["rows"])
        umls_product.index_artifacts.append(
            {
                "path": relative,
                "label": umls_index_label_for_path(path),
                "rows": row_count,
                "tables": table_counts,
            }
        )

    bundle_lookup = {bundle.key: bundle for bundle in bundles}
    for bundle in bundles:
        for product_key in products_for_bundle(bundle, root):
            product = get_product(product_key)
            product.bundle_keys.add(bundle.key)
            product.bundle_statuses[bundle.status] += 1
            product.updated_at = max(product.updated_at, bundle.updated_at)

    for product in products.values():
        status, notes = product_status(product)
        product.status = status
        product.notes.extend(notes)
        if product.vector_rows and product.document_rows and product.vector_rows != product.document_rows:
            product.notes.append("Vector and document counts differ at product level; drill down by bundle.")
        if product.evidence_rows and not product.corpus_rows:
            product.notes.append("Evidence exists without a detected product-level corpus artifact.")
        if product.corpus_rows and not product.evidence_rows and product.status not in {
            "ontology_reference",
            "subset_demo",
        }:
            product.notes.append("Corpus exists without detected linked evidence.")

    populated_products = [
        product
        for product in products.values()
        if product.key not in DASHBOARD_EXCLUDED_PRODUCTS
        and (
            product.corpus_rows
            or product.evidence_rows
            or product.document_rows
            or product.vector_rows
            or product.index_rows
        )
    ]

    return sorted(
        populated_products,
        key=lambda item: (
            PRODUCT_ORDER.get(item.key, 999),
            STATUS_ORDER.get(item.status, 99),
            item.label.lower(),
        ),
    )


def dashboard_bundle_is_excluded(bundle: BundleStats, root: Path) -> bool:
    products = products_for_bundle(bundle, root)
    return bool(products) and products <= DASHBOARD_EXCLUDED_PRODUCTS


STATUS_ORDER = {
    "systematic_pilot": 0,
    "systematic_snapshot": 1,
    "mixed_public_bundle": 2,
    "enrichment_snapshot": 3,
    "ontology_reference": 4,
    "topic_harvest": 5,
    "subset_demo": 6,
    "restricted_private": 7,
    "unclassified": 8,
}


def load_evaluation_summaries(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("build/**/search_quality_summary.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "kind": "quality_judgments",
                "run": path.parent.name,
                "path": rel(path, root),
                "queries": int(data.get("queries") or 0),
                "judgments": int(data.get("judgments") or 0),
                "mean_weighted_p5": data.get("mean_weighted_p5"),
                "mean_mrr": data.get("mean_mrr"),
                "queries_with_relevant_top1": data.get("queries_with_relevant_top1"),
                "top1_accuracy": None,
                "top3_accuracy": None,
                "topk_accuracy": None,
                "updated_at": iso_timestamp(path.stat().st_mtime),
            }
        )
    for path in sorted(root.glob("build/search_regression*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        summary = data.get("summary") if isinstance(data.get("summary"), dict) else data
        rows.append(
            {
                "kind": "regression_benchmark",
                "run": path.stem,
                "path": rel(path, root),
                "queries": int(summary.get("queries") or 0),
                "judgments": int(summary.get("judged_queries") or 0),
                "mean_weighted_p5": None,
                "mean_mrr": summary.get("mrr"),
                "queries_with_relevant_top1": None,
                "top1_accuracy": summary.get("top1_accuracy"),
                "top3_accuracy": summary.get("top3_accuracy"),
                "topk_accuracy": summary.get("topk_accuracy"),
                "updated_at": iso_timestamp(path.stat().st_mtime),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("updated_at") or ""), reverse=True)


def load_judgment_counts(root: Path) -> dict[str, Any]:
    grade_counts: Counter = Counter()
    files = []
    for path in sorted(root.glob("build/**/*judgments.csv")):
        try:
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                local = Counter()
                for row in reader:
                    grade = str(row.get("grade") or "").strip().lower()
                    if grade:
                        grade_counts[grade] += 1
                        local[grade] += 1
                if sum(local.values()):
                    files.append({"path": rel(path, root), "rows": sum(local.values()), "grades": dict(local)})
        except OSError:
            continue
    return {
        "files": files,
        "file_count": len(files),
        "grade_counts": dict(grade_counts),
        "rows": sum(grade_counts.values()),
    }


def summarize(
    products: list[ProductStats],
    bundles: list[BundleStats],
    evaluations: list[dict[str, Any]],
    judgments: dict[str, Any],
) -> dict[str, Any]:
    status_counts = Counter(product.status for product in products)
    systematic = [
        product
        for product in products
        if product.status in {"systematic_pilot", "systematic_snapshot"}
    ]
    total_products = len(products)
    ready_products = sum(1 for product in products if product.completion_fraction() >= 1.0)
    total_bundles = len(bundles)
    ready_bundles = sum(1 for bundle in bundles if bundle.completion_fraction() >= 1.0)
    best_eval = next((row for row in evaluations if row.get("kind") == "quality_judgments"), None)
    return {
        "product_count": total_products,
        "ready_product_count": ready_products,
        "bundle_count": total_bundles,
        "ready_bundle_count": ready_bundles,
        "status_counts": dict(status_counts),
        "corpus_rows": sum(product.corpus_rows for product in products),
        "evidence_rows": sum(product.evidence_rows for product in products),
        "document_rows": sum(product.document_rows for product in products),
        "vector_rows": sum(product.vector_rows for product in products),
        "index_rows": sum(product.index_rows for product in products),
        "systematic_product_count": len(systematic),
        "systematic_corpus_rows": sum(product.corpus_rows for product in systematic),
        "systematic_evidence_rows": sum(product.evidence_rows for product in systematic),
        "evaluation_run_count": len(evaluations),
        "judgment_rows": judgments.get("rows", 0),
        "best_current_quality": best_eval or {},
    }


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return ""


def fmt_pct(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(value)


def h(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def metric_card(label: str, value: str, detail: str = "") -> str:
    return (
        '<div class="metric">'
        f"<div class=\"metric-label\">{h(label)}</div>"
        f"<div class=\"metric-value\">{h(value)}</div>"
        f"<div class=\"metric-detail\">{h(detail)}</div>"
        "</div>"
    )


def status_badge(status: str) -> str:
    return f'<span class="badge {h(status)}">{h(status.replace("_", " "))}</span>'


def quality_cell(quality: dict[str, Any]) -> str:
    label = quality.get("label") or "Needs review"
    level = quality.get("level") or "quality_needs_review"
    reason = quality.get("reason") or ""
    return (
        '<td class="quality-cell">'
        f'<span class="quality-badge {h(level)}">{h(label)}</span>'
        f'<div class="muted small">{h(reason)}</div>'
        "</td>"
    )


def write_html(path: Path, payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    products = payload["products"]
    evaluations = payload["evaluations"]
    generated_at = payload["generated_at"]

    cards = "\n".join(
        [
            metric_card("Products", fmt_int(summary["product_count"]), f"{fmt_int(summary['ready_product_count'])} complete product pipelines"),
            metric_card("Concept Vectors", fmt_int(summary["vector_rows"]), "All detected vector embeddings"),
            metric_card("Reference Indexes", fmt_int(summary["index_rows"]), "Detected SQLite index entries"),
            metric_card("Evaluation Runs", fmt_int(summary["evaluation_run_count"]), f"{fmt_int(summary['judgment_rows'])} saved judgments"),
        ]
    )

    product_rows = []
    for product in products:
        notes = " ".join(product.get("notes") or [])
        review = product.get("source_review") or {}
        quality = product.get("source_quality") or {}
        child_rows = []
        for bundle in product.get("bundles") or []:
            file_hint = ", ".join((bundle["files"].get("corpus") or bundle["files"].get("documents") or [])[:2])
            child_rows.append(
                "<tr>"
                f"<td><strong>{h(bundle['label'])}</strong><div class=\"muted small\">{h(bundle['key'])}</div></td>"
                f"<td>{status_badge(bundle['status'])}</td>"
                f"<td>{fmt_int(bundle['vector_rows'])}</td>"
                f"<td><div class=\"muted small\">{h(file_hint)}</div></td>"
                "</tr>"
            )
        index_rows = []
        for artifact in product.get("index_artifacts") or []:
            table_text = ", ".join(
                f"{table.get('label')} ({fmt_int(table.get('rows'))})"
                for table in artifact.get("tables") or []
            )
            index_rows.append(
                "<tr>"
                f"<td><strong>{h(artifact.get('label'))}</strong><div class=\"muted small\">{h(artifact.get('path'))}</div></td>"
                f"<td>{fmt_int(artifact.get('rows'))}</td>"
                f"<td>{h(table_text)}</td>"
                "</tr>"
            )
        file_count = sum(len(paths) for paths in product.get("files", {}).values())
        drilldown = ""
        if child_rows:
            drilldown = (
                "<details>"
                f"<summary>{fmt_int(product.get('bundle_count'))} bundles, {fmt_int(file_count)} files</summary>"
                "<div class=\"nested-wrap\"><table class=\"nested-table\">"
                "<thead><tr><th>Bundle</th><th>Status</th><th>Vectors</th><th>Files</th></tr></thead>"
                f"<tbody>{''.join(child_rows)}</tbody>"
                "</table></div>"
                "</details>"
            )
        if index_rows:
            drilldown += (
                "<details>"
                f"<summary>{fmt_int(len(index_rows))} index artifacts, {fmt_int(product.get('index_rows'))} entries</summary>"
                "<div class=\"nested-wrap\"><table class=\"nested-table\">"
                "<thead><tr><th>Index</th><th>Entries</th><th>Tables</th></tr></thead>"
                f"<tbody>{''.join(index_rows)}</tbody>"
                "</table></div>"
                "</details>"
            )
        drilldown_html = drilldown
        if notes:
            drilldown_html = f"<div class=\"muted small status-notes\"><strong>Status notes:</strong> {h(notes)}</div>{drilldown}"
        product_rows.append(
            "<tr>"
            f"<td><strong>{h(product['label'])}</strong><div class=\"muted small\">{h(product['key'])}</div></td>"
            f"<td class=\"review-cell\">{h(review.get('why'))}</td>"
            f"<td class=\"review-cell\">{h(review.get('evidence'))}</td>"
            f"{quality_cell(quality)}"
            f"<td class=\"review-cell\">{h(review.get('next'))}</td>"
            f"<td>{status_badge(product['status'])}</td>"
            f"<td>{fmt_int(product['vector_rows'])}</td>"
            f"<td>{fmt_int(product.get('index_rows'))}</td>"
            f"<td class=\"drilldown-cell\">{drilldown_html}</td>"
            "</tr>"
        )

    eval_rows = []
    for row in evaluations[:20]:
        top1 = row.get("top1_accuracy")
        if top1 is None and row.get("queries_with_relevant_top1") is not None and row.get("queries"):
            try:
                top1 = float(row["queries_with_relevant_top1"]) / float(row["queries"])
            except (TypeError, ValueError, ZeroDivisionError):
                top1 = None
        eval_rows.append(
            "<tr>"
            f"<td><strong>{h(row.get('run'))}</strong><div class=\"muted small\">{h(row.get('kind'))}</div></td>"
            f"<td>{fmt_int(row.get('queries'))}</td>"
            f"<td>{fmt_int(row.get('judgments'))}</td>"
            f"<td>{fmt_pct(top1)}</td>"
            f"<td>{fmt_pct(row.get('top3_accuracy'))}</td>"
            f"<td>{fmt_pct(row.get('mean_weighted_p5'))}</td>"
            f"<td>{fmt_pct(row.get('mean_mrr'))}</td>"
            f"<td><code>{h(row.get('path'))}</code></td>"
            "</tr>"
        )

    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Evidence Progress Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f8;
      --surface: #ffffff;
      --line: #d9dee3;
      --text: #17202a;
      --muted: #66717d;
      --green: #157347;
      --amber: #9a6200;
      --red: #b42318;
      --blue: #1f5f99;
      --violet: #6a4c93;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 28px; margin: 0 0 4px; letter-spacing: 0; }}
    h2 {{ font-size: 18px; margin: 0 0 12px; letter-spacing: 0; }}
    .top {{ display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; margin-bottom: 18px; }}
    .muted {{ color: var(--muted); }}
    .small {{ font-size: 12px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }}
    .metric, section {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 12px; min-height: 96px; }}
    .metric-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; }}
    .metric-value {{ font-size: 28px; font-weight: 700; margin-top: 6px; }}
    .metric-detail {{ color: var(--muted); font-size: 12px; margin-top: 4px; }}
    section {{ padding: 14px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); padding: 8px; }}
    th {{ font-size: 12px; color: var(--muted); text-transform: uppercase; background: #fbfbfc; position: sticky; top: 0; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }}
    .table-wrap {{ overflow: auto; max-height: 620px; border: 1px solid var(--line); border-radius: 8px; }}
    details {{ margin-top: 8px; }}
    summary {{ cursor: pointer; color: var(--blue); font-weight: 700; }}
    .review-cell {{ min-width: 260px; max-width: 360px; }}
    .quality-cell {{ min-width: 220px; max-width: 320px; }}
    .quality-badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      background: #eef1f4;
      color: #334155;
      margin-bottom: 4px;
    }}
    .quality_high {{ background: #e7f5ee; color: var(--green); }}
    .quality_reference {{ background: #f0ecf7; color: var(--violet); }}
    .quality_medium {{ background: #fff4dd; color: var(--amber); }}
    .quality_enrichment {{ background: #e8f1fa; color: var(--blue); }}
    .quality_needs_review {{ background: #fdeceb; color: var(--red); }}
    .drilldown-cell {{ min-width: 280px; }}
    .support-products {{ min-width: 280px; max-width: 460px; }}
    .status-notes {{ margin-top: 8px; }}
    .nested-wrap {{ overflow: auto; max-height: 360px; margin-top: 8px; border: 1px solid var(--line); border-radius: 6px; }}
    .nested-table th, .nested-table td {{ font-size: 12px; padding: 6px; }}
    .badge {{
      display: inline-block;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      background: #eef1f4;
      color: #334155;
    }}
    .systematic_pilot, .systematic_snapshot {{ background: #e7f5ee; color: var(--green); }}
    .mixed_public_bundle, .enrichment_snapshot {{ background: #e8f1fa; color: var(--blue); }}
    .ontology_reference {{ background: #f0ecf7; color: var(--violet); }}
    .topic_harvest, .subset_demo {{ background: #fff4dd; color: var(--amber); }}
    .restricted_private, .unclassified {{ background: #fdeceb; color: var(--red); }}
    @media (max-width: 900px) {{
      main {{ padding: 14px; }}
      .top {{ display: block; }}
      .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric-value {{ font-size: 22px; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="top">
      <div>
        <h1>Evidence Progress Dashboard</h1>
        <div class="muted">Artifact-driven source ingestion and evaluation status.</div>
      </div>
      <div class="muted small">Generated {h(generated_at)}</div>
    </div>
    <div class="cards">
      {cards}
    </div>
    <section>
      <h2>Products</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Product</th><th>Why Included</th><th>Evidence Chosen</th><th>Evidence Quality</th><th>Next Steps</th>
              <th>Status</th><th>Vectors</th><th>Index Entries</th><th>Drilldown</th>
            </tr>
          </thead>
          <tbody>{''.join(product_rows)}</tbody>
        </table>
      </div>
    </section>
    <section>
      <h2>Evaluation</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run</th><th>Queries</th><th>Judgments</th><th>Top 1</th>
              <th>Top 3</th><th>Weighted P@5</th><th>MRR</th><th>File</th>
            </tr>
          </thead>
          <tbody>{''.join(eval_rows)}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def build_payload(root: Path) -> dict[str, Any]:
    bundles = [
        bundle
        for bundle in build_bundle_stats(root)
        if not dashboard_bundle_is_excluded(bundle, root)
    ]
    products = build_product_stats(root, bundles)
    evaluations = load_evaluation_summaries(root)
    judgments = load_judgment_counts(root)
    bundle_lookup = {bundle.key: bundle for bundle in bundles}
    summary = summarize(products, bundles, evaluations, judgments)
    return {
        "generated_at": datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat(),
        "summary": summary,
        "products": [product.to_json(bundle_lookup) for product in products],
        "bundles": [bundle.to_json() for bundle in bundles],
        "evaluations": evaluations,
        "judgments": judgments,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a simple evidence progress dashboard from local artifacts.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-html", type=Path, default=DEFAULT_OUT_HTML)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    payload = build_payload(root)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    write_html(args.out_html, payload)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
