#!/bin/sh
set -eu

ELASTIC_URL="${ELASTIC_URL:-http://elasticsearch:9200}"
ELASTIC_INDEX="${ELASTIC_INDEX:-qe-scaling-sapbert-cls}"
ELASTIC_ALIAS="${ELASTIC_ALIAS:-}"
BULK_DOCS_PER_FILE="${BULK_DOCS_PER_FILE:-25000}"
ELASTIC_SHARDS="${ELASTIC_SHARDS:-1}"
ELASTIC_REPLICAS="${ELASTIC_REPLICAS:-0}"
MANIFEST="${MANIFEST:-build/release_candidates/rc_public_search_20260604T211825Z/supporting/manifests/runtime_payload_manifest.json}"
OUT_DIR="${OUT_DIR:-build/docker_elastic/${ELASTIC_INDEX}}"

wait_for_elasticsearch() {
  python3 - "$ELASTIC_URL" <<'PY'
import sys
import time
import urllib.request

base_url = sys.argv[1].rstrip("/")
deadline = time.time() + 180
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(base_url, timeout=5) as response:
            if response.status < 500:
                print(f"Elasticsearch is available at {base_url}")
                raise SystemExit(0)
    except Exception as exc:
        last_error = exc
    time.sleep(3)
raise SystemExit(f"Elasticsearch was not ready at {base_url}: {last_error}")
PY
}

vector_paths() {
  python3 - "$MANIFEST" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
if manifest_path.exists():
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    paths = [item["path"] for item in data.get("vector_shards", []) if item.get("exists", True)]
else:
    paths = []
if not paths:
    raise SystemExit(f"no vector paths found in {manifest_path}")
for path in paths:
    if not Path(path).exists():
        raise SystemExit(f"missing vector file: {path}")
    print(path)
PY
}

wait_for_elasticsearch
mkdir -p "$OUT_DIR"

MAPPING="${OUT_DIR}/${ELASTIC_INDEX}.mapping.json"
VECTOR_LIST="${OUT_DIR}/vector_paths.txt"
FIRST=1

vector_paths > "$VECTOR_LIST"

while IFS= read -r VECTOR_PATH; do
  STEM="$(basename "$VECTOR_PATH" .jsonl)"
  BULK_BASE="${OUT_DIR}/${STEM}.bulk.ndjson"
  echo "Exporting $VECTOR_PATH"
  python3 scripts/evidence_vectors.py export-elastic \
    --vectors "$VECTOR_PATH" \
    --index "$ELASTIC_INDEX" \
    --out-mapping "$MAPPING" \
    --out-bulk "$BULK_BASE" \
    --bulk-docs-per-file "$BULK_DOCS_PER_FILE" \
    --shards "$ELASTIC_SHARDS" \
    --replicas "$ELASTIC_REPLICAS"

  if [ "$FIRST" = "1" ]; then
    echo "Creating and loading $ELASTIC_INDEX"
    python3 scripts/evidence_vectors.py load-elastic \
      --url "$ELASTIC_URL" \
      --index "$ELASTIC_INDEX" \
      --mapping "$MAPPING" \
      --bulk "$BULK_BASE" \
      --create-index \
      --delete-existing \
      --delete-bulk-after-load
    FIRST=0
  else
    echo "Loading additional shard into $ELASTIC_INDEX"
    python3 scripts/evidence_vectors.py load-elastic \
      --url "$ELASTIC_URL" \
      --index "$ELASTIC_INDEX" \
      --mapping "$MAPPING" \
      --bulk "$BULK_BASE" \
    --delete-bulk-after-load
  fi
done < "$VECTOR_LIST"

if [ -n "$ELASTIC_ALIAS" ] && [ "$ELASTIC_ALIAS" != "$ELASTIC_INDEX" ]; then
  python3 scripts/evidence_vectors.py alias-elastic \
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
