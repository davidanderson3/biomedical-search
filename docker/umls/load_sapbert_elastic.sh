#!/bin/sh
set -eu

ELASTIC_URL="${ELASTIC_URL:-http://elasticsearch:9200}"
ELASTIC_INDEX="${ELASTIC_INDEX:-qe-scaling-sapbert-cls}"
ELASTIC_ALIAS="${ELASTIC_ALIAS:-}"
BULK_DOCS_PER_FILE="${BULK_DOCS_PER_FILE:-5000}"
ELASTIC_SHARDS="${ELASTIC_SHARDS:-1}"
ELASTIC_REPLICAS="${ELASTIC_REPLICAS:-0}"
MANIFEST="${MANIFEST:-build/runtime_payload_manifest.json}"
OUT_DIR="${OUT_DIR:-build/docker_elastic/${ELASTIC_INDEX}}"
FORCE_RELOAD="${FORCE_RELOAD:-0}"
ELASTIC_READY_TIMEOUT="${ELASTIC_READY_TIMEOUT:-600}"
ELASTIC_BUILD_FROM_SHARDS="${ELASTIC_BUILD_FROM_SHARDS:-0}"
ELASTIC_EXPECTED_DOCS="${ELASTIC_EXPECTED_DOCS:-190051}"
ELASTIC_SNAPSHOT_REPO="${ELASTIC_SNAPSHOT_REPO:-qe-public-search-sapbert}"
ELASTIC_SNAPSHOT_NAME="${ELASTIC_SNAPSHOT_NAME:-latest}"
ELASTIC_SNAPSHOT_DIR="${ELASTIC_SNAPSHOT_DIR:-/workspace/build/elasticsearch_snapshots/${ELASTIC_SNAPSHOT_REPO}}"
PUBLIC_SEARCH_PAYLOAD_PROFILE="${PUBLIC_SEARCH_PAYLOAD_PROFILE:-full}"

progress() {
  echo "[install $(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
}

wait_for_elasticsearch() {
  python3 - "$ELASTIC_URL" "$ELASTIC_READY_TIMEOUT" <<'PY'
import sys
import time
import urllib.request

base_url = sys.argv[1].rstrip("/")
try:
    timeout_seconds = int(sys.argv[2])
except ValueError as exc:
    raise SystemExit(f"ELASTIC_READY_TIMEOUT must be an integer number of seconds; got {sys.argv[2]!r}") from exc
deadline = time.time() + timeout_seconds
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(base_url, timeout=5) as response:
            if response.status < 500:
                raise SystemExit(0)
    except Exception as exc:
        last_error = exc
    time.sleep(3)
raise SystemExit(
    f"The search database service was not ready within {timeout_seconds}s: {last_error}. "
    "If this computer is slow, increase ELASTIC_READY_TIMEOUT and ELASTIC_STARTUP_TIMEOUT."
)
PY
}

vector_record_count() {
  python3 - "$1" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.name.endswith(".manifest.json") and path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        print("unknown")
    else:
        print(data.get("count") or "unknown")
else:
    print("unknown")
PY
}

vector_paths() {
  python3 - "$MANIFEST" "$PUBLIC_SEARCH_PAYLOAD_PROFILE" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
profile = sys.argv[2].strip().lower()

level_zero_stems = [
    "scaling_chunk_001_gap_topics",
    "scaling_chunk_002_common_clinical",
    "scaling_chunk_003_abbreviation_language",
    "scaling_chunk_004_drug_safety_therapeutics",
    "scaling_chunk_005_diagnostics_procedures_devices",
]
full_stems = [
    "scaling_chunk_001_gap_topics",
    "scaling_chunk_002_common_clinical",
    "scaling_chunk_003_abbreviation_language",
    "scaling_chunk_004_drug_safety_therapeutics",
    "scaling_chunk_005_diagnostics_procedures_devices",
    "pubmed_bulk_recent_baseline",
    "pubmed_bulk_recent_next2",
    "pubmed_bulk_recent_1331_1330",
    "pubmed_bulk_recent_1329_1328",
    "pubmed_bulk_recent_1327_1326",
    "pubmed_bulk_recent_1325_1324",
    "pubmed_bulk_recent_1323_1322",
    "pubmed_bulk_recent_1321_1320",
]
aliases = {
    "full": "full",
    "public-slim": "public-slim",
    "level-zero": "level-zero",
    "level-0": "level-zero",
    "category-zero": "level-zero",
    "category-0": "level-zero",
}
profile = aliases.get(profile)
if not profile:
    raise SystemExit(f"unknown PUBLIC_SEARCH_PAYLOAD_PROFILE: {sys.argv[2]}")
selected_stems = set(level_zero_stems if profile == "level-zero" else full_stems)


def stem_from_path(path: str) -> str:
    name = Path(path).name
    for suffix in (
        "_sapbert_cls.manifest.json",
        "_concept_vectors.sapbert_cls.jsonl",
        "_concept_vectors.sapbert_cls.jsonl.gz",
    ):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


paths = []
if manifest_path.exists():
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [
        item["path"]
        for item in data.get("vector_shards", [])
        if item.get("exists", True) and stem_from_path(str(item.get("path", ""))) in selected_stems
    ]
else:
    paths = [f"build/compact_vectors/{stem}_sapbert_cls.manifest.json" for stem in sorted(selected_stems)]

if not paths:
    raise SystemExit(
        f"no vector paths found for profile {profile!r}; check runtime manifest {manifest_path}"
    )
for path in paths:
    path_obj = Path(path)
    if not path_obj.exists():
        raise SystemExit(f"missing vector file: {path}")
    print(path_obj)
PY
}

