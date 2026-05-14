from __future__ import annotations

import json
import os
import re
import tarfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import csv
import html
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .corpus import stable_doc_id
from .schema import CorpusDocument
from .text import clean_text


NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PMC_OPEN_ACCESS_FILTER = "open_access[filter]"
CLINICALTRIALS_STUDIES = "https://clinicaltrials.gov/api/v2/studies"
MEDLINEPLUS_XML_INDEX = "https://medlineplus.gov/xml.html"
MEDLINEPLUS_GENETICS_SUMMARIES = "https://medlineplus.gov/download/ghr-summaries.xml"
DAILYMED_SPLS = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
DAILYMED_SPL_XML = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml"
NLM_LITARCH_BASE = "https://ftp.ncbi.nlm.nih.gov/pub/litarch/"
NLM_LITARCH_FILE_LIST_CSV = urllib.parse.urljoin(NLM_LITARCH_BASE, "file_list.csv")
HPO_OBO = "http://purl.obolibrary.org/obo/hp.obo"
MONDO_OBO = "http://purl.obolibrary.org/obo/mondo.obo"
DAILYMED_SETID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
DAILYMED_MRSAT_ATN_HINTS = ("setid", "set_id", "spl_set", "dailymed")
DAILYMED_SECTION_KEYWORDS = (
    "indications",
    "dosage",
    "contraindications",
    "warnings",
    "precautions",
    "adverse reactions",
    "drug interactions",
    "use in specific populations",
    "clinical pharmacology",
    "description",
)
REFERENCE_PAGE_SOURCE_POLICIES: dict[str, dict[str, object]] = {
    "nci": {
        "label": "National Cancer Institute",
        "fetch_policy": "public_reusable",
        "license": "U.S. government public-domain text unless otherwise indicated",
        "terms_url": "https://www.cancer.gov/policies/copyright-reuse",
        "attribution": "Credit the National Cancer Institute as the source.",
        "default_urls": [
            "https://www.cancer.gov/about-cancer/diagnosis-staging/diagnosis",
            "https://www.cancer.gov/about-cancer/treatment/types",
            "https://www.cancer.gov/about-cancer/causes-prevention/risk",
        ],
    },
    "cdc": {
        "label": "Centers for Disease Control and Prevention",
        "fetch_policy": "public_reusable_with_exceptions",
        "license": "Most CDC/ATSDR website text is public domain; respect page-level exceptions.",
        "terms_url": "https://www.cdc.gov/other/agencymaterials.html",
        "attribution": "Acknowledge CDC as source where content is reused.",
        "default_urls": [
            "https://www.cdc.gov/diabetes/",
            "https://www.cdc.gov/flu/",
            "https://www.cdc.gov/sepsis/",
        ],
    },
    "fda": {
        "label": "U.S. Food and Drug Administration",
        "fetch_policy": "public_reusable",
        "license": "FDA website text and graphics are public domain unless otherwise noted.",
        "terms_url": "https://www.fda.gov/about-fda/about-website/website-policies",
        "attribution": "Credit to FDA is appreciated but not required.",
        "default_urls": [
            "https://www.fda.gov/drugs/drug-safety-and-availability",
            "https://www.fda.gov/drugs/resources-you-drugs/information-consumers-and-patients-drugs",
        ],
    },
    "niddk": {
        "label": "National Institute of Diabetes and Digestive and Kidney Diseases",
        "fetch_policy": "public_reusable_with_exceptions",
        "license": "Most NIDDK text is copyright-free; respect page-level exceptions.",
        "terms_url": "https://www.niddk.nih.gov/copyright",
        "attribution": "Acknowledge NIDDK as the source for unchanged reproduced content.",
        "default_urls": [
            "https://www.niddk.nih.gov/health-information/diabetes/overview/what-is-diabetes",
            "https://www.niddk.nih.gov/health-information/kidney-disease",
            "https://www.niddk.nih.gov/health-information/digestive-diseases",
        ],
    },
    "ncbi_bookshelf_oa": {
        "label": "NCBI Bookshelf / NLM LitArch Open Access subset",
        "fetch_policy": "public_reusable_with_per_file_license",
        "license": "Automated retrieval is permitted only through the NLM LitArch FTP service; licenses vary by package.",
        "terms_url": "https://www.ncbi.nlm.nih.gov/books/about/openaccess/",
        "attribution": "Preserve package-level license metadata and attribution requirements.",
        "default_urls": [],
        "source_kind": "bookshelf_oa",
    },
    "hpo": {
        "label": "Human Phenotype Ontology",
        "fetch_policy": "public_reusable_with_attribution_no_modification",
        "license": "Freely available HPO ontology files; acknowledge/cite HPO, display file version/date, and do not alter ontology content or logical relationships.",
        "terms_url": "https://human-phenotype-ontology.github.io/license.html",
        "attribution": "Acknowledge the Human Phenotype Ontology Consortium and preserve source version/date metadata.",
        "default_urls": [HPO_OBO],
        "source_kind": "obo_ontology",
        "id_prefixes": ["HP:"],
    },
    "mondo": {
        "label": "Mondo Disease Ontology",
        "fetch_policy": "cc_by_4_0",
        "license": "CC BY 4.0 disease ontology; attribution and license notice required.",
        "terms_url": "https://monarch-initiative.github.io/monarch-documentation/Repositories/mondo/",
        "attribution": "Credit Mondo / Monarch Initiative and preserve source version metadata.",
        "default_urls": [MONDO_OBO],
        "source_kind": "obo_ontology",
        "id_prefixes": ["MONDO:"],
    },
    "merck_manual_professional": {
        "label": "Merck Manual Professional Edition",
        "fetch_policy": "permission_required",
        "license": "Copyrighted reference content; permission required for reuse beyond personal use.",
        "terms_url": "https://www.merckmanuals.com/professional/content/termsofuse",
        "attribution": "Do not include in redistributable artifacts without written permission.",
        "default_urls": [],
    },
    "msd_manual_professional": {
        "label": "MSD Manual Professional Edition",
        "fetch_policy": "permission_required",
        "license": "Copyrighted reference content; permission required for reuse beyond personal use.",
        "terms_url": "https://www.msdmanuals.com/professional/content/termsofuse",
        "attribution": "Do not include in redistributable artifacts without written permission.",
        "default_urls": [],
    },
    "aafp": {
        "label": "American Academy of Family Physicians",
        "fetch_policy": "permission_required",
        "license": "AAFP content is copyrighted; terms grant personal non-commercial access only.",
        "terms_url": "https://www.aafp.org/about/this-site/terms.html",
        "attribution": "Use only with permission or locally supplied licensed content.",
        "default_urls": [],
    },
    "medscape": {
        "label": "Medscape",
        "fetch_policy": "permission_required",
        "license": "Medscape content is copyrighted and its terms prohibit scraping.",
        "terms_url": "https://www.medscape.com/public/termsofuse",
        "attribution": "Use only with permission or locally supplied licensed content.",
        "default_urls": [],
    },
    "bmj_best_practice": {
        "label": "BMJ Best Practice",
        "fetch_policy": "subscription_required",
        "license": "Copyrighted subscription clinical decision-support content; licensed use required.",
        "terms_url": "https://bestpractice.bmj.com/info/us/legal/",
        "attribution": "Use only with a BMJ license or locally supplied permitted content.",
        "default_urls": [],
    },
    "nice_cks": {
        "label": "NICE Clinical Knowledge Summaries",
        "fetch_policy": "permission_required",
        "license": "CKS is third-party Agilio/Clarity Informatics content; reuse requires the applicable EULA or permission.",
        "terms_url": "https://www.nice.org.uk/terms-and-conditions",
        "attribution": "Use only with permission or locally supplied licensed content.",
        "default_urls": [],
    },
    "ncbi_bookshelf_statpearls": {
        "label": "NCBI Bookshelf StatPearls",
        "fetch_policy": "noncommercial_no_derivatives",
        "license": "Bookshelf licenses vary by title; StatPearls chapters are typically CC BY-NC-ND 4.0.",
        "terms_url": "https://www.ncbi.nlm.nih.gov/books/about/copyright/",
        "attribution": "Preserve per-chapter license statements and do not create derived public artifacts without permission.",
        "default_urls": [],
    },
    "patient_info_professional": {
        "label": "Patient.info Professional Reference",
        "fetch_policy": "permission_required",
        "license": "Copyrighted; terms restrict extraction for structured medical knowledge, decision support, datasets, and AI/ML.",
        "terms_url": "https://patient.info/terms-and-conditions",
        "attribution": "Use only with permission or locally supplied licensed content.",
        "default_urls": [],
    },
    "gpnotebook": {
        "label": "GPnotebook",
        "fetch_policy": "permission_required",
        "license": "Copyrighted; limited personal non-commercial reference use, with copying and automated extraction restricted.",
        "terms_url": "https://gpnotebook.com/en-GB/terms-of-use",
        "attribution": "Use only with permission or locally supplied licensed content.",
        "default_urls": [],
    },
    "wikem": {
        "label": "WikEM",
        "fetch_policy": "cc_by_sa_with_automated_access_restrictions",
        "license": "CC BY-SA medical wiki with automated-access and AI/ML restrictions in the site terms.",
        "terms_url": "https://wikem.org/wiki/WikEM:Terms_of_Use",
        "attribution": "Use only with a compliant CC BY-SA artifact strategy and any required permission for automated access.",
        "default_urls": [],
    },
}
RESTRICTED_REFERENCE_FETCH_POLICIES = {
    "permission_required",
    "subscription_required",
    "noncommercial_no_derivatives",
    "cc_by_sa_with_automated_access_restrictions",
}


