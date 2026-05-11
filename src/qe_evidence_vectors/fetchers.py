from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .corpus import stable_doc_id
from .schema import CorpusDocument
from .text import clean_text


NCBI_EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPE_PMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PMC_OPEN_ACCESS_FILTER = "open_access[filter]"


@dataclass(frozen=True)
class PubMedTopic:
    topic: str
    term: str
    retmax: int | None = None


def _read_url(url: str, *, sleep_seconds: float = 0.34) -> bytes:
    with urllib.request.urlopen(url) as response:
        payload = response.read()
    if sleep_seconds:
        time.sleep(sleep_seconds)
    return payload


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
    return clean_text(" ".join("".join(node.itertext()).split()))


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
