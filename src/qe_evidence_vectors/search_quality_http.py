from __future__ import annotations

import csv
import json
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from qe_evidence_vectors.code_index import is_cui
from qe_evidence_vectors.search_execution import SearchBackendUnavailable, normalize_search_scope
from qe_evidence_vectors.search_service import SearchIndex


JUDGMENT_FIELDS = ["query", "doc_id", "cui", "view", "score", "grade", "labels"]
VALID_JUDGMENT_GRADES = {"relevant", "partial", "wrong"}

__all__ = [
    "API_VERSION",
    "OPENAPI_SPEC",
    "parse_multi_param",
    "parse_bool_param",
    "parse_bounded_int_param",
    "api_error",
    "read_judgments",
    "delete_judgment",
    "upsert_judgment",
    "write_judgments",
    "make_handler",
]

API_VERSION = "2026-06-09"


def api_error(code: str, message: str, *, status: int = 400) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "status": int(status),
        }
    }


OPENAPI_SPEC = {
    "openapi": "3.1.0",
    "info": {
        "title": "Biomedical Concept Search API",
        "version": API_VERSION,
        "description": (
            "Local biomedical concept search and linking API. The contract is stable for "
            "the documented fields; extra fields may be added over time."
        ),
    },
    "servers": [{"url": "/"}],
    "paths": {
        "/api/health": {
            "get": {
                "summary": "Cheap liveness/readiness check",
                "responses": {
                    "200": {
                        "description": "Server is ready to answer API requests.",
                    }
                },
            }
        },
        "/api/status": {
            "get": {
                "summary": "Loaded index and server status",
                "responses": {"200": {"description": "Search index status and artifact counts."}},
            }
        },
        "/api/search": {
            "get": {
                "summary": "Search free text for biomedical concepts",
                "parameters": [
                    {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                    {
                        "name": "profile",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["product", "review", "benchmark", "umls_only"],
                        },
                        "description": (
                            "Preset API defaults for UI surfaces and benchmarks. Explicit legacy "
                            "query parameters still override the preset."
                        ),
                    },
                    {"name": "k", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
                    {
                        "name": "mode",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["balanced", "exact", "comprehensive"]},
                    },
                    {
                        "name": "scope",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["umls", "umls_evidence"]},
                        "description": "Use UMLS-only label/code lookup or UMLS plus evidence-backed retrieval.",
                    },
                    {"name": "include_related", "in": "query", "schema": {"type": "boolean"}},
                    {
                        "name": "molecular_associations",
                        "in": "query",
                        "schema": {"type": "boolean"},
                        "description": (
                            "Opt in to relation-derived gene/protein association candidates "
                            "in the main ranked results. Directly matched molecular concepts "
                            "can still appear when this is false."
                        ),
                    },
                    {
                        "name": "linked",
                        "in": "query",
                        "schema": {"type": "boolean"},
                        "description": (
                            "Include query-linked concept highlights and span-level mentions "
                            "in the initial search payload."
                        ),
                    },
                    {
                        "name": "evidence_items",
                        "in": "query",
                        "schema": {"type": "boolean"},
                        "description": "Include compact evidence snippets in search hits. Full evidence is available through /api/detail.",
                    },
                    {
                        "name": "debug",
                        "in": "query",
                        "schema": {"type": "boolean"},
                        "description": "Include vector lineage and retrieval debug fields on hits.",
                    },
                    {
                        "name": "semantic_bucket",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Comma-separated custom semantic bucket keys.",
                    },
                    {
                        "name": "codes",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": (
                            "Source asserted code systems to return. default/none/all control "
                            "code mappings on concept hits; a specific SAB such as RXNORM, "
                            "SNOMEDCT_US, ICD10CM, or LNC returns source vocabulary rows for "
                            "ordinary text searches and never falls back to concept hits."
                        ),
                    },
                ],
                "responses": {
                    "200": {"description": "Ranked concept hits grouped by semantic bucket."},
                    "400": {"description": "Validation error."},
                },
            }
        },
        "/api/resolve": {
            "get": {
                "summary": "Resolve direct CUI/code/text input before full search",
                "parameters": [
                    {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                    {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
                ],
                "responses": {"200": {"description": "Resolution candidates."}},
            }
        },
        "/api/detail": {
            "get": {
                "summary": "Fetch lazy details for a result by doc_id or CUI",
                "parameters": [
                    {"name": "doc_id", "in": "query", "schema": {"type": "string"}},
                    {"name": "cui", "in": "query", "schema": {"type": "string", "pattern": "^C[0-9]{7}$"}},
                    {
                        "name": "profile",
                        "in": "query",
                        "schema": {
                            "type": "string",
                            "enum": ["product", "review", "benchmark", "umls_only"],
                        },
                        "description": "Preset defaults matching /api/search profiles.",
                    },
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "include_related", "in": "query", "schema": {"type": "boolean"}},
                    {
                        "name": "scope",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["umls", "umls_evidence"]},
                    },
                    {
                        "name": "codes",
                        "in": "query",
                        "schema": {"type": "string"},
                        "description": "Source asserted code systems to return.",
                    },
                ],
                "responses": {"200": {"description": "Detailed concept record."}},
            }
        },
        "/api/related": {
            "get": {
                "summary": "Fetch related concepts and mappings for a CUI",
                "parameters": [
                    {"name": "cui", "in": "query", "required": True, "schema": {"type": "string", "pattern": "^C[0-9]{7}$"}},
                    {"name": "k", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100}},
                    {"name": "vocab", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {"200": {"description": "Related concept bundle."}},
            }
        },
        "/api/judgments": {
            "get": {"summary": "Read local search quality judgments", "responses": {"200": {"description": "Judgment rows."}}},
            "post": {"summary": "Upsert, delete, or replace local search quality judgments", "responses": {"200": {"description": "Persisted judgment rows."}}},
        },
        "/api/openapi.json": {
            "get": {"summary": "Machine-readable API contract", "responses": {"200": {"description": "OpenAPI 3.1 document."}}},
        },
    },
    "components": {
        "schemas": {
            "ApiError": {
                "type": "object",
                "required": ["error"],
                "properties": {
                    "error": {
                        "type": "object",
                        "required": ["code", "message", "status"],
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "status": {"type": "integer"},
                        },
                    }
                },
            }
        }
    },
}