@dataclass(frozen=True)
class PubMedTopic:
    topic: str
    term: str
    retmax: int | None = None


@dataclass(frozen=True)
class BookshelfOAEntry:
    archive_path: str
    title: str
    publisher: str
    publication_year: str
    accession_id: str
    last_updated: str


@dataclass(frozen=True)
class OboTerm:
    term_id: str
    name: str
    namespace: str = ""
    definition: str = ""
    synonyms: tuple[str, ...] = ()
    xrefs: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()
    relationships: tuple[str, ...] = ()
    is_obsolete: bool = False


def _read_url(url: str, *, sleep_seconds: float = 0.34) -> bytes:
    with urllib.request.urlopen(url) as response:
        payload = response.read()
    if sleep_seconds:
        time.sleep(sleep_seconds)
    return payload


def _read_resource_bytes(value: str, *, sleep_seconds: float = 0.34) -> bytes:
    local_path = Path(value).expanduser()
    if local_path.exists():
        return local_path.read_bytes()
    return _read_url(value, sleep_seconds=sleep_seconds)


def reference_source_policies() -> dict[str, dict[str, object]]:
    return {key: dict(value) for key, value in REFERENCE_PAGE_SOURCE_POLICIES.items()}


def reference_page_source_policies() -> dict[str, dict[str, object]]:
    return {
        key: dict(value)
        for key, value in REFERENCE_PAGE_SOURCE_POLICIES.items()
        if str(value.get("source_kind") or "reference_page") == "reference_page"
    }


def ontology_source_policies() -> dict[str, dict[str, object]]:
    return {
        key: dict(value)
        for key, value in REFERENCE_PAGE_SOURCE_POLICIES.items()
        if str(value.get("source_kind") or "reference_page") == "obo_ontology"
    }


def reference_source_policy(source: str) -> dict[str, object]:
    key = clean_text(source).lower().replace("-", "_")
    if key not in REFERENCE_PAGE_SOURCE_POLICIES:
        available = ", ".join(sorted(REFERENCE_PAGE_SOURCE_POLICIES))
        raise ValueError(f"unknown reference source {source!r}; expected one of: {available}")
    return dict(REFERENCE_PAGE_SOURCE_POLICIES[key])


def reference_source_is_restricted(source: str) -> bool:
    policy = reference_source_policy(source)
    return str(policy.get("fetch_policy") or "") in RESTRICTED_REFERENCE_FETCH_POLICIES


