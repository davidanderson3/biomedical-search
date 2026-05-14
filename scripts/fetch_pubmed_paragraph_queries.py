#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


def split_values(value: str) -> list[str]:
    normalized = value.replace(",", "|").replace(";", "|")
    return [part.strip() for part in normalized.split("|") if part.strip()]


def read_topics(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            row
            for row in csv.DictReader(
                (line for line in handle if line.strip() and not line.lstrip().startswith("#")),
                delimiter="\t",
            )
            if (row.get("id") or "").strip()
        ]


def request_text(url: str, *, delay: float, retries: int) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if delay:
            time.sleep(delay)
        request = Request(
            url,
            headers={
                "Accept": "application/xml,application/json",
                "User-Agent": "query-expansion-pubmed-paragraph-fetcher/1.0",
            },
        )
        try:
            with urlopen(request, timeout=45) as response:
                return response.read().decode("utf-8", errors="replace")
        except HTTPError as err:
            last_error = err
            if err.code not in {429, 500, 502, 503, 504}:
                raise
        except URLError as err:
            last_error = err
        time.sleep(min(30.0, 2.0 * (attempt + 1)))
    raise RuntimeError(f"request failed after retries: {last_error}")


def eutils_url(endpoint: str, params: dict[str, str | int]) -> str:
    return f"{EUTILS_BASE}/{endpoint}?{urlencode(params)}"


def search_pmids(topic: dict[str, str], *, email: str, api_key: str, delay: float, retries: int) -> list[str]:
    explicit_pmids = split_values(topic.get("pmids") or "")
    if explicit_pmids:
        invalid = [pmid for pmid in explicit_pmids if not re.fullmatch(r"\d+", pmid)]
        if invalid:
            topic_id = topic.get("id") or "<unknown topic>"
            raise ValueError(f"{topic_id} has nonnumeric PMID values in the pmids column: {', '.join(invalid)}")
        return explicit_pmids
    term = (topic.get("term") or "").strip()
    if not term:
        return []
    params: dict[str, str | int] = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retmax": int(topic.get("retmax") or 1),
        "sort": "relevance",
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    payload = json.loads(request_text(eutils_url("esearch.fcgi", params), delay=delay, retries=retries))
    return [str(value) for value in payload.get("esearchresult", {}).get("idlist", []) if value]


def text_for(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def fetch_articles(pmids: list[str], *, email: str, api_key: str, delay: float, retries: int) -> list[dict[str, str]]:
    if not pmids:
        return []
    params: dict[str, str | int] = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    root = ET.fromstring(request_text(eutils_url("efetch.fcgi", params), delay=delay, retries=retries))
    rows = []
    for article in root.findall(".//PubmedArticle"):
        pmid = text_for(article.find(".//PMID"))
        title = text_for(article.find(".//ArticleTitle"))
        abstract_parts = []
        for item in article.findall(".//Abstract/AbstractText"):
            label = (item.attrib.get("Label") or "").strip()
            text = text_for(item)
            if not text:
                continue
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = " ".join(abstract_parts)
        if pmid and (title or abstract):
            rows.append({"pmid": pmid, "title": title, "abstract": abstract})
    return rows


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["id", "query", "expected_cuis", "why", "disallowed_cuis"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch PubMed abstracts into a paragraph-query TSV for local quality testing.")
    parser.add_argument("--topics", type=Path, default=ROOT / "config" / "pubmed_paragraph_topics.tsv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "build" / "pubmed_paragraph_tests")
    parser.add_argument("--email", default="", help="Optional NCBI contact email.")
    parser.add_argument("--api-key", default="", help="Optional NCBI API key.")
    parser.add_argument("--delay", type=float, default=0.4, help="Delay before each NCBI request.")
    parser.add_argument("--retries", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    topics = read_topics(args.topics)
    query_rows: list[dict[str, str]] = []
    paragraph_rows: list[str] = []
    record_rows: list[dict[str, str]] = []
    for topic in topics:
        topic_id = (topic.get("id") or "").strip()
        pmids = search_pmids(topic, email=args.email, api_key=args.api_key, delay=args.delay, retries=args.retries)
        articles = fetch_articles(pmids, email=args.email, api_key=args.api_key, delay=args.delay, retries=args.retries)
        for article in articles:
            query = " ".join(
                part
                for part in [
                    f"PubMed PMID {article['pmid']}.",
                    article.get("title", ""),
                    article.get("abstract", ""),
                ]
                if part
            )
            row_id = f"{topic_id}_{article['pmid']}"
            query_rows.append(
                {
                    "id": row_id,
                    "query": query,
                    "expected_cuis": topic.get("expected_cuis") or "",
                    "why": f"{topic.get('why') or ''} PMID {article['pmid']}.",
                    "disallowed_cuis": topic.get("disallowed_cuis") or "",
                }
            )
            paragraph_rows.append(query)
            record_rows.append({**topic, **article, "id": row_id})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_tsv(args.output_dir / "pubmed_paragraph_queries.tsv", query_rows)
    (args.output_dir / "pubmed_paragraphs.json").write_text(
        json.dumps(paragraph_rows, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (args.output_dir / "pubmed_records.jsonl").open("w", encoding="utf-8") as handle:
        for row in record_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps({"topics": len(topics), "abstracts": len(query_rows), "output_dir": str(args.output_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
