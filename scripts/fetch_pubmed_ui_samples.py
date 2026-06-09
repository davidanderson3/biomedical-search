#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DEFAULT_TERM = "patients[tiab] AND hasabstract[text] AND english[lang]"


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\t", " ").replace("\r", " ").replace("\n", " ")
    return " ".join(value.split())


def ascii_safe(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def request_text(url: str, *, delay: float, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        if delay:
            time.sleep(delay)
        request = Request(
            url,
            headers={
                "Accept": "application/xml,application/json",
                "User-Agent": "query-expansion-pubmed-ui-sampler/1.0",
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
        time.sleep(min(12.0, 1.5 * (attempt + 1)))
    raise RuntimeError(f"request failed after retries: {last_error}")


def eutils_url(endpoint: str, params: dict[str, str | int]) -> str:
    return f"{EUTILS_BASE}/{endpoint}?{urlencode(params)}"


def pubmed_search(
    term: str,
    *,
    retstart: int = 0,
    retmax: int = 0,
    email: str = "",
    api_key: str = "",
    delay: float = 0.34,
) -> dict:
    params: dict[str, str | int] = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "retstart": retstart,
        "retmax": retmax,
        "sort": "pub date",
    }
    if email:
        params["email"] = email
    if api_key:
        params["api_key"] = api_key
    return json.loads(request_text(eutils_url("esearch.fcgi", params), delay=delay))


def text_for(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return clean_text("".join(element.itertext()))


def fetch_articles(
    pmids: list[str],
    *,
    email: str = "",
    api_key: str = "",
    delay: float = 0.34,
) -> list[dict[str, str]]:
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
    root = ET.fromstring(request_text(eutils_url("efetch.fcgi", params), delay=delay))
    articles = []
    for article in root.findall(".//PubmedArticle"):
        pmid = text_for(article.find(".//PMID"))
        title = text_for(article.find(".//ArticleTitle"))
        journal = text_for(article.find(".//Journal/Title"))
        year = text_for(article.find(".//PubDate/Year"))
        abstract_parts = []
        for item in article.findall(".//Abstract/AbstractText"):
            label = clean_text(item.attrib.get("Label") or "")
            text = text_for(item)
            if not text:
                continue
            abstract_parts.append(f"{label}: {text}" if label else text)
        abstract = clean_text(" ".join(abstract_parts))
        if pmid and title and abstract:
            articles.append(
                {
                    "pmid": pmid,
                    "title": title,
                    "journal": journal,
                    "year": year,
                    "abstract": abstract,
                }
            )
    return articles


def excerpt_from_abstract(abstract: str, *, max_chars: int) -> str:
    abstract = clean_text(abstract)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", abstract)
    excerpt = ""
    for sentence in sentences:
        sentence = clean_text(sentence)
        if not sentence:
            continue
        candidate = f"{excerpt} {sentence}".strip() if excerpt else sentence
        if len(candidate) > max_chars:
            break
        excerpt = candidate
        if len(excerpt) >= max_chars * 0.55:
            break
    if excerpt:
        return excerpt
    return abstract[:max_chars].rsplit(" ", 1)[0].strip()


def build_passage(article: dict[str, str], *, max_chars: int) -> str:
    prefix = f"PubMed PMID {article['pmid']}. {article['title']}"
    remaining = max(120, max_chars - len(prefix) - 1)
    excerpt = excerpt_from_abstract(article.get("abstract") or "", max_chars=remaining)
    return ascii_safe(clean_text(f"{prefix} {excerpt}"))


def collect_random_pmids(
    *,
    term: str,
    count: int,
    seed: int,
    email: str,
    api_key: str,
    delay: float,
) -> list[str]:
    rng = random.Random(seed)
    payload = pubmed_search(
        term,
        retmax=max(count * 8, 200),
        email=email,
        api_key=api_key,
        delay=delay,
    )
    pmids = [
        str(pmid)
        for pmid in payload.get("esearchresult", {}).get("idlist", [])
        if str(pmid)
    ]
    rng.shuffle(pmids)
    return pmids[: count * 4]


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["id", "query", "pmid", "title", "journal", "year", "source_url"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def update_paragraph_pool(path: Path, rows: list[dict[str, str]]) -> int:
    current = []
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(current, list):
        raise ValueError(f"{path} must contain a JSON list")
    base = [
        str(item).strip()
        for item in current
        if str(item).strip() and not str(item).strip().startswith("PubMed PMID ")
    ]
    seen = set(base)
    for row in rows:
        query = str(row.get("query") or "").strip()
        if query and query not in seen:
            seen.add(query)
            base.append(query)
    path.write_text(json.dumps(base, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(base)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch short random PubMed excerpts into the search-quality UI sample pool."
    )
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260609)
    parser.add_argument("--term", default=DEFAULT_TERM)
    parser.add_argument("--max-chars", type=int, default=760)
    parser.add_argument("--email", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--delay", type=float, default=0.34)
    parser.add_argument("--output", type=Path, default=ROOT / "config" / "pubmed_ui_sample_queries.tsv")
    parser.add_argument("--paragraphs", type=Path, default=ROOT / "docs" / "search_quality" / "paragraphs.json")
    parser.add_argument("--no-update-paragraphs", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pmids = collect_random_pmids(
        term=args.term,
        count=args.count,
        seed=args.seed,
        email=args.email,
        api_key=args.api_key,
        delay=args.delay,
    )
    articles = fetch_articles(pmids, email=args.email, api_key=args.api_key, delay=args.delay)
    rows = []
    for article in articles:
        query = build_passage(article, max_chars=args.max_chars)
        if not query:
            continue
        rows.append(
            {
                "id": f"pubmed_ui_{article['pmid']}",
                "query": query,
                "pmid": article["pmid"],
                "title": ascii_safe(article.get("title") or ""),
                "journal": ascii_safe(article.get("journal") or ""),
                "year": article.get("year") or "",
                "source_url": f"https://pubmed.ncbi.nlm.nih.gov/{article['pmid']}/",
            }
        )
        if len(rows) >= args.count:
            break
    write_rows(args.output, rows)
    total = None
    if not args.no_update_paragraphs:
        total = update_paragraph_pool(args.paragraphs, rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "output": str(args.output),
                "paragraphs": str(args.paragraphs) if not args.no_update_paragraphs else "",
                "paragraph_pool_count": total,
                "seed": args.seed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