def strip_markup(text: str | None) -> str:
    text = html.unescape(str(text or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return clean_text(text)


def _list_text(values: Iterable[object]) -> list[str]:
    return [clean_text(str(value)) for value in values if clean_text(str(value))]


def html_page_to_text(payload: bytes | str) -> tuple[str, str]:
    raw = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", raw, flags=re.I | re.S)
    title = strip_markup(h1_match.group(1) if h1_match else (title_match.group(1) if title_match else ""))
    body = re.sub(r"<(script|style|noscript|svg|canvas)\b[^>]*>.*?</\1>", " ", raw, flags=re.I | re.S)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    text = strip_markup(body)
    return title, text


def _read_reference_resource(value: str) -> bytes:
    return _read_resource_bytes(value, sleep_seconds=0.15)


def fetch_reference_page_documents(
    source: str,
    *,
    urls: Iterable[str] = (),
    max_records: int = 25,
    max_chars: int | None = 25000,
    allow_restricted: bool = False,
) -> Iterator[CorpusDocument]:
    source_key = clean_text(source).lower().replace("-", "_")
    policy = reference_source_policy(source_key)
    if str(policy.get("source_kind") or "reference_page") != "reference_page":
        raise ValueError(f"{source_key} is not an HTML reference-page source; use its dedicated fetch command")
    fetch_policy = str(policy.get("fetch_policy") or "")
    if fetch_policy in RESTRICTED_REFERENCE_FETCH_POLICIES and not allow_restricted:
        raise ValueError(
            f"{source_key} is marked {fetch_policy}; provide locally licensed content "
            "with ingest-tabular-corpus, or rerun with --allow-restricted-reference-source "
            "only for a private deployment with appropriate rights."
        )
    selected_urls = [clean_text(value) for value in urls if clean_text(value)]
    if not selected_urls:
        selected_urls = [str(value) for value in policy.get("default_urls") or []]
    if not selected_urls:
        raise ValueError(f"{source_key} has no default URLs; pass --url for explicitly licensed pages")
    emitted = 0
    seen: set[str] = set()
    for url in selected_urls:
        if max_records and emitted >= max_records:
            return
        key = url.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        title, text = html_page_to_text(_read_reference_resource(key))
        if max_chars is not None and max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars].rsplit(" ", 1)[0]
        if not text:
            continue
        yield CorpusDocument(
            doc_id=f"{source_key.upper()}:{stable_doc_id(source_key, key)}",
            source=source_key,
            title=title,
            text=clean_text(" ".join(part for part in [title, text] if part)),
            metadata={
                "source_url": key,
                "source_label": str(policy.get("label") or source_key),
                "source_license": str(policy.get("license") or ""),
                "license_status": fetch_policy,
                "terms_url": str(policy.get("terms_url") or ""),
                "attribution": str(policy.get("attribution") or ""),
                "retrieved_via": "reference_page_html",
            },
        )
        emitted += 1


def _strip_obo_comment(value: str) -> str:
    in_quote = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == '"':
            in_quote = not in_quote
            continue
        if not in_quote and value[index : index + 3] == " ! ":
            return value[:index].strip()
    return value.strip()


def _first_obo_quoted(value: str) -> str:
    match = re.search(r'"((?:[^"\\]|\\.)*)"', value)
    if not match:
        return clean_text(_strip_obo_comment(value))
    return clean_text(
        match.group(1)
        .replace(r"\"", '"')
        .replace(r"\n", " ")
        .replace(r"\t", " ")
        .replace(r"\\", "\\")
    )


def _first_obo_token(value: str) -> str:
    cleaned = _strip_obo_comment(value)
    return clean_text(cleaned.split()[0] if cleaned else "")


def obo_text_to_terms(payload: bytes | str) -> tuple[dict[str, str], list[OboTerm]]:
    raw = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
    header: dict[str, str] = {}
    terms: list[OboTerm] = []
    stanza = "header"
    block: dict[str, list[str]] = {}

    def flush_term() -> None:
        nonlocal block
        if stanza != "Term" or not block:
            block = {}
            return
        term_id = clean_text((block.get("id") or [""])[0])
        name = clean_text((block.get("name") or [""])[0])
        if not term_id or not name:
            block = {}
            return
        terms.append(
            OboTerm(
                term_id=term_id,
                name=name,
                namespace=clean_text((block.get("namespace") or [""])[0]),
                definition=_first_obo_quoted((block.get("def") or [""])[0]),
                synonyms=tuple(
                    dict.fromkeys(_first_obo_quoted(value) for value in block.get("synonym", []) if _first_obo_quoted(value))
                ),
                xrefs=tuple(dict.fromkeys(_first_obo_token(value) for value in block.get("xref", []) if _first_obo_token(value))),
                parents=tuple(dict.fromkeys(_first_obo_token(value) for value in block.get("is_a", []) if _first_obo_token(value))),
                relationships=tuple(
                    dict.fromkeys(_strip_obo_comment(value) for value in block.get("relationship", []) if _strip_obo_comment(value))
                ),
                is_obsolete=any(clean_text(value).lower() == "true" for value in block.get("is_obsolete", [])),
            )
        )
        block = {}

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("[") and line.endswith("]"):
            flush_term()
            stanza = line.strip("[]")
            block = {}
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if stanza == "header":
            if key not in header:
                header[key] = clean_text(_strip_obo_comment(value))
        elif stanza == "Term":
            block.setdefault(key, []).append(value)
    flush_term()
    return header, terms


def obo_term_to_document(
    term: OboTerm,
    *,
    source: str,
    source_url: str,
    policy: dict[str, object],
    header: dict[str, str],
    max_chars: int | None = 8000,
) -> CorpusDocument:
    version = header.get("data-version") or header.get("date") or ""
    text_parts = [
        term.name,
        f"Identifier: {term.term_id}",
        f"Namespace: {term.namespace}" if term.namespace else "",
        f"Definition: {term.definition}" if term.definition else "",
        f"Synonyms: {'; '.join(term.synonyms)}" if term.synonyms else "",
        f"Cross-references: {'; '.join(term.xrefs)}" if term.xrefs else "",
        f"Parent terms: {'; '.join(term.parents)}" if term.parents else "",
        f"Relationships: {'; '.join(term.relationships)}" if term.relationships else "",
        "Obsolete term" if term.is_obsolete else "",
    ]
    text = clean_text(" ".join(part for part in text_parts if part))
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0]
    return CorpusDocument(
        doc_id=f"{source.upper()}:{term.term_id.replace(':', '_')}",
        source=source,
        title=term.name,
        text=text,
        metadata={
            "source_url": source_url,
            "source_label": str(policy.get("label") or source),
            "source_license": str(policy.get("license") or ""),
            "license_status": str(policy.get("fetch_policy") or ""),
            "terms_url": str(policy.get("terms_url") or ""),
            "attribution": str(policy.get("attribution") or ""),
            "retrieved_via": "obo_purl",
            "ontology": header.get("ontology") or source,
            "data_version": version,
            "format_version": header.get("format-version") or "",
            "obo_id": term.term_id,
            "namespace": term.namespace,
            "synonyms": list(term.synonyms),
            "xrefs": list(term.xrefs),
            "parents": list(term.parents),
            "relationships": list(term.relationships),
            "is_obsolete": term.is_obsolete,
        },
    )


def fetch_obo_ontology_documents(
    source: str,
    *,
    source_url: str | None = None,
    max_records: int = 0,
    max_chars: int | None = 8000,
    include_obsolete: bool = False,
) -> Iterator[CorpusDocument]:
    source_key = clean_text(source).lower().replace("-", "_")
    policy = reference_source_policy(source_key)
    if str(policy.get("source_kind") or "reference_page") != "obo_ontology":
        raise ValueError(f"{source_key} is not an OBO ontology source")
    selected_url = clean_text(source_url or "")
    if not selected_url:
        urls = [str(value) for value in policy.get("default_urls") or []]
        if not urls:
            raise ValueError(f"{source_key} has no default OBO URL; pass --source-url")
        selected_url = urls[0]
    header, terms = obo_text_to_terms(_read_resource_bytes(selected_url, sleep_seconds=0.15))
    id_prefixes = tuple(str(value) for value in policy.get("id_prefixes") or [])
    emitted = 0
    for term in terms:
        if max_records and emitted >= max_records:
            return
        if term.is_obsolete and not include_obsolete:
            continue
        if id_prefixes and not any(term.term_id.startswith(prefix) for prefix in id_prefixes):
            continue
        yield obo_term_to_document(
            term,
            source=source_key,
            source_url=selected_url,
            policy=policy,
            header=header,
            max_chars=max_chars,
        )
        emitted += 1


def _direct_child_text(node: ET.Element, local_name: str) -> str:
    for child in node:
        if _local_name(child.tag) == local_name:
            return _node_text(child)
    return ""


def _direct_child(node: ET.Element, local_name: str) -> ET.Element | None:
    for child in node:
        if _local_name(child.tag) == local_name:
            return child
    return None


def read_bookshelf_oa_entries(file_list_url: str = NLM_LITARCH_FILE_LIST_CSV) -> list[BookshelfOAEntry]:
    payload = _read_resource_bytes(file_list_url, sleep_seconds=0.15).decode("utf-8-sig", errors="replace")
    entries: list[BookshelfOAEntry] = []
    for row in csv.DictReader(io.StringIO(payload)):
        archive_path = clean_text(row.get("File") or "")
        accession_id = clean_text(row.get("Accession ID") or "")
        if not archive_path or not accession_id:
            continue
        entries.append(
            BookshelfOAEntry(
                archive_path=archive_path,
                title=html.unescape(clean_text(row.get("Title") or "")),
                publisher=html.unescape(clean_text(row.get("Publisher") or "")),
                publication_year=clean_text(row.get("Publication Year") or ""),
                accession_id=accession_id,
                last_updated=clean_text(row.get("Last Updated (YYYY-MM-DD HH:MM:SS)") or ""),
            )
        )
    return entries


def _bookshelf_oa_entry_matches(
    entry: BookshelfOAEntry,
    *,
    terms: Iterable[str] = (),
    accession_ids: Iterable[str] = (),
) -> bool:
    wanted_ids = {clean_text(value).upper() for value in accession_ids if clean_text(value)}
    if wanted_ids and entry.accession_id.upper() not in wanted_ids:
        return False
    cleaned_terms = [clean_text(value).lower() for value in terms if clean_text(value)]
    if not cleaned_terms:
        return True
    haystack = " ".join([entry.title, entry.publisher, entry.publication_year, entry.accession_id]).lower()
    return any(term in haystack for term in cleaned_terms)