index_count() {
  python3 - "$ELASTIC_URL" "$ELASTIC_INDEX" <<'PY'
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

base_url, index = sys.argv[1].rstrip("/"), sys.argv[2]
url = f"{base_url}/{urllib.parse.quote(index, safe=',*')}/_count"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    if exc.code == 404:
        print(0)
        raise SystemExit(0)
    raise
except Exception:
    print(0)
    raise SystemExit(0)
print(int(payload.get("count") or 0))
PY
}

restore_elasticsearch_snapshot() {
  if [ ! -d "$ELASTIC_SNAPSHOT_DIR" ]; then
    progress "The packaged search database was not found at $ELASTIC_SNAPSHOT_DIR."
    return 1
  fi
  if ! find "$ELASTIC_SNAPSHOT_DIR" -type f | grep -q .; then
    progress "The packaged search database folder is empty at $ELASTIC_SNAPSHOT_DIR."
    return 1
  fi
  progress "Copying the packaged search database into Docker. This can take several minutes on the first run."
  if python3 - "$ELASTIC_URL" "$ELASTIC_INDEX" "$ELASTIC_SNAPSHOT_REPO" "$ELASTIC_SNAPSHOT_NAME" "$ELASTIC_SNAPSHOT_DIR" <<'PY'
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

base_url, index, repo, snapshot, location = sys.argv[1:6]
base_url = base_url.rstrip("/")

def progress(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[install {timestamp}] {message}", flush=True)


def request(method: str, path: str, payload: dict | None = None, *, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        f"{base_url}/{path.lstrip('/')}",
        data=data,
        method=method,
    )
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {raw}") from exc
    return json.loads(raw.decode("utf-8")) if raw else {}


def index_count() -> int:
    quoted = urllib.parse.quote(index, safe=",*")
    try:
        payload = request("GET", f"{quoted}/_count", timeout=10)
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return 0
        raise
    return int(payload.get("count") or 0)


def recovery_percent():
    quoted = urllib.parse.quote(index, safe=",*")
    try:
        payload = request("GET", f"{quoted}/_recovery?active_only=true", timeout=10)
    except RuntimeError:
        return None
    shards = (payload.get(index) or {}).get("shards") or []
    percents = []
    for shard in shards:
        index_info = shard.get("index") or {}
        files = index_info.get("files") or {}
        bytes_info = index_info.get("size") or {}
        percent_text = str(bytes_info.get("percent") or files.get("percent") or "").strip()
        if percent_text.endswith("%"):
            try:
                percents.append(float(percent_text[:-1]))
            except ValueError:
                pass
    if not percents:
        return None
    return max(0, min(100, int(min(percents))))


repo_path = "_snapshot/" + urllib.parse.quote(repo, safe="")
try:
    request(
        "PUT",
        repo_path,
        {"type": "fs", "settings": {"location": location, "readonly": True}},
    )
    try:
        request("DELETE", urllib.parse.quote(index, safe=",*"))
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
    restore_path = (
        repo_path
        + "/"
        + urllib.parse.quote(snapshot, safe="")
        + "/_restore?wait_for_completion=false"
    )
    request(
        "POST",
        restore_path,
        {
            "indices": index,
            "include_aliases": True,
            "ignore_unavailable": False,
        },
    )

    last_percent = -1
    deadline = time.time() + 7200
    while time.time() < deadline:
        current_percent = recovery_percent()
        if current_percent is not None and current_percent != last_percent:
            if current_percent < 100:
                progress(f"Copying the search database into Docker: {current_percent}% complete.")
            last_percent = current_percent
        try:
            count = index_count()
        except Exception:
            count = 0
        if count > 0 and current_percent is None:
            progress("Finished copying the search database into Docker.")
            raise SystemExit(0)
        time.sleep(5)
    raise RuntimeError("Timed out while copying the packaged search database into Docker")
except Exception as exc:
    print(f"Search database copy failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc
PY
  then
    return 0
  fi
  progress "Could not copy the packaged search database into Docker."
  return 1
}

progress "Starting the search database service inside Docker."
wait_for_elasticsearch
progress "The search database service is ready."

EXISTING_COUNT="$(index_count)"
if [ "$FORCE_RELOAD" != "1" ] && [ "$EXISTING_COUNT" -eq "$ELASTIC_EXPECTED_DOCS" ]; then
  progress "The search database is already ready with $EXISTING_COUNT searchable items."
  exit 0
fi
if [ "$FORCE_RELOAD" != "1" ] && [ "$EXISTING_COUNT" -gt 0 ]; then
  progress "An older or incomplete search database was found. Replacing it with the packaged one."
fi

if [ "$ELASTIC_BUILD_FROM_SHARDS" != "1" ]; then
  if ! restore_elasticsearch_snapshot; then
    raise_message="UMLS Search requires the packaged search database. Rebuild or replace this release package, then run the launcher again."
    progress "$raise_message"
    exit 1
  fi
  RESTORED_COUNT="$(index_count)"
  if [ "$RESTORED_COUNT" -eq "$ELASTIC_EXPECTED_DOCS" ]; then
    progress "The search database is ready with $RESTORED_COUNT searchable items."
    exit 0
  fi
  progress "The search database finished copying, but it has $RESTORED_COUNT searchable items instead of the expected $ELASTIC_EXPECTED_DOCS."
  exit 1
fi

progress "A developer rebuild was requested. Building the search database from the packaged search files."
mkdir -p "$OUT_DIR"

MAPPING="${OUT_DIR}/${ELASTIC_INDEX}.mapping.json"
VECTOR_LIST="${OUT_DIR}/vector_paths.txt"
FIRST=1

vector_paths > "$VECTOR_LIST"
TOTAL_SHARDS="$(wc -l < "$VECTOR_LIST" | tr -d ' ')"
progress "The search database needs to be built from $TOTAL_SHARDS packaged file(s). This can take a while because Docker is loading the searchable medical terms."

SHARD_NUMBER=0
while IFS= read -r VECTOR_PATH; do
  SHARD_NUMBER=$((SHARD_NUMBER + 1))
  STEM="$(basename "$VECTOR_PATH" .jsonl)"
  BULK_BASE="${OUT_DIR}/${STEM}.bulk.ndjson"
  RECORD_COUNT="$(vector_record_count "$VECTOR_PATH")"
  progress "File $SHARD_NUMBER/$TOTAL_SHARDS: preparing $VECTOR_PATH ($RECORD_COUNT searchable items)."
  python3 scripts/runtime_elastic.py export-elastic \
    --vectors "$VECTOR_PATH" \
    --index "$ELASTIC_INDEX" \
    --out-mapping "$MAPPING" \
    --out-bulk "$BULK_BASE" \
    --bulk-docs-per-file "$BULK_DOCS_PER_FILE" \
    --shards "$ELASTIC_SHARDS" \
    --replicas "$ELASTIC_REPLICAS"

  if [ "$FIRST" = "1" ]; then
    progress "File $SHARD_NUMBER/$TOTAL_SHARDS: creating the search database and loading the first items."
    python3 scripts/runtime_elastic.py load-elastic \
      --url "$ELASTIC_URL" \
      --index "$ELASTIC_INDEX" \
      --mapping "$MAPPING" \
      --bulk "$BULK_BASE" \
      --create-index \
      --delete-existing \
      --delete-bulk-after-load
    FIRST=0
  else
    progress "File $SHARD_NUMBER/$TOTAL_SHARDS: adding more searchable items."
    python3 scripts/runtime_elastic.py load-elastic \
      --url "$ELASTIC_URL" \
      --index "$ELASTIC_INDEX" \
      --mapping "$MAPPING" \
      --bulk "$BULK_BASE" \
      --delete-bulk-after-load
  fi
done < "$VECTOR_LIST"

if [ -n "$ELASTIC_ALIAS" ] && [ "$ELASTIC_ALIAS" != "$ELASTIC_INDEX" ]; then
  progress "Adding an alternate search database name for compatibility."
  python3 scripts/runtime_elastic.py alias-elastic \
    --url "$ELASTIC_URL" \
    --index "$ELASTIC_INDEX" \
    --alias "$ELASTIC_ALIAS"
fi

python3 - "$ELASTIC_URL" "$ELASTIC_INDEX" <<'PY'
import json
import sys
import urllib.request

base_url, index = sys.argv[1].rstrip("/"), sys.argv[2]
with urllib.request.urlopen(f"{base_url}/{index}/_count", timeout=30) as response:
    payload = json.loads(response.read().decode("utf-8"))
print(json.dumps({"index": index, "count": payload.get("count")}, indent=2, sort_keys=True))
PY
FINAL_COUNT="$(index_count)"
if [ "$FINAL_COUNT" -ne "$ELASTIC_EXPECTED_DOCS" ]; then
  progress "The rebuilt search database has $FINAL_COUNT searchable items, but this release expects $ELASTIC_EXPECTED_DOCS."
  exit 1
fi
progress "The search database is ready."