SEARCH_PROFILE_DEFAULTS = {
    "product": {
        "k": 60,
        "mode": "balanced",
        "scope": "umls_evidence",
        "include_related": True,
        "include_linked": True,
        "include_evidence_items": False,
        "include_molecular_associations": False,
        "debug": False,
    },
    "review": {
        "k": 60,
        "mode": "balanced",
        "scope": "umls_evidence",
        "include_related": True,
        "include_linked": True,
        "include_evidence_items": False,
        "include_molecular_associations": False,
        "debug": False,
    },
    "benchmark": {
        "k": 60,
        "mode": "balanced",
        "scope": "umls_evidence",
        "include_related": True,
        "include_linked": True,
        "include_evidence_items": False,
        "include_molecular_associations": False,
        "debug": False,
    },
    "umls_only": {
        "k": 60,
        "mode": "balanced",
        "scope": "umls",
        "include_related": True,
        "include_linked": True,
        "include_evidence_items": False,
        "include_molecular_associations": False,
        "debug": False,
    },
}


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


def parse_search_profile(params: dict) -> tuple[str, dict, str | None]:
    profile = (params.get("profile") or [""])[0].strip().lower()
    if not profile:
        return "", {}, None
    defaults = SEARCH_PROFILE_DEFAULTS.get(profile)
    if defaults is None:
        return profile, {}, (
            "profile must be one of "
            + ", ".join(sorted(SEARCH_PROFILE_DEFAULTS))
        )
    return profile, defaults, None


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


def valid_judgment(row: dict) -> bool:
    return bool(row.get("query") and row.get("doc_id") and row.get("grade") in VALID_JUDGMENT_GRADES)