def _join_resource_path(base: str, path: str) -> str:
    if re.match(r"^[a-z][a-z0-9+.-]*://", base, flags=re.I):
        return urllib.parse.urljoin(base.rstrip("/") + "/", path)
    return str(Path(base).expanduser() / path)


def _bookshelf_oa_xml_license_text(root: ET.Element) -> str:
    parts: list[str] = []
    for node in root.iter():
        if _local_name(node.tag) in {"permissions", "license", "copyright-statement"}:
            text = _node_text(node)
            if text:
                parts.append(text)
    return clean_text(" ".join(dict.fromkeys(parts)))


def bookshelf_oa_nxml_to_document(
    payload: bytes | str,
    *,
    entry: BookshelfOAEntry,
    package_url: str,
    nxml_path: str,
    license_text: str = "",
    max_chars: int | None = 30000,
    min_chars: int = 300,
) -> CorpusDocument | None:
    root = ET.fromstring(payload)
    book_part_type = clean_text(root.attrib.get("book-part-type", ""))
    if book_part_type.lower() == "toc":
        return None
    book_title = _node_text(root.find("./book-meta/book-title-group/book-title"))
    subtitle = _node_text(root.find("./book-meta/book-title-group/subtitle"))
    part_title = _node_text(root.find("./book-part-meta/title-group/title"))
    abstract = clean_text(" ".join(_node_text(node) for node in root.findall("./book-meta/abstract")))
    body = _node_text(root.find("./body"))
    text = clean_text(
        " ".join(
            part
            for part in [
                entry.title,
                book_title if book_title != entry.title else "",
                subtitle,
                part_title,
                abstract,
                body,
            ]
            if part
        )
    )
    if len(text) < min_chars:
        return None
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0]
    xml_license = _bookshelf_oa_xml_license_text(root)
    return CorpusDocument(
        doc_id=f"BOOKSHELF_OA:{entry.accession_id}:{stable_doc_id(entry.archive_path, nxml_path)}",
        source="ncbi_bookshelf_oa",
        title=part_title or entry.title,
        text=text,
        metadata={
            "accession_id": entry.accession_id,
            "book_title": entry.title,
            "publisher": entry.publisher,
            "publication_year": entry.publication_year,
            "last_updated": entry.last_updated,
            "archive_path": entry.archive_path,
            "archive_url": package_url,
            "nxml_path": nxml_path,
            "book_part_type": book_part_type,
            "source_url": f"https://www.ncbi.nlm.nih.gov/books/{entry.accession_id}/",
            "source_license": clean_text(license_text),
            "xml_license": xml_license,
            "license_status": "nlm_litarch_open_access_subset",
            "terms_url": "https://www.ncbi.nlm.nih.gov/books/about/openaccess/",
            "retrieved_via": "nlm_litarch_ftp_open_access_subset",
        },
    )


def bookshelf_oa_archive_to_documents(
    payload: bytes,
    *,
    entry: BookshelfOAEntry,
    package_url: str,
    max_chars: int | None = 30000,
    min_chars: int = 300,
) -> Iterator[CorpusDocument]:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        license_text = ""
        members = archive.getmembers()
        for member in members:
            if member.isfile() and member.name.endswith("license.txt"):
                handle = archive.extractfile(member)
                if handle is not None:
                    license_text = handle.read().decode("utf-8", errors="replace")
                break
        for member in members:
            if not member.isfile() or not member.name.endswith(".nxml"):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            document = bookshelf_oa_nxml_to_document(
                handle.read(),
                entry=entry,
                package_url=package_url,
                nxml_path=member.name,
                license_text=license_text,
                max_chars=max_chars,
                min_chars=min_chars,
            )
            if document is not None:
                yield document


def fetch_bookshelf_oa_documents(
    *,
    file_list_url: str = NLM_LITARCH_FILE_LIST_CSV,
    package_base_url: str = NLM_LITARCH_BASE,
    terms: Iterable[str] = (),
    accession_ids: Iterable[str] = (),
    max_books: int = 3,
    max_records: int = 100,
    max_chars: int | None = 30000,
    min_chars: int = 300,
) -> Iterator[CorpusDocument]:
    entries = read_bookshelf_oa_entries(file_list_url)
    emitted = 0
    fetched_books = 0
    for entry in entries:
        if max_books and fetched_books >= max_books:
            return
        if max_records and emitted >= max_records:
            return
        if not _bookshelf_oa_entry_matches(entry, terms=terms, accession_ids=accession_ids):
            continue
        package_url = _join_resource_path(package_base_url, entry.archive_path)
        payload = _read_resource_bytes(package_url, sleep_seconds=0.15)
        fetched_books += 1
        for document in bookshelf_oa_archive_to_documents(
            payload,
            entry=entry,
            package_url=package_url,
            max_chars=max_chars,
            min_chars=min_chars,
        ):
            yield document
            emitted += 1
            if max_records and emitted >= max_records:
                return


def resolve_ncbi_api_key(api_key: str | None = None) -> str | None:
    return api_key or os.environ.get("NCBI") or os.environ.get("APIKEY") or None


def add_ncbi_api_key(params: dict[str, str], api_key: str | None = None) -> None:
    resolved = resolve_ncbi_api_key(api_key)
    if resolved:
        params["api_key"] = resolved


def fetch_pubmed_ids(
    *,
    term: str,
    retmax: int,
    email: str | None = None,
    api_key: str | None = None,
    tool: str = "query_expansion_vectors",
    sort: str = "relevance",
) -> list[str]:
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": str(retmax),
        "retmode": "json",
        "sort": sort,
        "tool": tool,
    }
    if email:
        params["email"] = email
    add_ncbi_api_key(params, api_key)
    url = f"{NCBI_EUTILS}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    payload = json.loads(_read_url(url).decode("utf-8"))
    return list(payload.get("esearchresult", {}).get("idlist", []))


def fetch_pubmed_documents(
    *,
    term: str,
    retmax: int = 100,
    email: str | None = None,
    api_key: str | None = None,
    tool: str = "query_expansion_vectors",
    batch_size: int = 100,
) -> Iterator[CorpusDocument]:
    ids = fetch_pubmed_ids(
        term=term,
        retmax=retmax,
        email=email,
        api_key=api_key,
        tool=tool,
    )
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "tool": tool,
        }
        if email:
            params["email"] = email
        add_ncbi_api_key(params, api_key)
        url = f"{NCBI_EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(_read_url(url))
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID") or ""
            title = clean_text(" ".join(article.findtext(".//ArticleTitle", "").split()))
            abstract_parts = [
                "".join(node.itertext())
                for node in article.findall(".//Abstract/AbstractText")
            ]
            abstract = clean_text(" ".join(abstract_parts))
            text = clean_text(" ".join(part for part in [title, abstract] if part))
            if not pmid or not text:
                continue
            yield CorpusDocument(
                doc_id=f"PMID:{pmid}",
                source="pubmed",
                title=title,
                text=text,
                metadata={"pmid": pmid, "query": term},
            )


