from __future__ import annotations

import csv
import json
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from qe_evidence_vectors.code_index import is_cui
from qe_evidence_vectors.search_service import SearchIndex


JUDGMENT_FIELDS = ["query", "doc_id", "cui", "view", "score", "grade", "labels"]
VALID_JUDGMENT_GRADES = {"relevant", "partial", "wrong"}

__all__ = [
    "parse_multi_param",
    "parse_bool_param",
    "parse_bounded_int_param",
    "read_judgments",
    "write_judgments",
    "make_handler",
]


def parse_multi_param(params: dict, *names: str) -> list[str]:
    values = []
    for name in names:
        for raw_value in params.get(name, []):
            values.extend(part.strip() for part in raw_value.split(",") if part.strip())
    return values


def parse_bool_param(params: dict, *names: str, default: bool = True) -> bool:
    for name in names:
        raw_values = params.get(name)
        if not raw_values:
            continue
        raw_value = str(raw_values[0]).strip().lower()
        if raw_value in {"0", "false", "no", "off"}:
            return False
        if raw_value in {"1", "true", "yes", "on"}:
            return True
    return default


def parse_bounded_int_param(
    params: dict,
    *names: str,
    default: int,
    minimum: int = 1,
    maximum: int = 100,
) -> tuple[int | None, str | None]:
    for name in names:
        raw_values = params.get(name)
        if not raw_values:
            continue
        raw_value = str(raw_values[0]).strip()
        try:
            value = int(raw_value)
        except ValueError:
            return None, f"{name} must be an integer"
        return max(minimum, min(value, maximum)), None
    return max(minimum, min(default, maximum)), None


def judgment_key(row: dict) -> str:
    return f"{row.get('query', '')}\t{row.get('doc_id', '')}"


def normalize_judgment(row: dict) -> dict:
    labels = row.get("labels") or []
    if isinstance(labels, str):
        labels = [label.strip() for label in labels.split(";") if label.strip()]
    grade = str(row.get("grade") or "").strip().lower()
    return {
        "query": str(row.get("query") or "").strip(),
        "doc_id": str(row.get("doc_id") or "").strip(),
        "cui": str(row.get("cui") or "").strip(),
        "view": str(row.get("view") or "").strip(),
        "score": row.get("score", ""),
        "grade": grade,
        "labels": labels,
    }


def read_judgments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = normalize_judgment(row)
            if not normalized["query"] or not normalized["doc_id"]:
                continue
            if normalized["grade"] not in VALID_JUDGMENT_GRADES:
                continue
            rows.append(normalized)
    return rows


def write_judgments(path: Path, judgments: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalize_judgment(row) for row in judgments]
    normalized = [
        row
        for row in normalized
        if row["query"] and row["doc_id"] and row["grade"] in VALID_JUDGMENT_GRADES
    ]
    normalized.sort(key=lambda row: (row["query"], row["doc_id"]))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=JUDGMENT_FIELDS)
        writer.writeheader()
        for row in normalized:
            output = dict(row)
            output["labels"] = "; ".join(row.get("labels") or [])
            writer.writerow(output)
    return len(normalized)