def read_judgments(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            normalized = normalize_judgment(row)
            if not valid_judgment(normalized):
                continue
            rows.append(normalized)
    return rows


def write_judgments(path: Path, judgments: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalize_judgment(row) for row in judgments]
    normalized = [
        row
        for row in normalized
        if valid_judgment(row)
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


def upsert_judgment(path: Path, judgment: dict) -> list[dict]:
    normalized = normalize_judgment(judgment)
    if not valid_judgment(normalized):
        raise ValueError("judgment requires query, doc_id, and grade relevant/partial/wrong")
    rows = {judgment_key(row): row for row in read_judgments(path)}
    rows[judgment_key(normalized)] = normalized
    write_judgments(path, list(rows.values()))
    return read_judgments(path)


def delete_judgment(path: Path, judgment: dict) -> list[dict]:
    normalized = normalize_judgment(judgment)
    if not normalized["query"] or not normalized["doc_id"]:
        raise ValueError("delete requires query and doc_id")
    rows = {judgment_key(row): row for row in read_judgments(path)}
    rows.pop(judgment_key(normalized), None)
    write_judgments(path, list(rows.values()))
    return read_judgments(path)


def make_handler(
    index: SearchIndex,
    html_path: Path,
    progress_html_path: Path,
    source_dashboard_html_path: Path | None,
    progress_plan_path: Path,
    full_progress_plan_path: Path,
    judgments_path: Path,
    product_html_path: Path | None = None,
    *,
    plan_status_func: Callable[[dict], dict],
    resolve_path_func: Callable[[str], Path],
):
    search_quality_dir = html_path.parent / "search_quality"
    root_html_path = product_html_path or html_path
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
        "/search_quality_real_short_queries.json": (
            search_quality_dir / "real_short_queries.json",
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
                self.send_html(root_html_path.read_text(encoding="utf-8"))
                return
            if parsed.path in {"/review", "/review/", "/review.html"}:
                self.send_html(html_path.read_text(encoding="utf-8"))
                return
            if parsed.path == "/api/health":
                self.send_json(
                    {
                        "ok": True,
                        "api_version": API_VERSION,
                        "records": len(index.records),
                        "backend": index.status().get("search_backend"),
                    }
                )
                return
            if parsed.path == "/api/openapi.json":
                self.send_json(OPENAPI_SPEC)
                return
            if parsed.path == "/progress":
                self.send_html(progress_html_path.read_text(encoding="utf-8"))
                return
            if parsed.path in {"/source-dashboard", "/evidence-dashboard"}:
                if not source_dashboard_html_path or not source_dashboard_html_path.exists():
                    self.send_error_json("not_found", "source dashboard has not been generated", status=404)
                    return
                self.send_html(source_dashboard_html_path.read_text(encoding="utf-8"))
                return
            if parsed.path in static_assets:
                asset_path, content_type = static_assets[parsed.path]
                if not asset_path.exists():
                    self.send_error_json("not_found", "not found", status=404)
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
                    self.send_error_json("invalid_parameter", error, status=400)
                    return
                if not query:
                    self.send_error_json("missing_parameter", "missing q", status=400)
                    return
                self.send_json(index.public_output_payload(index.resolve(query, limit=limit or 10)))
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
                    self.send_error_json("invalid_parameter", error, status=400)
                    return
                if not cui:
                    self.send_error_json("missing_parameter", "missing cui", status=400)
                    return
                if not is_cui(cui):
                    self.send_error_json("invalid_cui", "cui must look like C0000000", status=400)
                    return
                self.send_json(
                    index.public_output_payload(
                        index.related_bundle(
                            cui,
                            top_k=top_k or 10,
                            mapping_sabs=parse_multi_param(params, "sab", "vocab", "system"),
                        )
                    )
                )
                return
            if parsed.path == "/api/detail":
                params = parse_qs(parsed.query)
                _, profile_defaults, profile_error = parse_search_profile(params)
                if profile_error:
                    self.send_error_json("invalid_parameter", profile_error, status=400)
                    return
                doc_id = (params.get("doc_id") or [""])[0].strip()
                cui = (params.get("cui") or [""])[0].strip()
                query = (params.get("q") or params.get("query") or [""])[0].strip()
                return_code_sabs = parse_multi_param(
                    params,
                    "codes",
                    "source_codes",
                    "source_code",
                    "code_system",
                    "code_systems",
                    "code_sab",
                    "code_sabs",
                )
                include_related = parse_bool_param(
                    params,
                    "related",
                    "include_related",
                    default=bool(profile_defaults.get("include_related", True)),
                )
                try:
                    search_scope = normalize_search_scope(
                        (
                            params.get("scope")
                            or params.get("search_scope")
                            or [profile_defaults.get("scope", "umls_evidence")]
                        )[0]
                    )
                except ValueError as exc:
                    self.send_error_json("invalid_parameter", str(exc), status=400)
                    return
                if not doc_id and not cui:
                    self.send_error_json("missing_parameter", "missing doc_id or cui", status=400)
                    return
                if cui and not is_cui(cui):
                    self.send_error_json("invalid_cui", "cui must look like C0000000", status=400)
                    return
                bundle = index.detail_bundle(
                    doc_id=doc_id,
                    cui=cui,
                    include_related=include_related,
                    query=query,
                    return_code_sabs=return_code_sabs or None,
                    search_scope=search_scope,
                )
                if bundle.get("error"):
                    error_message = str(bundle["error"])
                    error_status = 404 if error_message != "missing doc_id or cui" else 400
                    self.send_error_json(
                        "not_found" if error_status == 404 else "missing_parameter",
                        error_message,
                        status=error_status,
                    )
                    return
                self.send_json(index.public_output_payload(bundle))
                return
            if parsed.path == "/api/search":
                params = parse_qs(parsed.query)
                _, profile_defaults, profile_error = parse_search_profile(params)
                if profile_error:
                    self.send_error_json("invalid_parameter", profile_error, status=400)
                    return
                query = (params.get("q") or [""])[0].strip()
                top_k, error = parse_bounded_int_param(
                    params,
                    "k",
                    "top_k",
                    "limit",
                    default=int(profile_defaults.get("k", 10)),
                    minimum=1,
                    maximum=100,
                )
                if error:
                    self.send_error_json("invalid_parameter", error, status=400)
                    return
                if not query:
                    self.send_error_json("missing_parameter", "missing q", status=400)
                    return
                include_related = parse_bool_param(
                    params,
                    "related",
                    "include_related",
                    default=bool(profile_defaults.get("include_related", True)),
                )
                include_linked = parse_bool_param(
                    params,
                    "linked",
                    "include_linked",
                    "linked_concepts",
                    default=bool(profile_defaults.get("include_linked", include_related)),
                )
                include_evidence_items = parse_bool_param(
                    params,
                    "evidence_items",
                    "include_evidence_items",
                    "evidence_snippets",
                    default=bool(profile_defaults.get("include_evidence_items", True)),
                )
                include_molecular_associations = parse_bool_param(
                    params,
                    "molecular_associations",
                    "include_molecular_associations",
                    default=bool(profile_defaults.get("include_molecular_associations", False)),
                )
                debug = parse_bool_param(params, "debug", default=bool(profile_defaults.get("debug", False)))
                semantic_bucket_keys = parse_multi_param(
                    params,
                    "semantic_bucket",
                    "semantic_buckets",
                    "bucket",
                    "buckets",
                    "semantic_group",
                    "semantic_groups",
                )
                return_code_sabs = parse_multi_param(
                    params,
                    "codes",
                    "source_codes",
                    "source_code",
                    "code_system",
                    "code_systems",
                    "code_sab",
                    "code_sabs",
                )
                search_mode = (
                    (
                        params.get("mode")
                        or params.get("search_mode")
                        or [profile_defaults.get("mode", "balanced")]
                    )[0]
                    .strip()
                    .lower()
                )
                search_scope = (
                    (
                        params.get("scope")
                        or params.get("search_scope")
                        or [profile_defaults.get("scope", "umls_evidence")]
                    )[0]
                    .strip()
                    .lower()
                )
                try:
                    self.send_json(
                        index.public_output_payload(
                            index.search(
                                query,
                                top_k=top_k or 10,
                                include_related=include_related,
                                include_linked_concepts=include_linked,
                                include_evidence_items=include_evidence_items,
                                include_molecular_associations=include_molecular_associations,
                                semantic_bucket_keys=semantic_bucket_keys,
                                search_mode=search_mode,
                                search_scope=search_scope,
                                return_code_sabs=return_code_sabs or None,
                                debug=debug,
                            )
                        )
                    )
                except ValueError as exc:
                    self.send_error_json("invalid_parameter", str(exc), status=400)
                except SearchBackendUnavailable as exc:
                    self.send_error_json("backend_unavailable", str(exc), status=503)
                return
            self.send_error_json("not_found", "not found", status=404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/judgments":
                self.send_error_json("not_found", "not found", status=404)
                return
            try:
                length = int(self.headers.get("Content-Length") or "0")
                body = self.rfile.read(length).decode("utf-8")
                payload = json.loads(body or "{}")
                if isinstance(payload.get("judgment"), dict):
                    rows = upsert_judgment(judgments_path, payload["judgment"])
                elif isinstance(payload.get("delete"), dict):
                    rows = delete_judgment(judgments_path, payload["delete"])
                else:
                    payload_rows = payload.get("judgments")
                    if not isinstance(payload_rows, list):
                        self.send_error_json(
                            "invalid_payload",
                            "expected judgments array, judgment object, or delete object",
                            status=400,
                        )
                        return
                    write_judgments(judgments_path, payload_rows)
                    rows = read_judgments(judgments_path)
                self.send_json(
                    {
                        "path": str(judgments_path),
                        "count": len(rows),
                        "judgments": rows,
                    }
                )
            except ValueError as exc:
                self.send_error_json("invalid_payload", str(exc), status=400)
            except Exception as exc:
                self.send_error_json("invalid_payload", str(exc), status=400)

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

        def send_error_json(self, code: str, message: str, *, status: int = 400) -> None:
            self.send_json(api_error(code, message, status=status), status=status)

        def send_common_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")

    return Handler
