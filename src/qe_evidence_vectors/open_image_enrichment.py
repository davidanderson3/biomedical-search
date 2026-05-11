from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import quote, urlencode, unquote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .schema import ConceptDocument, iter_jsonl
from .text import normalized_key


OPEN_IMAGE_VIEW = "open_image"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
COMMONS_API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_SOURCE = "wikimedia_commons"
DEFAULT_USER_AGENT = "query-expansion-open-image-enrichment/0.1"

OPEN_LICENSE_MARKERS = (
    "cc0",
    "cc by",
    "cc-by",
    "cc by-sa",
    "cc-by-sa",
    "public domain",
    "pd-",
    "gfdl",
    "free art license",
)
BLOCKED_LICENSE_MARKERS = (
    "fair use",
    "non-commercial",
    "noncommercial",
    "no derivatives",
    "no-derivatives",
    "all rights reserved",
)


@dataclass(frozen=True)
class ConceptImageTarget:
    cui: str
    labels: tuple[str, ...]
    evidence_count: int = 0


def load_image_targets(path: str | Path) -> list[ConceptImageTarget]:
    targets: list[ConceptImageTarget] = []
    seen: set[str] = set()
    for raw_line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        cui = parts[0].strip().upper()
        if not cui or cui in seen:
            continue
        labels = tuple(
            item.strip()
            for item in re.split(r"\s*[|,]\s*", parts[1] if len(parts) > 1 else "")
            if item.strip()
        )
        if not labels:
            labels = (cui,)
        targets.append(ConceptImageTarget(cui=cui, labels=labels))
        seen.add(cui)
    return targets


def image_targets_from_documents(
    doc_paths: Iterable[str | Path],
    *,
    limit: int = 0,
    offset: int = 0,
) -> list[ConceptImageTarget]:
    by_cui: dict[str, dict[str, Any]] = {}
    for doc_path in doc_paths:
        path = Path(doc_path).expanduser()
        if not path.exists():
            continue
        for payload in iter_jsonl(path):
            cui = str(payload.get("cui") or "").strip().upper()
            if not cui:
                continue
            labels = string_list(payload.get("labels"))
            evidence_count = int(payload.get("evidence_count") or 0)
            current = by_cui.setdefault(cui, {"labels": [], "evidence_count": 0})
            current["evidence_count"] = max(int(current["evidence_count"]), evidence_count)
            for label in labels:
                add_unique_label(current["labels"], label)
    targets = [
        ConceptImageTarget(
            cui=cui,
            labels=tuple(payload["labels"] or [cui]),
            evidence_count=int(payload["evidence_count"]),
        )
        for cui, payload in by_cui.items()
    ]
    targets.sort(
        key=lambda item: (
            -item.evidence_count,
            normalized_key(item.labels[0] if item.labels else item.cui),
            item.cui,
        )
    )
    if offset:
        targets = targets[offset:]
    if limit:
        targets = targets[:limit]
    return targets


def build_open_image_documents(
    targets: Iterable[ConceptImageTarget],
    *,
    images_by_cui: dict[str, list[dict[str, Any]]],
    max_images_per_cui: int = 3,
) -> list[ConceptDocument]:
    documents = []
    for target in targets:
        images = list(images_by_cui.get(target.cui, []))[:max_images_per_cui]
        if not images:
            continue
        documents.append(open_image_document(target, images))
    return documents


def open_image_document(target: ConceptImageTarget, images: list[dict[str, Any]]) -> ConceptDocument:
    labels = list(target.labels)
    lines = [
        f"CUI: {target.cui}",
        f"Evidence view: {OPEN_IMAGE_VIEW}",
        "Open-license images:",
    ]
    for image in images:
        title = str(image.get("title") or image.get("page_title") or "image")
        license_text = str(image.get("license") or "open license")
        source_url = str(image.get("source_url") or image.get("file_page_url") or "")
        lines.append(f"- {title}: {source_url} ({license_text})")
    lines.append("UMLS labels:")
    lines.extend(f"- {label}" for label in labels)
    lines.append("Real-world evidence:")
    for image in images:
        title = str(image.get("title") or image.get("page_title") or "image")
        license_text = str(image.get("license") or "open license")
        lines.append(
            f"- Open-license image from Wikimedia Commons: {title} ({license_text}) (weight 1)"
        )
    return ConceptDocument(
        doc_id=f"{target.cui}:{OPEN_IMAGE_VIEW}",
        cui=target.cui,
        view=OPEN_IMAGE_VIEW,
        text="\n".join(lines),
        evidence_count=len(images),
        sources=[WIKIMEDIA_SOURCE],
        labels=labels,
        metadata={
            "document_builder": "open_image_enrichment",
            "source": WIKIMEDIA_SOURCE,
            "image_count": len(images),
            "images": images,
        },
    )