def make_handler(
    index: SearchIndex,
    html_path: Path,
    progress_html_path: Path,
    progress_plan_path: Path,
    full_progress_plan_path: Path,
    judgments_path: Path,
    *,
    plan_status_func: Callable[[dict], dict],
    resolve_path_func: Callable[[str], Path],
):
    search_quality_dir = html_path.parent / "search_quality"
    static_assets = {
        "/search_quality_server.css": (search_quality_dir / "server.css", "text/css; charset=utf-8"),
        "/search_quality_app.js": (search_quality_dir / "app.js", "application/javascript; charset=utf-8"),
        "/search_quality_suggestions.json": (
            search_quality_dir / "suggestions.json",
            "application/json; charset=utf-8",
        ),
        "/search_quality_paragraphs.json": (
            search_quality_dir / "paragraphs.json",
            "application/json; charset=utf-8",
        ),
        "/search_quality_expansion_profiles.json": (
            search_quality_dir / "expansion_profiles.json",
            "application/json; charset=utf-8",
        ),
        "/search_quality_semantic_buckets.json": (
            resolve_path_func("config/search_quality_semantic_buckets.json"),
            "application/json; charset=utf-8",
        ),
    }

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_common_headers()
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self.send_html(html_path.read_text(encoding="utf-8"))
                return
            if parsed.path == "/progress":
                self.send_html(progress_html_path.read_text(encoding="utf-8"))
                return
            if parsed.path in static_assets:
                asset_path, content_type = static_assets[parsed.path]
                if not asset_path.exists():
                    self.send_json({"error": "not found"}, status=404)
                    return
                self.send_text(asset_path.read_text(encoding="utf-8"), content_type=content_type)
                return
            if parsed.path == "/api/status":
                status = index.status()
                status["judgments_path"] = str(judgments_path)
                status["judgments_count"] = len(read_judgments(judgments_path))
                self.send_json(status)
                return
            if parsed.path == "/api/judgments":
                rows = read_judgments(judgments_path)
                self.send_json(
                    {
                        "path": str(judgments_path),
                        "count": len(rows),
                        "judgments": rows,
                    }
                )
                return
            if parsed.path == "/api/progress":
                plan = json.loads(resolve_path_func(str(progress_plan_path)).read_text(encoding="utf-8"))
                self.send_json(plan_status_func(plan))
                return
            if parsed.path == "/api/full-progress":
                plan = json.loads(resolve_path_func(str(full_progress_plan_path)).read_text(encoding="utf-8"))
                self.send_json(plan_status_func(plan))
                return
            if parsed.path == "/api/resolve":
                params = parse_qs(parsed.query)
                query = (params.get("q") or [""])[0].strip()
                limit, error = parse_bounded_int_param(
                    params,
                    "limit",
                    "k",
                    "top_k",
                    default=10,
                    minimum=1,
                    maximum=100,
                )
                if error:
                    self.send_json({"error": error}, status=400)
                    return
                if not query:
                    self.send_json({"error": "missing q"}, status=400)
                    return
                self.send_json(index.resolve(query, limit=limit or 10))
                return
            if parsed.path == "/api/related":
                params = parse_qs(parsed.query)
                cui = (params.get("cui") or [""])[0].strip()
                top_k, error = parse_bounded_int_param(
                    params,
                    "k",
                    "top_k",
                    "limit",
                    default=10,
                    minimum=1,
                    maximum=100,
                )
                if error:
                    self.send_json({"error": error}, status=400)
                    return
                if not cui:
                    self.send_json({"error": "missing cui"}, status=400)
                    return
                if not is_cui(cui):
                    self.send_json({"error": "cui must look like C0000000"}, status=400)
                    return
                self.send_json(
                    index.related_bundle(
                        cui,
                        top_k=top_k or 10,
                        mapping_sabs=parse_multi_param(params, "sab", "vocab", "system"),
                    )
                )
                return
            if parsed.path == "/api/detail":
                params = parse_qs(parsed.query)
                doc_id = (params.get("doc_id") or [""])[0].strip()
                cui = (params.get("cui") or [""])[0].strip()
                include_related = parse_bool_param(
                    params,
                    "related",
                    "include_related",
                    default=True,
                )
                if not doc_id and not cui:
                    self.send_json({"error": "missing doc_id or cui"}, status=400)
                    return
                if cui and not is_cui(cui):
                    self.send_json({"error": "cui must look like C0000000"}, status=400)
                    return
                bundle = index.detail_bundle(
                    doc_id=doc_id,
                    cui=cui,
                    include_related=include_related,
                )
                if bundle.get("error"):
                    self.send_json(bundle, status=404 if bundle["error"] != "missing doc_id or cui" else 400)
                    return
                self.send_json(bundle)
                return
            if parsed.path == "/api/search":
                params = parse_qs(parsed.query)
                query = (params.get("q") or [""])[0].strip()
                top_k, error = parse_bounded_int_param(
                    params,
                    "k",
                    "top_k",
                    "limit",
                    default=10,
                    minimum=1,
                    maximum=100,
                )
                if error:
                    self.send_json({"error": error}, status=400)
                    return
                if not query:
                    self.send_json({"error": "missing q"}, status=400)
                    return
                include_related = parse_bool_param(
                    params,
                    "related",
                    "include_related",
                    default=True,
                )
                semantic_bucket_keys = parse_multi_param(
                    params,
                    "semantic_bucket",
                    "semantic_buckets",
                    "bucket",
                    "buckets",
                    "semantic_group",
                    "semantic_groups",
                )
                try:
                    self.send_json(
                        index.search(
                            query,
                            top_k=top_k or 10,
                            include_related=include_related,
                            semantic_bucket_keys=semantic_bucket_keys,
                        )
                    )
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=400)
                return
            self.send_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/judgments":
                self.send_json({"error": "not found"}, status=404)
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body or "{}")
                rows = payload.get("judgments")
                if not isinstance(rows, list):
                    self.send_json({"error": "expected judgments array"}, status=400)
                    return
                count = write_judgments(judgments_path, rows)
                self.send_json({"path": str(judgments_path), "count": count})
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=400)

        def log_message(self, format: str, *args) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

        def send_html(self, body: str, *, status: int = 200) -> None:
            self.send_text(body, status=status, content_type="text/html; charset=utf-8")

        def send_text(self, body: str, *, status: int = 200, content_type: str = "text/plain; charset=utf-8") -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_common_headers()
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def send_json(self, body: dict, *, status: int = 200) -> None:
            payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_common_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")

    return Handler