def read_pubmed_topics(path: str | Path, *, default_retmax: int) -> list[PubMedTopic]:
    topics = []
    with Path(path).expanduser().open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        required = {"topic", "term"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("topic file must be TSV with topic and term columns")
        for line_number, row in enumerate(reader, start=2):
            topic = (row.get("topic") or "").strip()
            term = (row.get("term") or "").strip()
            retmax_text = (row.get("retmax") or "").strip()
            if not topic and not term:
                continue
            if not topic or not term:
                raise ValueError(f"{path}:{line_number}: topic and term are required")
            retmax = int(retmax_text) if retmax_text else default_retmax
            if retmax <= 0:
                raise ValueError(f"{path}:{line_number}: retmax must be positive")
            topics.append(PubMedTopic(topic=topic, term=term, retmax=retmax))
    return topics


def fetch_pubmed_topic_documents(
    topics: Iterable[PubMedTopic],
    *,
    default_retmax: int,
    email: str | None = None,
    api_key: str | None = None,
    tool: str = "query_expansion_vectors",
    batch_size: int = 100,
) -> Iterator[CorpusDocument]:
    seen_pmids: set[str] = set()
    for topic in topics:
        retmax = topic.retmax if topic.retmax is not None else default_retmax
        for document in fetch_pubmed_documents(
            term=topic.term,
            retmax=retmax,
            email=email,
            api_key=api_key,
            tool=tool,
            batch_size=batch_size,
        ):
            pmid = str(document.metadata.get("pmid", ""))
            if pmid and pmid in seen_pmids:
                continue
            if pmid:
                seen_pmids.add(pmid)
            metadata = {
                **document.metadata,
                "topic": topic.topic,
                "topic_query": topic.term,
            }
            yield CorpusDocument(
                doc_id=document.doc_id,
                source=document.source,
                title=document.title,
                text=document.text,
                metadata=metadata,
            )


def fetch_europepmc_documents(
    *,
    query: str,
    max_records: int = 100,
    page_size: int = 100,
) -> Iterator[CorpusDocument]:
    cursor = "*"
    fetched = 0
    while fetched < max_records:
        size = min(page_size, max_records - fetched)
        params = {
            "query": query,
            "format": "json",
            "pageSize": str(size),
            "cursorMark": cursor,
        }
        url = f"{EUROPE_PMC_SEARCH}?{urllib.parse.urlencode(params)}"
        payload = json.loads(_read_url(url).decode("utf-8"))
        results = payload.get("resultList", {}).get("result", [])
        if not results:
            break
        for result in results:
            source = result.get("source") or "EUROPEPMC"
            identifier = result.get("id") or result.get("pmid") or result.get("pmcid")
            title = clean_text(result.get("title") or "")
            abstract = clean_text(result.get("abstractText") or "")
            text = clean_text(" ".join(part for part in [title, abstract] if part))
            if not identifier or not text:
                continue
            fetched += 1
            yield CorpusDocument(
                doc_id=f"EUROPEPMC:{source}:{identifier}",
                source="europepmc",
                title=title,
                text=text,
                metadata={
                    "source": source,
                    "id": identifier,
                    "pmid": result.get("pmid", ""),
                    "pmcid": result.get("pmcid", ""),
                    "doi": result.get("doi", ""),
                    "query": query,
                    "is_open_access": result.get("isOpenAccess", ""),
                },
            )
            if fetched >= max_records:
                break
        next_cursor = payload.get("nextCursorMark")
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor


def fetch_europepmc_topic_documents(
    topics: Iterable[PubMedTopic],
    *,
    default_max_records: int,
    page_size: int = 100,
) -> Iterator[CorpusDocument]:
    seen_ids: set[str] = set()
    for topic in topics:
        max_records = topic.retmax if topic.retmax is not None else default_max_records
        for document in fetch_europepmc_documents(
            query=topic.term,
            max_records=max_records,
            page_size=page_size,
        ):
            pmid = str(document.metadata.get("pmid", "")).strip()
            pmcid = str(document.metadata.get("pmcid", "")).strip()
            doi = str(document.metadata.get("doi", "")).strip().lower()
            identifier = pmid or pmcid or doi or document.doc_id
            if identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            metadata = {
                **document.metadata,
                "topic": topic.topic,
                "topic_query": topic.term,
            }
            yield CorpusDocument(
                doc_id=document.doc_id,
                source=document.source,
                title=document.title,
                text=document.text,
                metadata=metadata,
            )


def normalize_pmcid(value: str | int | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.upper().startswith("PMC"):
        suffix = text[3:]
    else:
        suffix = text
    digits = re.sub(r"\D", "", suffix)
    return f"PMC{digits}" if digits else ""


def pmcid_numeric(value: str | int | None) -> str:
    pmcid = normalize_pmcid(value)
    return pmcid[3:] if pmcid.startswith("PMC") else ""


def pmc_open_access_query(query: str) -> str:
    query = query.strip()
    if not query:
        raise ValueError("query is required")
    return f"({query}) AND {PMC_OPEN_ACCESS_FILTER}"


def fetch_pmc_oa_ids(
    *,
    query: str,
    retmax: int,
    email: str | None = None,
    api_key: str | None = None,
    tool: str = "query_expansion_vectors",
    sort: str = "relevance",
) -> list[str]:
    params = {
        "db": "pmc",
        "term": pmc_open_access_query(query),
        "retmax": str(retmax),
        "retmode": "json",
        "sort": sort,
        "tool": tool,
    }
    if email:
        params["email"] = email
    add_ncbi_api_key(params, api_key)
    url = f"{NCBI_EUTILS}/esearch.fcgi?{urllib.parse.urlencode(params)}"
    payload = json.loads(_read_url(url).decode("utf-8"))
    return [pmcid_numeric(item) for item in payload.get("esearchresult", {}).get("idlist", []) if pmcid_numeric(item)]


def _chunked(values: list[str], size: int) -> Iterator[list[str]]:
    if size <= 0:
        raise ValueError("batch_size must be positive")
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return clean_text(" ".join(" ".join(node.itertext()).split()))


def _article_id(article: ET.Element, id_type: str) -> str:
    for node in article.findall(".//article-id"):
        if node.attrib.get("pub-id-type") == id_type:
            return clean_text("".join(node.itertext()))
    return ""


def _article_id_any(article: ET.Element, *id_types: str) -> str:
    for id_type in id_types:
        value = _article_id(article, id_type)
        if value:
            return value
    return ""


def _article_title(article: ET.Element) -> str:
    return _node_text(article.find(".//front/article-meta/title-group/article-title"))


def _article_abstract(article: ET.Element) -> str:
    return clean_text(" ".join(_node_text(node) for node in article.findall(".//front/article-meta/abstract")))


def _article_body(article: ET.Element) -> str:
    body = article.find(".//body")
    if body is None:
        return ""
    parts = []
    for node in body.iter():
        if _local_name(node.tag) in {"title", "p"}:
            text = _node_text(node)
            if text:
                parts.append(text)
    return clean_text(" ".join(parts))


def _article_journal(article: ET.Element) -> str:
    return _node_text(article.find(".//front/journal-meta/journal-title-group/journal-title"))


def _article_year(article: ET.Element) -> str:
    for node in article.findall(".//front/article-meta/pub-date/year"):
        value = clean_text("".join(node.itertext()))
        if value:
            return value
    return ""


def _article_license(article: ET.Element) -> str:
    for node in article.findall(".//front/article-meta/custom-meta-group/custom-meta"):
        name = _node_text(node.find("meta-name"))
        if name == "pmc-license-ref":
            value = _node_text(node.find("meta-value"))
            if value:
                return value
    for node in article.findall(".//front/article-meta/permissions/license"):
        license_type = (node.attrib.get("license-type") or "").strip()
        if license_type:
            return license_type
        for key, value in node.attrib.items():
            if key.endswith("href") and value:
                return clean_text(value)
    return ""


def _pmc_articles(root: ET.Element) -> list[ET.Element]:
    if _local_name(root.tag) == "article":
        return [root]
    return [node for node in root.findall(".//article") if _local_name(node.tag) == "article"]


def pmc_oa_article_to_document(
    article: ET.Element,
    *,
    query: str = "",
    max_chars: int | None = None,
) -> CorpusDocument | None:
    pmcid = normalize_pmcid(_article_id_any(article, "pmcid", "pmc", "pmcaid"))
    if not pmcid:
        return None
    title = _article_title(article)
    abstract = _article_abstract(article)
    body = _article_body(article)
    text = clean_text(" ".join(part for part in [abstract, body] if part))
    if max_chars is not None and max_chars > 0:
        text = text[:max_chars].rsplit(" ", 1)[0] if len(text) > max_chars else text
    if not text:
        return None
    pmid = _article_id(article, "pmid")
    doi = _article_id(article, "doi")
    return CorpusDocument(
        doc_id=f"PMCID:{pmcid}",
        source="pmc_oa",
        title=title,
        text=text,
        metadata={
            "pmcid": pmcid,
            "pmid": pmid,
            "doi": doi,
            "journal": _article_journal(article),
            "publication_year": _article_year(article),
            "license": _article_license(article),
            "query": query,
            "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
            "retrieved_via": "ncbi_efetch_pmc_open_access",
        },
    )


def fetch_pmc_oa_documents(
    *,
    query: str,
    max_records: int = 100,
    email: str | None = None,
    api_key: str | None = None,
    tool: str = "query_expansion_vectors",
    batch_size: int = 50,
    max_chars: int | None = None,
) -> Iterator[CorpusDocument]:
    ids = fetch_pmc_oa_ids(
        query=query,
        retmax=max_records,
        email=email,
        api_key=api_key,
        tool=tool,
    )
    emitted = 0
    for batch in _chunked(ids, batch_size):
        params = {
            "db": "pmc",
            "id": ",".join(batch),
            "retmode": "xml",
            "tool": tool,
        }
        if email:
            params["email"] = email
        add_ncbi_api_key(params, api_key)
        url = f"{NCBI_EUTILS}/efetch.fcgi?{urllib.parse.urlencode(params)}"
        root = ET.fromstring(_read_url(url))
        for article in _pmc_articles(root):
            document = pmc_oa_article_to_document(article, query=query, max_chars=max_chars)
            if document is None:
                continue
            yield document
            emitted += 1
            if emitted >= max_records:
                return


def fetch_pmc_oa_topic_documents(
    topics: Iterable[PubMedTopic],
    *,
    default_max_records: int,
    email: str | None = None,
    api_key: str | None = None,
    tool: str = "query_expansion_vectors",
    batch_size: int = 50,
    max_chars: int | None = None,
) -> Iterator[CorpusDocument]:
    seen_ids: set[str] = set()
    for topic in topics:
        max_records = topic.retmax if topic.retmax is not None else default_max_records
        for document in fetch_pmc_oa_documents(
            query=topic.term,
            max_records=max_records,
            email=email,
            api_key=api_key,
            tool=tool,
            batch_size=batch_size,
            max_chars=max_chars,
        ):
            pmcid = str(document.metadata.get("pmcid", "")).strip()
            pmid = str(document.metadata.get("pmid", "")).strip()
            doi = str(document.metadata.get("doi", "")).strip().lower()
            identifier = pmcid or pmid or doi or document.doc_id
            if identifier in seen_ids:
                continue
            seen_ids.add(identifier)
            metadata = {
                **document.metadata,
                "topic": topic.topic,
                "topic_query": topic.term,
            }
            yield CorpusDocument(
                doc_id=document.doc_id,
                source=document.source,
                title=document.title,
                text=document.text,
                metadata=metadata,
            )


def _clinicaltrials_module(study: dict, name: str) -> dict:
    protocol = study.get("protocolSection") or {}
    module = protocol.get(name) or {}
    return module if isinstance(module, dict) else {}


def _clinicaltrials_intervention_text(intervention: dict) -> str:
    name = strip_markup(intervention.get("name"))
    kind = strip_markup(intervention.get("type"))
    description = strip_markup(intervention.get("description"))
    parts = []
    if kind and name:
        parts.append(f"{kind}: {name}")
    elif name:
        parts.append(name)
    elif kind:
        parts.append(kind)
    if description:
        parts.append(description)
    return clean_text(". ".join(parts))


def clinicaltrials_study_to_document(study: dict, *, query: str = "") -> CorpusDocument | None:
    identification = _clinicaltrials_module(study, "identificationModule")
    description = _clinicaltrials_module(study, "descriptionModule")
    conditions = _clinicaltrials_module(study, "conditionsModule")
    arms = _clinicaltrials_module(study, "armsInterventionsModule")
    eligibility = _clinicaltrials_module(study, "eligibilityModule")
    design = _clinicaltrials_module(study, "designModule")
    status = _clinicaltrials_module(study, "statusModule")
    outcomes = _clinicaltrials_module(study, "outcomesModule")

    nct_id = clean_text(str(identification.get("nctId") or ""))
    if not nct_id:
        return None
    title = strip_markup(identification.get("briefTitle") or identification.get("officialTitle"))
    official_title = strip_markup(identification.get("officialTitle"))
    condition_names = _list_text(conditions.get("conditions") or [])
    intervention_items = [
        item for item in arms.get("interventions") or [] if isinstance(item, dict)
    ]
    intervention_texts = [
        text for text in (_clinicaltrials_intervention_text(item) for item in intervention_items) if text
    ]
    intervention_names = _list_text(item.get("name", "") for item in intervention_items)
    intervention_types = _list_text(item.get("type", "") for item in intervention_items)
    primary_outcomes = _list_text(
        outcome.get("measure", "")
        for outcome in outcomes.get("primaryOutcomes") or []
        if isinstance(outcome, dict)
    )
    secondary_outcomes = _list_text(
        outcome.get("measure", "")
        for outcome in outcomes.get("secondaryOutcomes") or []
        if isinstance(outcome, dict)
    )

    population_parts = _list_text(
        [
            eligibility.get("sex", ""),
            eligibility.get("minimumAge", ""),
            eligibility.get("maximumAge", ""),
            eligibility.get("healthyVolunteers", ""),
        ]
    )
    text_parts = [
        title,
        official_title if official_title != title else "",
        strip_markup(description.get("briefSummary")),
        strip_markup(description.get("detailedDescription")),
        f"Conditions: {', '.join(condition_names)}." if condition_names else "",
        f"Interventions: {'; '.join(intervention_texts)}." if intervention_texts else "",
        f"Eligibility: {strip_markup(eligibility.get('eligibilityCriteria'))}" if eligibility.get("eligibilityCriteria") else "",
        f"Population: {', '.join(population_parts)}." if population_parts else "",
        f"Primary outcomes: {', '.join(primary_outcomes)}." if primary_outcomes else "",
        f"Secondary outcomes: {', '.join(secondary_outcomes)}." if secondary_outcomes else "",
    ]
    text = clean_text(" ".join(part for part in text_parts if part))
    if not text:
        return None
    return CorpusDocument(
        doc_id=f"NCT:{nct_id}",
        source="clinicaltrials_gov",
        title=title,
        text=text,
        metadata={
            "nct_id": nct_id,
            "query": query,
            "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
            "overall_status": status.get("overallStatus", ""),
            "study_type": design.get("studyType", ""),
            "phases": design.get("phases", []),
            "conditions": condition_names,
            "interventions": intervention_names,
            "intervention_types": intervention_types,
            "retrieved_via": "clinicaltrials_gov_api_v2",
        },
    )


def fetch_clinicaltrials_documents(
    *,
    query: str,
    max_records: int = 100,
    page_size: int = 25,
) -> Iterator[CorpusDocument]:
    fetched = 0
    page_token = ""
    while fetched < max_records:
        params = {
            "query.term": query,
            "format": "json",
            "pageSize": str(min(page_size, max_records - fetched)),
        }
        if page_token:
            params["pageToken"] = page_token
        url = f"{CLINICALTRIALS_STUDIES}?{urllib.parse.urlencode(params)}"
        payload = json.loads(_read_url(url, sleep_seconds=0.15).decode("utf-8"))
        studies = payload.get("studies") or []
        if not studies:
            break
        for study in studies:
            if not isinstance(study, dict):
                continue
            document = clinicaltrials_study_to_document(study, query=query)
            if document is None:
                continue
            yield document
            fetched += 1
            if fetched >= max_records:
                return
        page_token = payload.get("nextPageToken") or ""
        if not page_token:
            break


def resolve_medlineplus_xml_url(
    *,
    index_url: str = MEDLINEPLUS_XML_INDEX,
    prefer_compressed: bool = True,
) -> str:
    payload = _read_url(index_url, sleep_seconds=0.1).decode("utf-8", errors="replace")
    hrefs = re.findall(r'href=["\']([^"\']*mplus_topics[^"\']*\.(?:xml|zip))["\']', payload, flags=re.I)
    if not hrefs:
        raise ValueError(f"could not find a MedlinePlus health topic XML link at {index_url}")
    normalized = [urllib.parse.urljoin(index_url, href) for href in hrefs]
    if prefer_compressed:
        for href in normalized:
            if href.lower().endswith(".zip"):
                return href
    for href in normalized:
        if href.lower().endswith(".xml"):
            return href
    return normalized[0]


def _medlineplus_xml_root(payload: bytes) -> ET.Element:
    if payload[:4] == b"PK\x03\x04":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            if not xml_names:
                raise ValueError("MedlinePlus zip did not contain an XML file")
            with archive.open(xml_names[0]) as handle:
                return ET.fromstring(handle.read())
    return ET.fromstring(payload)


def _medlineplus_values(topic: ET.Element, path: str) -> list[str]:
    return [value for value in (_node_text(node) for node in topic.findall(path)) if value]


def medlineplus_topic_to_document(
    topic: ET.Element,
    *,
    source_url: str = "",
    include_spanish: bool = False,
) -> CorpusDocument | None:
    language = clean_text(topic.attrib.get("language", ""))
    if language and language.lower() != "english" and not include_spanish:
        return None
    topic_id = clean_text(topic.attrib.get("id", ""))
    url = clean_text(topic.attrib.get("url", ""))
    title = clean_text(topic.attrib.get("title", "")) or _node_text(topic.find("title"))
    if not topic_id or not title:
        return None
    also_called = _medlineplus_values(topic, "also-called")
    see_references = _medlineplus_values(topic, "see-reference")
    groups = _medlineplus_values(topic, "group")
    mesh = _medlineplus_values(topic, ".//mesh-heading/descriptor")
    summary = strip_markup(_node_text(topic.find("full-summary")))
    meta_description = strip_markup(_node_text(topic.find("meta-desc")))
    text_parts = [
        title,
        f"Also called: {', '.join(also_called)}." if also_called else "",
        f"See also: {', '.join(see_references)}." if see_references else "",
        f"Groups: {', '.join(groups)}." if groups else "",
        f"MeSH headings: {', '.join(mesh)}." if mesh else "",
        meta_description,
        summary,
    ]
    text = clean_text(" ".join(part for part in text_parts if part))
    if not text:
        return None
    return CorpusDocument(
        doc_id=f"MEDLINEPLUS:{topic_id}",
        source="medlineplus",
        title=title,
        text=text,
        metadata={
            "id": topic_id,
            "url": url,
            "language": language,
            "also_called": also_called,
            "see_references": see_references,
            "groups": groups,
            "mesh_headings": mesh,
            "source_url": source_url,
            "retrieved_via": "medlineplus_health_topic_xml",
        },
    )


def fetch_medlineplus_health_topic_documents(
    *,
    source_url: str | None = None,
    max_records: int = 500,
    include_spanish: bool = False,
    prefer_compressed: bool = True,
) -> Iterator[CorpusDocument]:
    resolved_url = source_url or resolve_medlineplus_xml_url(prefer_compressed=prefer_compressed)
    payload = _read_url(resolved_url, sleep_seconds=0.1)
    root = _medlineplus_xml_root(payload)
    emitted = 0
    for topic in root.findall(".//health-topic"):
        document = medlineplus_topic_to_document(
            topic,
            source_url=resolved_url,
            include_spanish=include_spanish,
        )
        if document is None:
            continue
        yield document
        emitted += 1
        if max_records and emitted >= max_records:
            return


def _first_text(node: ET.Element, *names: str) -> str:
    wanted = set(names)
    for child in node:
        if _local_name(child.tag) in wanted:
            return _node_text(child)
    return ""


def _child_values(node: ET.Element, child_name: str, value_name: str = "name") -> list[str]:
    values: list[str] = []
    for child in node.iter():
        if _local_name(child.tag) != child_name:
            continue
        value = _first_text(child, value_name)
        if value:
            values.append(value)
    return values


def _summary_texts(summary: ET.Element) -> list[str]:
    texts: list[str] = []
    for text_node in summary.iter():
        if _local_name(text_node.tag) != "text":
            continue
        role = _first_text(text_node, "text-role")
        html_node = _direct_child(text_node, "html")
        body = strip_markup(_node_text(html_node or text_node))
        if not body:
            continue
        texts.append(f"{role}: {body}" if role else body)
    return texts


def medlineplus_genetics_summary_to_document(summary: ET.Element) -> CorpusDocument | None:
    summary_type = _local_name(summary.tag).replace("-summary", "")
    summary_id = clean_text(summary.attrib.get("id", ""))
    if not summary_id:
        return None
    if summary_type == "gene":
        title = _first_text(summary, "gene-symbol") or _first_text(summary, "name")
        name = _first_text(summary, "name")
    else:
        title = _first_text(summary, "name")
        name = title
    if not title:
        return None
    synonyms = _child_values(summary, "synonym", "synonym")
    related_conditions = _child_values(summary, "related-health-condition")
    related_genes = _child_values(summary, "related-gene")
    related_chromosomes = _child_values(summary, "related-chromosome")
    db_keys = []
    for db_key in summary.iter():
        if _local_name(db_key.tag) != "db-key":
            continue
        db = _first_text(db_key, "db")
        key = _first_text(db_key, "key")
        if db and key:
            db_keys.append(f"{db}:{key}")
    text_parts = [
        title,
        name if name and name != title else "",
        f"Synonyms: {', '.join(synonyms)}." if synonyms else "",
        f"Related conditions: {', '.join(related_conditions)}." if related_conditions else "",
        f"Related genes: {', '.join(related_genes)}." if related_genes else "",
        f"Related chromosomes: {', '.join(related_chromosomes)}." if related_chromosomes else "",
        *_summary_texts(summary),
    ]
    text = clean_text(" ".join(part for part in text_parts if part))
    if not text:
        return None
    page = _first_text(summary, "ghr-page")
    return CorpusDocument(
        doc_id=f"MEDLINEPLUS_GENETICS:{summary_type}:{summary_id}",
        source="medlineplus_genetics",
        title=title,
        text=text,
        metadata={
            "id": summary_id,
            "summary_type": summary_type,
            "name": name,
            "url": page,
            "synonyms": synonyms,
            "related_conditions": related_conditions,
            "related_genes": related_genes,
            "related_chromosomes": related_chromosomes,
            "db_keys": db_keys,
            "reviewed": _first_text(summary, "reviewed"),
            "published": _first_text(summary, "published"),
            "retrieved_via": "medlineplus_genetics_ghr_summaries_xml",
        },
    )


def fetch_medlineplus_genetics_documents(
    *,
    source_url: str = MEDLINEPLUS_GENETICS_SUMMARIES,
    max_records: int = 500,
    include_types: Iterable[str] = ("health-condition", "gene", "chromosome"),
) -> Iterator[CorpusDocument]:
    include = set(include_types)
    local_path = Path(source_url).expanduser()
    payload = local_path.read_bytes() if local_path.exists() else _read_url(source_url, sleep_seconds=0.1)
    root = ET.fromstring(payload)
    emitted = 0
    for summary in root:
        summary_type = _local_name(summary.tag).replace("-summary", "")
        if include and summary_type not in include:
            continue
        document = medlineplus_genetics_summary_to_document(summary)
        if document is None:
            continue
        yield document
        emitted += 1
        if max_records and emitted >= max_records:
            return


def _collect_setids(payload: object) -> list[str]:
    found: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() == "setid" and isinstance(child, str) and child.strip():
                    found.append(clean_text(child))
                else:
                    walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    unique: list[str] = []
    seen: set[str] = set()
    for setid in found:
        key = setid.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(setid)
    return unique


def fetch_dailymed_setids_for_drug(
    drug_name: str,
    *,
    max_records: int = 3,
    page_size: int = 20,
) -> list[str]:
    if max_records <= 0:
        return []
    setids: list[str] = []
    page = 1
    while len(setids) < max_records:
        params = {
            "drug_name": drug_name,
            "name_type": "both",
            "pagesize": str(max(1, min(page_size, max_records - len(setids)))),
            "page": str(page),
        }
        url = f"{DAILYMED_SPLS}?{urllib.parse.urlencode(params)}"
        payload = json.loads(_read_url(url, sleep_seconds=0.15).decode("utf-8"))
        page_setids = _collect_setids(payload)
        if not page_setids:
            break
        before = len(setids)
        seen = {value.lower() for value in setids}
        for setid in page_setids:
            if setid.lower() in seen:
                continue
            setids.append(setid)
            seen.add(setid.lower())
            if len(setids) >= max_records:
                break
        if len(setids) == before:
            break
        page += 1
    return setids


def _dailymed_document_title(root: ET.Element) -> str:
    title = _direct_child_text(root, "title")
    if title:
        return title
    for node in root.iter():
        if _local_name(node.tag) == "title":
            return _node_text(node)
    return ""


def _dailymed_section_heading(section: ET.Element) -> str:
    title = _direct_child_text(section, "title")
    code = _direct_child(section, "code")
    display = ""
    if code is not None:
        display = clean_text(code.attrib.get("displayName", ""))
    return title or display


def _dailymed_section_is_relevant(heading: str) -> bool:
    key = re.sub(r"\s+", " ", heading.lower())
    return any(keyword in key for keyword in DAILYMED_SECTION_KEYWORDS)


def _dailymed_section_text(section: ET.Element) -> str:
    parts: list[str] = []
    for node in section.iter():
        local = _local_name(node.tag)
        if local in {"title", "paragraph", "item", "content", "caption"}:
            text = _node_text(node)
            if text:
                parts.append(text)
    return clean_text(" ".join(parts))


def dailymed_spl_to_document(
    root: ET.Element,
    *,
    setid: str,
    drug_name: str = "",
    max_chars: int | None = 20000,
) -> CorpusDocument | None:
    setid = clean_text(setid)
    if not setid:
        return None
    title = _dailymed_document_title(root)
    section_parts: list[str] = []
    section_titles: list[str] = []
    for section in root.iter():
        if _local_name(section.tag) != "section":
            continue
        heading = _dailymed_section_heading(section)
        if not heading or not _dailymed_section_is_relevant(heading):
            continue
        text = _dailymed_section_text(section)
        if not text:
            continue
        section_titles.append(heading)
        section_parts.append(f"{heading}: {text}")
    text = clean_text(" ".join(part for part in [title, *section_parts] if part))
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0]
    if not text:
        return None
    return CorpusDocument(
        doc_id=f"DAILYMED:{setid}",
        source="dailymed",
        title=title or drug_name,
        text=text,
        metadata={
            "setid": setid,
            "drug_name": drug_name,
            "section_titles": section_titles,
            "source_url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={urllib.parse.quote(setid)}",
            "retrieved_via": "dailymed_services_v2_spls",
        },
    )


def read_dailymed_setids_from_mrsat(
    path: str | Path,
    *,
    max_records: int = 100,
    atn_hints: Iterable[str] = DAILYMED_MRSAT_ATN_HINTS,
) -> list[str]:
    hints = tuple(hint.lower() for hint in atn_hints if hint)
    setids: list[str] = []
    seen: set[str] = set()
    with Path(path).expanduser().open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            columns = line.rstrip("\n").split("|")
            if columns and columns[-1] == "":
                columns = columns[:-1]
            if len(columns) < 11:
                continue
            atn = columns[8].lower()
            atv = columns[10]
            if hints and not any(hint in atn for hint in hints):
                continue
            match = DAILYMED_SETID_RE.search(atv)
            if not match:
                continue
            setid = match.group(0).lower()
            if setid in seen:
                continue
            seen.add(setid)
            setids.append(setid)
            if max_records and len(setids) >= max_records:
                break
    return setids


def fetch_dailymed_document_by_setid(
    setid: str,
    *,
    drug_name: str = "",
    max_chars: int | None = 20000,
) -> CorpusDocument | None:
    setid = clean_text(setid)
    if not setid:
        return None
    url = DAILYMED_SPL_XML.format(setid=urllib.parse.quote(setid))
    root = ET.fromstring(_read_url(url, sleep_seconds=0.15))
    return dailymed_spl_to_document(
        root,
        setid=setid,
        drug_name=drug_name,
        max_chars=max_chars,
    )


def fetch_dailymed_documents(
    drug_names: Iterable[str],
    *,
    setids: Iterable[str] = (),
    max_labels_per_drug: int = 2,
    max_records: int = 20,
    page_size: int = 20,
    max_chars: int | None = 20000,
) -> Iterator[CorpusDocument]:
    emitted = 0
    seen_setids: set[str] = set()
    for setid in setids:
        key = clean_text(setid).lower()
        if not key or key in seen_setids:
            continue
        seen_setids.add(key)
        document = fetch_dailymed_document_by_setid(
            setid,
            max_chars=max_chars,
        )
        if document is None:
            continue
        yield document
        emitted += 1
        if max_records and emitted >= max_records:
            return
    for drug_name in drug_names:
        drug_name = clean_text(drug_name)
        if not drug_name:
            continue
        setids = fetch_dailymed_setids_for_drug(
            drug_name,
            max_records=max_labels_per_drug,
            page_size=page_size,
        )
        for setid in setids:
            key = setid.lower()
            if key in seen_setids:
                continue
            seen_setids.add(key)
            document = fetch_dailymed_document_by_setid(
                setid=setid,
                drug_name=drug_name,
                max_chars=max_chars,
            )
            if document is None:
                continue
            yield document
            emitted += 1
            if max_records and emitted >= max_records:
                return
