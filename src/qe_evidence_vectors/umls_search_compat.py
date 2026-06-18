from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from qe_evidence_vectors.code_index import is_cui, normalize_sab
from qe_evidence_vectors.search_semantics import SEMANTIC_GROUP_LABELS, semantic_group_from_types
from qe_evidence_vectors.text import normalized_key


VALID_INPUT_TYPES = {
    "atom": "atom",
    "code": "code",
    "sourceconcept": "sourceConcept",
    "sourcedescriptor": "sourceDescriptor",
    "sourceui": "sourceUi",
    "tty": "tty",
}
VALID_RETURN_ID_TYPES = {
    "aui": "aui",
    "concept": "concept",
    "code": "code",
    "sourceconcept": "sourceConcept",
    "sourcedescriptor": "sourceDescriptor",
    "sourceui": "sourceUi",
}
VALID_SEARCH_TYPES = {
    "exact": "exact",
    "words": "words",
    "lefttruncation": "leftTruncation",
    "righttruncation": "rightTruncation",
    "normalizedstring": "normalizedString",
    "normalizedwords": "normalizedWords",
}


class UMLSSearchParameterError(ValueError):
    pass


@dataclass(frozen=True)
class UMLSSearchRequest:
    string: str
    input_type: str
    return_id_type: str
    search_type: str
    sabs: tuple[str, ...]
    semantic_types: tuple[str, ...]
    semantic_groups: tuple[str, ...]
    include_obsolete: bool
    include_suppressible: bool
    partial_search: bool
    page_size: int


def umls_search_response(
    index,
    params: dict[str, list[str]],
    *,
    version: str = "current",
    base_uri: str = "https://uts-ws.nlm.nih.gov/rest",
) -> dict:
    request = parse_umls_search_request(params)
    results = umls_search_results(index, request, version=version, base_uri=base_uri)
    return {
        "pageSize": request.page_size,
        "pageNumber": 1,
        "result": {
            "classType": "searchResults",
            "results": results[: request.page_size],
            "recCount": len(results),
        },
    }


def parse_umls_search_request(params: dict[str, list[str]]) -> UMLSSearchRequest:
    query = _first(params, "string", "q").strip()
    if not query:
        raise UMLSSearchParameterError("missing string")
    input_type = _enum_param(
        params,
        "inputType",
        VALID_INPUT_TYPES,
        default="atom",
        display_values=("atom", "code", "sourceConcept", "sourceDescriptor", "sourceUi", "tty"),
    )
    return_id_type = _enum_param(
        params,
        "returnIdType",
        VALID_RETURN_ID_TYPES,
        default="concept",
        display_values=("aui", "concept", "code", "sourceConcept", "sourceDescriptor", "sourceUi"),
    )
    search_type = _enum_param(
        params,
        "searchType",
        VALID_SEARCH_TYPES,
        default="words",
        display_values=(
            "exact",
            "words",
            "leftTruncation",
            "rightTruncation",
            "normalizedString",
            "normalizedWords",
        ),
    )
    page_size = _int_param(params, "pageSize", default=200, minimum=1, maximum=200)
    return UMLSSearchRequest(
        string=query,
        input_type=input_type,
        return_id_type=return_id_type,
        search_type=search_type,
        sabs=_parse_sabs(params),
        semantic_types=tuple(_split_param(params, "semanticTypes")),
        semantic_groups=tuple(_split_param(params, "semanticGroups")),
        include_obsolete=_bool_param(params, "includeObsolete", default=False),
        include_suppressible=_bool_param(params, "includeSuppressible", default=False),
        partial_search=_bool_param(params, "partialSearch", default=False),
        page_size=page_size,
    )