def fetch_wikidata_image_bindings(
    cuis: Iterable[str],
    *,
    endpoint: str = WIKIDATA_SPARQL_ENDPOINT,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 30,
    fetch_json: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    cui_values = [cui.strip().upper() for cui in cuis if cui.strip()]
    if not cui_values:
        return {}
    values = " ".join(json.dumps(cui) for cui in cui_values)
    query = f"""
SELECT ?cui ?item ?itemLabel ?image WHERE {{
  VALUES ?cui {{ {values} }}
  ?item wdt:P2892 ?cui .
  OPTIONAL {{ ?item wdt:P18 ?image . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""
    payload = (fetch_json or fetch_url_json)(
        endpoint,
        params={"query": query, "format": "json"},
        user_agent=user_agent,
        timeout=timeout,
    )
    by_cui: dict[str, list[dict[str, Any]]] = {}
    for binding in payload.get("results", {}).get("bindings", []):
        cui = binding_value(binding, "cui").strip().upper()
        image_url = binding_value(binding, "image").strip()
        if not cui or not image_url:
            continue
        by_cui.setdefault(cui, []).append(
            {
                "wikidata_item": binding_value(binding, "item"),
                "wikidata_label": binding_value(binding, "itemLabel"),
                "image_url": image_url,
                "title": commons_title_from_special_file_path(image_url),
                "source_kind": "wikidata_p18",
            }
        )
    return by_cui


def fetch_commons_image_metadata(
    titles: Iterable[str],
    *,
    endpoint: str = COMMONS_API_ENDPOINT,
    thumb_width: int = 512,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 30,
    fetch_json: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    normalized_titles = []
    seen: set[str] = set()
    for title in titles:
        page_title = normalize_commons_file_title(title)
        key = page_title.lower()
        if not page_title or key in seen:
            continue
        seen.add(key)
        normalized_titles.append(page_title)
    if not normalized_titles:
        return {}
    payload = (fetch_json or fetch_url_json)(
        endpoint,
        params={
            "action": "query",
            "titles": "|".join(normalized_titles),
            "prop": "imageinfo|info",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": str(thumb_width),
            "inprop": "url",
            "format": "json",
            "formatversion": "2",
        },
        user_agent=user_agent,
        timeout=timeout,
    )
    metadata_by_title = {}
    for page in payload.get("query", {}).get("pages", []):
        title = normalize_commons_file_title(str(page.get("title") or ""))
        imageinfo = (page.get("imageinfo") or [{}])[0]
        ext = imageinfo.get("extmetadata") or {}
        image = {
            "source": WIKIMEDIA_SOURCE,
            "title": title,
            "source_url": str(page.get("fullurl") or commons_file_page_url(title)),
            "file_page_url": str(page.get("fullurl") or commons_file_page_url(title)),
            "image_url": str(imageinfo.get("url") or ""),
            "thumbnail_url": str(imageinfo.get("thumburl") or imageinfo.get("url") or ""),
            "mime": str(imageinfo.get("mime") or ""),
            "width": int(imageinfo.get("width") or 0),
            "height": int(imageinfo.get("height") or 0),
            "license": ext_value(ext, "LicenseShortName") or ext_value(ext, "UsageTerms"),
            "license_url": ext_value(ext, "LicenseUrl"),
            "attribution": clean_html_text(ext_value(ext, "Attribution") or ext_value(ext, "Artist")),
            "artist": clean_html_text(ext_value(ext, "Artist")),
            "credit": clean_html_text(ext_value(ext, "Credit")),
            "description": clean_html_text(
                ext_value(ext, "ImageDescription") or ext_value(ext, "ObjectName")
            ),
        }
        if image["image_url"] and is_open_license(image):
            metadata_by_title[title] = image
    return metadata_by_title


def search_commons_images(
    label: str,
    *,
    endpoint: str = COMMONS_API_ENDPOINT,
    limit: int = 5,
    thumb_width: int = 512,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 30,
    fetch_json: Callable[..., dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    query = re.sub(r"\s+", " ", label or "").strip()
    if not query:
        return []
    payload = (fetch_json or fetch_url_json)(
        endpoint,
        params={
            "action": "query",
            "generator": "search",
            "gsrnamespace": "6",
            "gsrsearch": query,
            "gsrlimit": str(limit),
            "prop": "imageinfo|info",
            "iiprop": "url|mime|size|extmetadata",
            "iiurlwidth": str(thumb_width),
            "inprop": "url",
            "format": "json",
            "formatversion": "2",
        },
        user_agent=user_agent,
        timeout=timeout,
    )
    images = []
    for page in payload.get("query", {}).get("pages", []):
        title = normalize_commons_file_title(str(page.get("title") or ""))
        imageinfo = (page.get("imageinfo") or [{}])[0]
        ext = imageinfo.get("extmetadata") or {}
        image = {
            "source": WIKIMEDIA_SOURCE,
            "title": title,
            "source_url": str(page.get("fullurl") or commons_file_page_url(title)),
            "file_page_url": str(page.get("fullurl") or commons_file_page_url(title)),
            "image_url": str(imageinfo.get("url") or ""),
            "thumbnail_url": str(imageinfo.get("thumburl") or imageinfo.get("url") or ""),
            "mime": str(imageinfo.get("mime") or ""),
            "width": int(imageinfo.get("width") or 0),
            "height": int(imageinfo.get("height") or 0),
            "license": ext_value(ext, "LicenseShortName") or ext_value(ext, "UsageTerms"),
            "license_url": ext_value(ext, "LicenseUrl"),
            "attribution": clean_html_text(ext_value(ext, "Attribution") or ext_value(ext, "Artist")),
            "artist": clean_html_text(ext_value(ext, "Artist")),
            "credit": clean_html_text(ext_value(ext, "Credit")),
            "description": clean_html_text(
                ext_value(ext, "ImageDescription") or ext_value(ext, "ObjectName")
            ),
            "source_kind": "commons_search",
        }
        if image["image_url"] and is_open_license(image):
            images.append(image)
    return images


def resolve_open_images_for_targets(
    targets: Iterable[ConceptImageTarget],
    *,
    batch_size: int = 80,
    max_images_per_cui: int = 3,
    min_score: float = 0.78,
    commons_search_fallback: bool = True,
    sleep_seconds: float = 0.1,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, list[dict[str, Any]]]:
    target_list = list(targets)
    by_cui: dict[str, list[dict[str, Any]]] = {target.cui: [] for target in target_list}
    target_by_cui = {target.cui: target for target in target_list}
    for batch_start in range(0, len(target_list), batch_size):
        batch = target_list[batch_start : batch_start + batch_size]
        try:
            bindings = fetch_wikidata_image_bindings(
                [target.cui for target in batch],
                user_agent=user_agent,
            )
        except (HTTPError, URLError, TimeoutError, OSError):
            bindings = {}
        title_rows = []
        for rows in bindings.values():
            for row in rows:
                if row.get("title"):
                    title_rows.append(str(row["title"]))
        try:
            metadata_by_title = fetch_commons_image_metadata(
                title_rows,
                user_agent=user_agent,
            )
        except (HTTPError, URLError, TimeoutError, OSError):
            metadata_by_title = {}
        for cui, rows in bindings.items():
            target = target_by_cui.get(cui)
            if not target:
                continue
            for row in rows:
                metadata = metadata_by_title.get(normalize_commons_file_title(str(row.get("title") or "")))
                if not metadata:
                    continue
                image = dict(metadata)
                image.update(
                    {
                        "source_kind": "wikidata_p18",
                        "wikidata_item": row.get("wikidata_item") or "",
                        "wikidata_label": row.get("wikidata_label") or "",
                    }
                )
                image["match_score"] = 1.0
                image["matched_label"] = target.labels[0] if target.labels else target.cui
                add_image(by_cui[cui], image, max_images=max_images_per_cui)
        if commons_search_fallback:
            for target in batch:
                if len(by_cui[target.cui]) >= max_images_per_cui:
                    continue
                for label in target.labels[:3]:
                    try:
                        candidates = search_commons_images(label, user_agent=user_agent)
                    except (HTTPError, URLError, TimeoutError, OSError):
                        candidates = []
                    scored = []
                    for candidate in candidates:
                        score = image_match_score(target.labels, candidate)
                        if score < min_score:
                            continue
                        item = dict(candidate)
                        item["match_score"] = score
                        item["matched_label"] = label
                        scored.append(item)
                    scored.sort(key=lambda item: (-float(item.get("match_score") or 0), item["title"]))
                    for item in scored:
                        add_image(by_cui[target.cui], item, max_images=max_images_per_cui)
                    if len(by_cui[target.cui]) >= max_images_per_cui:
                        break
                    if sleep_seconds:
                        time.sleep(sleep_seconds)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return {cui: images for cui, images in by_cui.items() if images}


def add_image(images: list[dict[str, Any]], image: dict[str, Any], *, max_images: int) -> None:
    key = str(image.get("image_url") or image.get("source_url") or image.get("title") or "").strip()
    if not key or any(key == str(existing.get("image_url") or existing.get("source_url") or existing.get("title") or "") for existing in images):
        return
    if len(images) >= max_images:
        return
    images.append(image)


def image_match_score(labels: Iterable[str], image: dict[str, Any]) -> float:
    labels = [label for label in labels if label]
    title = normalized_image_title(str(image.get("title") or ""))
    description = normalized_key(str(image.get("description") or ""))
    searchable = " ".join(part for part in (title, description) if part)
    best = 0.0
    for label in labels:
        label_key = normalized_key(label)
        if not label_key:
            continue
        label_tokens = [token for token in label_key.split() if len(token) > 2]
        if not label_tokens:
            continue
        if label_key and label_key in title:
            best = max(best, 0.98)
        elif all(token in title.split() for token in label_tokens):
            best = max(best, 0.9)
        elif all(token in searchable.split() for token in label_tokens):
            best = max(best, 0.82)
        else:
            overlap = sum(1 for token in label_tokens if token in searchable.split())
            best = max(best, overlap / max(len(label_tokens), 1) * 0.75)
    return round(best, 3)


def is_open_license(image: dict[str, Any]) -> bool:
    text = " ".join(
        str(image.get(field) or "").lower()
        for field in ("license", "license_url", "usage_terms")
    )
    if any(marker in text for marker in BLOCKED_LICENSE_MARKERS):
        return False
    return any(marker in text for marker in OPEN_LICENSE_MARKERS)


def fetch_url_json(
    url: str,
    *,
    params: dict[str, str],
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: int = 30,
) -> dict[str, Any]:
    separator = "&" if "?" in url else "?"
    request_url = f"{url}{separator}{urlencode(params)}"
    request = Request(request_url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def binding_value(binding: dict[str, Any], key: str) -> str:
    value = binding.get(key) or {}
    return str(value.get("value") or "")


def ext_value(extmetadata: dict[str, Any], key: str) -> str:
    value = extmetadata.get(key) or {}
    return str(value.get("value") or "")


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def commons_title_from_special_file_path(url: str) -> str:
    parsed = urlparse(url)
    marker = "/wiki/Special:FilePath/"
    path = parsed.path
    if marker not in path:
        return ""
    filename = unquote(path.split(marker, 1)[1])
    return normalize_commons_file_title(filename)


def normalize_commons_file_title(title: str) -> str:
    value = unquote(str(title or "")).strip().replace(" ", "_")
    if not value:
        return ""
    if not value.lower().startswith("file:"):
        value = f"File:{value}"
    return value


def normalized_image_title(title: str) -> str:
    value = normalize_commons_file_title(title)
    value = re.sub(r"^File:", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", value)
    return normalized_key(value.replace("_", " "))


def commons_file_page_url(title: str) -> str:
    page_title = normalize_commons_file_title(title)
    return f"https://commons.wikimedia.org/wiki/{quote(page_title.replace(' ', '_'), safe=':/')}"


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    labels = []
    for item in value:
        add_unique_label(labels, str(item or ""))
    return labels


def add_unique_label(labels: list[str], value: str) -> None:
    text = re.sub(r"\s+", " ", value or "").strip()
    key = normalized_key(text)
    if not text or not key:
        return
    if key in {normalized_key(existing) for existing in labels}:
        return
    labels.append(text)
