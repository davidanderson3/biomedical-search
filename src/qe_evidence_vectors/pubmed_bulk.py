from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from .schema import CorpusDocument, write_jsonl
from .text import clean_text


PUBMED_BASELINE_URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline"
PUBMED_UPDATEFILES_URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/updatefiles"
DEFAULT_PUBMED_BULK_YEAR = 2026
DEFAULT_PUBMED_BULK_LATEST_BASELINE = 1334


@dataclass(frozen=True)
class PubMedBulkFile:
    year: int
    number: int
    name: str
    url: str
    md5_url: str
    local_path: str
    md5_path: str


def baseline_file_name(year: int, number: int) -> str:
    return f"pubmed{year % 100:02d}n{number:04d}.xml.gz"


def recent_baseline_files(
    *,
    year: int = DEFAULT_PUBMED_BULK_YEAR,
    latest_number: int = DEFAULT_PUBMED_BULK_LATEST_BASELINE,
    count: int = 1,
    out_dir: str | Path = "data/pubmed/baseline",
) -> list[PubMedBulkFile]:
    if count <= 0:
        raise ValueError("count must be positive")
    if latest_number <= 0:
        raise ValueError("latest_number must be positive")
    out_dir = Path(out_dir).expanduser()
    files = []
    for number in range(latest_number, max(0, latest_number - count), -1):
        name = baseline_file_name(year, number)
        url = f"{PUBMED_BASELINE_URL}/{name}"
        local_path = out_dir / name
        files.append(
            PubMedBulkFile(
                year=year,
                number=number,
                name=name,
                url=url,
                md5_url=f"{url}.md5",
                local_path=str(local_path),
                md5_path=str(local_path.with_suffix(local_path.suffix + ".md5")),
            )
        )
    return files


def _read_url_to_path(url: str, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0
    with urllib.request.urlopen(url) as response, path.open("wb") as handle:
        for chunk in iter(lambda: response.read(1024 * 1024), b""):
            handle.write(chunk)
            bytes_written += len(chunk)
    return bytes_written


def parse_md5_payload(payload: str) -> str:
    match = re.search(r"\b([a-fA-F0-9]{32})\b", payload)
    if not match:
        raise ValueError("MD5 payload does not contain a checksum")
    return match.group(1).lower()


def file_md5(path: str | Path) -> str:
    digest = hashlib.md5()
    with Path(path).expanduser().open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_pubmed_bulk_files(
    files: list[PubMedBulkFile],
    *,
    skip_existing: bool = True,
    verify_md5: bool = True,
) -> list[dict]:
    results = []
    for file in files:
        started = time.time()
        local_path = Path(file.local_path).expanduser()
        md5_path = Path(file.md5_path).expanduser()
        downloaded = False
        if not skip_existing or not local_path.exists():
            _read_url_to_path(file.url, local_path)
            downloaded = True
        if not skip_existing or not md5_path.exists():
            _read_url_to_path(file.md5_url, md5_path)

        expected_md5 = parse_md5_payload(md5_path.read_text(encoding="utf-8"))
        actual_md5 = file_md5(local_path) if verify_md5 else ""
        if verify_md5 and actual_md5 != expected_md5:
            raise ValueError(
                f"MD5 mismatch for {local_path}: expected {expected_md5}, got {actual_md5}"
            )
        stat = local_path.stat()
        results.append(
            {
                **asdict(file),
                "downloaded": downloaded,
                "bytes": stat.st_size,
                "expected_md5": expected_md5,
                "actual_md5": actual_md5,
                "verified": bool(verify_md5),
                "seconds": round(time.time() - started, 3),
            }
        )
    return results


def write_bulk_manifest(path: str | Path, records: list[dict]) -> None:
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file_count": len(records),
        "total_bytes": sum(int(record.get("bytes", 0)) for record in records),
        "files": records,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return clean_text(" ".join("".join(node.itertext()).split()))


def _article_year(article: ET.Element) -> str:
    for path in [
        ".//Article/Journal/JournalIssue/PubDate/Year",
        ".//Article/ArticleDate/Year",
        ".//DateCompleted/Year",
        ".//DateRevised/Year",
    ]:
        value = (article.findtext(path) or "").strip()
        if value:
            return value
    medline_date = (article.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or "").strip()
    match = re.search(r"\b(18|19|20|21)\d{2}\b", medline_date)
    return match.group(0) if match else ""


def _publication_types(article: ET.Element) -> list[str]:
    return [
        clean_text("".join(node.itertext()))
        for node in article.findall(".//PublicationTypeList/PublicationType")
        if clean_text("".join(node.itertext()))
    ]


def pubmed_article_to_document(article: ET.Element, *, source_file: str = "") -> CorpusDocument | None:
    pmid = clean_text(article.findtext(".//PMID") or "")
    if not pmid:
        return None
    title = _node_text(article.find(".//ArticleTitle"))
    abstract_parts = [_node_text(node) for node in article.findall(".//Abstract/AbstractText")]
    abstract = clean_text(" ".join(part for part in abstract_parts if part))
    text = clean_text(" ".join(part for part in [title, abstract] if part))
    if not text:
        return None
    journal = _node_text(article.find(".//Article/Journal/Title"))
    doi = ""
    for article_id in article.findall(".//ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType") == "doi":
            doi = clean_text("".join(article_id.itertext()))
            break
    return CorpusDocument(
        doc_id=f"PMID:{pmid}",
        source="pubmed_bulk",
        title=title,
        text=text,
        metadata={
            "pmid": pmid,
            "doi": doi,
            "journal": journal,
            "publication_year": _article_year(article),
            "publication_types": _publication_types(article),
            "source_file": source_file,
            "bulk_source": "pubmed_baseline",
        },
    )


def iter_pubmed_bulk_documents(
    paths: list[str | Path],
    *,
    max_docs: int | None = None,
) -> Iterator[CorpusDocument]:
    emitted = 0
    for path in paths:
        path = Path(path).expanduser()
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as handle:
            context = ET.iterparse(handle, events=("end",))
            for _event, element in context:
                if element.tag != "PubmedArticle":
                    continue
                document = pubmed_article_to_document(element, source_file=path.name)
                element.clear()
                if document is None:
                    continue
                yield document
                emitted += 1
                if max_docs is not None and emitted >= max_docs:
                    return


def write_pubmed_bulk_corpus(
    paths: list[str | Path],
    out_path: str | Path,
    *,
    max_docs: int | None = None,
) -> int:
    return write_jsonl(out_path, iter_pubmed_bulk_documents(paths, max_docs=max_docs))