def umls_search_results(
    index,
    request: UMLSSearchRequest,
    *,
    version: str,
    base_uri: str,
) -> list[dict]:
    scan_limit = max(request.page_size * 12, request.page_size + 250)
    if request.return_id_type == "concept":
        rows = _concept_candidate_rows(index, request, limit=scan_limit)
        return _concept_results(index, rows, request, version=version, base_uri=base_uri)
    rows = _source_candidate_rows(index, request, limit=scan_limit)
    return _source_results(index, rows, request, version=version, base_uri=base_uri)


def _concept_candidate_rows(index, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    if request.input_type == "atom":
        if is_cui(request.string) and getattr(index, "code_index", None):
            return [
                _code_row_to_candidate(row, matched_label=row.get("label") or request.string)
                for row in index.code_index.lookup_cui(
                    request.string,
                    sabs=request.sabs or None,
                    limit=limit,
                )
                if _row_visible(row, request)
            ]
        return _label_rows(index, request, limit=limit)
    if request.input_type == "tty":
        return _tty_rows(index, request, limit=limit)
    return [
        _code_row_to_candidate(row)
        for row in _identifier_rows(index, request, limit=limit)
        if _row_visible(row, request)
    ]


def _source_candidate_rows(index, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    if not getattr(index, "code_index", None):
        return []
    if request.input_type == "atom":
        if is_cui(request.string):
            return _source_rows_for_cui(index, request.string, request, limit=limit)
        if request.sabs and request.return_id_type != "aui":
            rows = index.code_index.search_source_atoms(
                request.string,
                sabs=request.sabs,
                include_obsolete=request.include_obsolete,
                include_suppressible=request.include_suppressible,
                limit=limit,
            )
            if rows:
                return rows
        label_rows = _label_rows(index, request, limit=limit)
        return _source_rows_for_label_rows(index, label_rows, request, limit=limit)
    if request.input_type == "tty":
        return _tty_rows(index, request, limit=limit)
    return [
        row
        for row in _identifier_rows(index, request, limit=limit)
        if _row_visible(row, request)
    ]


def _label_rows(index, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    code_index = getattr(index, "code_index", None)
    if code_index:
        rows = code_index.search_labels(
            request.string,
            search_type=request.search_type,
            sabs=request.sabs,
            include_obsolete=request.include_obsolete,
            include_suppressible=request.include_suppressible,
            partial=request.partial_search,
            limit=limit,
        )
        if rows:
            return _dedupe_candidates(rows, key_fields=("cui", "label", "sab", "tty", "code"))[:limit]
    search_label_fallback = getattr(index, "umls_search_label_fallback", None)
    label_fallback = (
        search_label_fallback
        if search_label_fallback and getattr(search_label_fallback, "paths", None)
        else getattr(index, "label_fallback", None)
    )
    if not label_fallback:
        return []
    rows: list[dict] = []
    for label_index in label_fallback.indexes():
        rows.extend(
            label_index.search(
                request.string,
                search_type=request.search_type,
                sabs=request.sabs,
                include_obsolete=request.include_obsolete,
                include_suppressible=request.include_suppressible,
                partial=request.partial_search,
                limit=limit,
            )
        )
    return _dedupe_candidates(rows, key_fields=("cui", "label", "sab", "tty"))[:limit]


def _identifier_rows(index, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    code_index = getattr(index, "code_index", None)
    if not code_index:
        return []
    identifier_type = {
        "code": "CODE",
        "sourceConcept": "SCUI",
        "sourceDescriptor": "SDUI",
    }.get(request.input_type)
    rows: list[dict] = []
    lookup_sabs = request.sabs or ("",)
    if request.input_type == "sourceUi":
        if request.sabs:
            for sab in request.sabs:
                rows.extend(code_index.lookup_code(request.string, sab=sab, limit=limit))
        else:
            rows.extend(code_index.lookup_code(request.string, limit=limit))
    elif identifier_type:
        for sab in lookup_sabs:
            rows.extend(
                code_index.lookup_identifier(
                    request.string,
                    identifier_type=identifier_type,
                    sab=sab or None,
                    limit=limit,
                )
            )
    return _dedupe_candidates(rows, key_fields=("cui", "sab", "code", "scui", "sdui"))[:limit]


def _tty_rows(index, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    code_index = getattr(index, "code_index", None)
    if not code_index:
        return []
    clauses = ["tty = ? COLLATE NOCASE"]
    values: list[object] = [request.string]
    clauses.append(_suppress_visibility_clause(request))
    if request.sabs:
        placeholders = ",".join("?" for _ in request.sabs)
        clauses.append(f"sab IN ({placeholders})")
        values.extend(request.sabs)
    columns = code_index.code_mapping_columns()
    rows = code_index.connection().execute(
        f"""
        SELECT {columns}
        FROM code_mappings
        WHERE {' AND '.join(f'({clause})' for clause in clauses)}
        LIMIT ?
        """,
        (*values, limit),
    )
    return [dict(row) for row in rows]


def _source_rows_for_label_rows(
    index,
    label_rows: Iterable[dict],
    request: UMLSSearchRequest,
    *,
    limit: int,
) -> list[dict]:
    rows: list[dict] = []
    seen_cuis: set[str] = set()
    for label_row in label_rows:
        cui = str(label_row.get("cui") or "").strip().upper()
        if not cui or cui in seen_cuis:
            continue
        seen_cuis.add(cui)
        rows.extend(_source_rows_for_cui(index, cui, request, limit=max(1, limit - len(rows))))
        if len(rows) >= limit:
            break
    return _dedupe_candidates(rows, key_fields=("sab", "code", "scui", "sdui", "matched_identifier"))[:limit]


def _source_rows_for_cui(index, cui: str, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    code_index = getattr(index, "code_index", None)
    if not code_index:
        return []
    if request.return_id_type == "aui":
        return _aui_rows_for_cui(index, cui, request, limit=limit)
    rows = code_index.lookup_cui(cui, sabs=request.sabs or None, limit=limit)
    rows = [
        row
        for row in rows
        if _row_visible(row, request)
        and _source_ui_for_row(row, request.return_id_type)
    ]
    return rows[:limit]


def _aui_rows_for_cui(index, cui: str, request: UMLSSearchRequest, *, limit: int) -> list[dict]:
    code_index = getattr(index, "code_index", None)
    if not code_index:
        return []
    return code_index.lookup_aui_for_cui(
        cui,
        sabs=request.sabs or None,
        include_obsolete=request.include_obsolete,
        include_suppressible=request.include_suppressible,
        limit=limit,
    )


def _concept_results(
    index,
    rows: Iterable[dict],
    request: UMLSSearchRequest,
    *,
    version: str,
    base_uri: str,
) -> list[dict]:
    best_by_cui: dict[str, dict] = {}
    for rank, row in enumerate(rows):
        cui = str(row.get("cui") or "").strip().upper()
        if not cui:
            continue
        semantic_types = _semantic_types(index, cui)
        if not _passes_semantic_filters(semantic_types, request):
            continue
        item = _concept_result(index, row, semantic_types, version=version, base_uri=base_uri)
        if not item:
            continue
        current = best_by_cui.get(cui)
        if current is None or _candidate_rank_key(row, rank) < current["_rank_key"]:
            item["_rank_key"] = _candidate_rank_key(row, rank)
            best_by_cui[cui] = item
    results = sorted(best_by_cui.values(), key=lambda item: item.pop("_rank_key"))
    return results


def _source_results(
    index,
    rows: Iterable[dict],
    request: UMLSSearchRequest,
    *,
    version: str,
    base_uri: str,
) -> list[dict]:
    best: dict[tuple[str, str], dict] = {}
    for rank, row in enumerate(rows):
        cui = str(row.get("cui") or "").strip().upper()
        semantic_types = _semantic_types(index, cui)
        if not _passes_semantic_filters(semantic_types, request):
            continue
        item = _source_result(row, request, version=version, base_uri=base_uri)
        if not item:
            continue
        if _public_output_enabled(index) and not index.public_source_allowed(item.get("rootSource")):
            continue
        key = (str(item.get("rootSource") or ""), str(item.get("ui") or "").upper())
        current = best.get(key)
        if current is None or _candidate_rank_key(row, rank) < current["_rank_key"]:
            item["_rank_key"] = _candidate_rank_key(row, rank)
            best[key] = item
    results = sorted(best.values(), key=lambda item: item.pop("_rank_key"))
    return results


def _concept_result(index, row: dict, semantic_types: list[dict], *, version: str, base_uri: str) -> dict | None:
    cui = str(row.get("cui") or "").strip().upper()
    if _public_output_enabled(index):
        name = index.public_display_label_for_cui(cui)
        if not name:
            return None
    else:
        name = (
            _call_string_method(index, "preferred_label_for_cui", cui)
            or str(row.get("label") or row.get("matched_label") or "").strip()
            or cui
        )
    root_source = str(row.get("sab") or row.get("rootSource") or "MTH").strip() or "MTH"
    return {
        "ui": cui,
        "rootSource": root_source,
        "uri": f"{base_uri}/content/{version}/CUI/{cui}",
        "name": name,
        "semanticTypes": _semantic_type_names(semantic_types),
    }


def _source_result(row: dict, request: UMLSSearchRequest, *, version: str, base_uri: str) -> dict | None:
    root_source = str(row.get("sab") or "").strip()
    ui = _source_ui_for_row(row, request.return_id_type)
    if not root_source or not ui:
        return None
    if request.return_id_type == "aui":
        uri = f"{base_uri}/content/{version}/AUI/{ui}"
    else:
        uri = f"{base_uri}/content/{version}/source/{root_source}/{ui}"
    return {
        "ui": ui,
        "rootSource": root_source,
        "uri": uri,
        "name": str(row.get("label") or "").strip() or ui,
    }


def _source_ui_for_row(row: dict, return_id_type: str) -> str:
    if return_id_type == "aui":
        if str(row.get("matched_identifier_type") or row.get("identifier_type") or "").upper() == "AUI":
            return str(row.get("matched_identifier") or row.get("identifier") or "").strip()
        return str(row.get("aui") or row.get("legacy_aui") or "").strip()
    if return_id_type == "sourceConcept":
        return str(row.get("scui") or "").strip()
    if return_id_type == "sourceDescriptor":
        return str(row.get("sdui") or "").strip()
    if return_id_type == "sourceUi":
        return str(row.get("code") or row.get("scui") or row.get("sdui") or "").strip()
    return str(row.get("code") or "").strip()


def _code_row_to_candidate(row: dict, *, matched_label: str = "") -> dict:
    item = dict(row)
    if matched_label and not item.get("label"):
        item["label"] = matched_label
    return item


def _passes_semantic_filters(semantic_types: list[dict], request: UMLSSearchRequest) -> bool:
    if request.semantic_types and not _semantic_type_filter_match(semantic_types, request.semantic_types):
        return False
    if request.semantic_groups and not _semantic_group_filter_match(semantic_types, request.semantic_groups):
        return False
    return True


def _semantic_type_filter_match(semantic_types: list[dict], filters: tuple[str, ...]) -> bool:
    for item in semantic_types:
        tui = str(item.get("tui") or "").strip().lower()
        stn = str(item.get("stn") or "").strip().lower()
        name = str(item.get("name") or item.get("sty") or "").strip().lower()
        for raw_filter in filters:
            value = str(raw_filter or "").strip().lower()
            if not value:
                continue
            if re.fullmatch(r"t\d{3}", value) and tui == value:
                return True
            if re.fullmatch(r"[a-z]\d+(?:\.\d+)*", value) and stn.startswith(value):
                return True
            if name == value:
                return True
    return False


def _semantic_group_filter_match(semantic_types: list[dict], filters: tuple[str, ...]) -> bool:
    group = semantic_group_from_types(semantic_types)
    label = SEMANTIC_GROUP_LABELS.get(group, "")
    values = {group.lower(), label.lower()}
    return any(str(value or "").strip().lower() in values for value in filters)


def _semantic_types(index, cui: str) -> list[dict]:
    if not cui:
        return []
    try:
        return list(index.semantic_types_for_cui(cui))
    except Exception:
        return []


def _semantic_type_names(semantic_types: list[dict]) -> list[str]:
    names = []
    seen = set()
    for item in semantic_types:
        name = str(item.get("name") or item.get("sty") or "").strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _candidate_rank_key(row: dict, rank: int) -> tuple:
    return (
        0 if normalized_key(str(row.get("label") or "")) else 1,
        0 if str(row.get("suppress") or "") == "N" else 1,
        0 if str(row.get("ispref") or "") == "Y" else 1,
        rank,
        str(row.get("label") or "").lower(),
        str(row.get("cui") or ""),
    )


def _row_visible(row: dict, request: UMLSSearchRequest) -> bool:
    suppress = str(row.get("suppress") or "N").strip().upper()
    if suppress == "N":
        return True
    if suppress == "O":
        return request.include_obsolete
    return request.include_suppressible


def _suppress_visibility_clause(request: UMLSSearchRequest) -> str:
    if request.include_obsolete and request.include_suppressible:
        return "1 = 1"
    if request.include_obsolete:
        return "suppress IN ('N', 'O')"
    if request.include_suppressible:
        return "suppress IN ('N', 'E', 'Y')"
    return "suppress = 'N'"


def _dedupe_candidates(rows: Iterable[dict], *, key_fields: tuple[str, ...]) -> list[dict]:
    seen = set()
    output = []
    for row in rows:
        key = tuple(str(row.get(field) or "").upper() for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        output.append(dict(row))
    return output


def _parse_sabs(params: dict[str, list[str]]) -> tuple[str, ...]:
    values = []
    for value in _split_param(params, "sabs", separator=","):
        sab = normalize_sab(value)
        if sab and sab not in values:
            values.append(sab)
    return tuple(values)


def _split_param(
    params: dict[str, list[str]],
    name: str,
    *,
    separator: str = "|",
) -> list[str]:
    values = []
    for raw in params.get(name, []):
        text = str(raw or "").strip()
        if not text:
            continue
        parts = text.split(separator)
        values.extend(part.strip() for part in parts if part.strip())
    return values


def _first(params: dict[str, list[str]], *names: str, default: str = "") -> str:
    for name in names:
        values = params.get(name)
        if values:
            return str(values[0] or "")
    return default


def _enum_param(
    params: dict[str, list[str]],
    name: str,
    valid: dict[str, str],
    *,
    default: str,
    display_values: tuple[str, ...],
) -> str:
    raw = _first(params, name, default=default).strip()
    key = raw.lower()
    value = valid.get(key)
    if value:
        return value
    raise UMLSSearchParameterError(f"{name} must be one of {', '.join(display_values)}")


def _bool_param(params: dict[str, list[str]], name: str, *, default: bool) -> bool:
    raw = _first(params, name, default="")
    if raw == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise UMLSSearchParameterError(f"{name} must be true or false")


def _int_param(
    params: dict[str, list[str]],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _first(params, name, default="")
    if raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise UMLSSearchParameterError(f"{name} must be an integer") from exc
    return max(minimum, min(value, maximum))


def _public_output_enabled(index) -> bool:
    try:
        return bool(index.public_output_enabled())
    except Exception:
        return False


def _call_string_method(index, name: str, *args) -> str:
    method = getattr(index, name, None)
    if not method:
        return ""
    try:
        return str(method(*args) or "").strip()
    except Exception:
        return ""
