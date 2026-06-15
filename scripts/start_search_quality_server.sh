#!/bin/sh
set -eu

PORT="${PORT:-8766}"
ELASTIC_URL="${ELASTIC_URL:-http://localhost:9200}"
ELASTIC_INDEX="${ELASTIC_INDEX:-qe-scaling-sapbert-cls}"
ELASTIC_STARTUP_TIMEOUT="${ELASTIC_STARTUP_TIMEOUT:-0}"
PUBLIC_OUTPUT_ONLY="${PUBLIC_OUTPUT_ONLY:-1}"
PUBLIC_OUTPUT_ARGS=""
if [ "$PUBLIC_OUTPUT_ONLY" = "1" ] || [ "$PUBLIC_OUTPUT_ONLY" = "true" ]; then
  PUBLIC_OUTPUT_ARGS="--public-output-only"
fi
if [ "${PUBLIC_OUTPUT_SOURCE_ALLOWLIST:-}" ]; then
  PUBLIC_OUTPUT_ARGS="$PUBLIC_OUTPUT_ARGS --public-output-source-allowlist $PUBLIC_OUTPUT_SOURCE_ALLOWLIST"
fi

VECTOR_PATHS=""
DOC_PATHS=""

add_vector() {
  if [ -f "$1" ]; then
    VECTOR_PATHS="${VECTOR_PATHS} $1"
  fi
}

add_doc() {
  if [ -f "$1" ]; then
    DOC_PATHS="${DOC_PATHS} $1"
  fi
}

wait_for_elasticsearch_index() {
  python3 - "$ELASTIC_URL" "$ELASTIC_INDEX" "$ELASTIC_STARTUP_TIMEOUT" <<'PY'
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

base_url, index, timeout_text = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3]
try:
    timeout_seconds = int(timeout_text)
except ValueError as exc:
    raise SystemExit(f"ELASTIC_STARTUP_TIMEOUT must be an integer number of seconds; got {timeout_text!r}") from exc

if timeout_seconds <= 0:
    raise SystemExit(0)
if not base_url or not index:
    raise SystemExit("ELASTIC_URL and ELASTIC_INDEX are required when ELASTIC_STARTUP_TIMEOUT is set")

quoted_index = urllib.parse.quote(index, safe=",*")
url = f"{base_url}/{quoted_index}/_count"
deadline = time.time() + timeout_seconds
last_error = None
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status < 400:
                print(f"Elasticsearch index is available at {url}")
                raise SystemExit(0)
            last_error = f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        last_error = f"HTTP {exc.code}"
    except (OSError, urllib.error.URLError) as exc:
        last_error = str(exc)
    time.sleep(3)

raise SystemExit(
    f"Elasticsearch index was not ready at {url} within {timeout_seconds}s: {last_error}"
)
PY
}

add_vector build/scaling_chunk_001_gap_topics_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_002_common_clinical_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_003_abbreviation_language_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_004_drug_safety_therapeutics_concept_vectors.sapbert_cls.jsonl
add_vector build/scaling_chunk_005_diagnostics_procedures_devices_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_baseline_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_next2_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1331_1330_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1329_1328_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1327_1326_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1325_1324_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1323_1322_concept_vectors.sapbert_cls.jsonl
add_vector build/pubmed_bulk_recent_1321_1320_concept_vectors.sapbert_cls.jsonl

add_doc build/scaling_chunk_001_gap_topics_concept_documents.jsonl
add_doc build/scaling_chunk_002_common_clinical_concept_documents.jsonl
add_doc build/scaling_chunk_003_abbreviation_language_concept_documents.jsonl
add_doc build/scaling_chunk_004_drug_safety_therapeutics_concept_documents.jsonl
add_doc build/scaling_chunk_005_diagnostics_procedures_devices_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_baseline_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_next2_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1331_1330_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1329_1328_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1327_1326_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1325_1324_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1323_1322_concept_documents.jsonl
add_doc build/pubmed_bulk_recent_1321_1320_concept_documents.jsonl

wait_for_elasticsearch_index

exec python3 scripts/search_quality_server.py \
  --port "$PORT" \
  --vectors $VECTOR_PATHS \
  --docs $DOC_PATHS \
  --evidence \
  --provenance-index build/search_quality_provenance.sqlite \
  --provider sapbert \
  --local-files-only \
  --max-seq-length 128 \
  --elastic-url "$ELASTIC_URL" \
  --elastic-index "$ELASTIC_INDEX" \
  --elastic-num-candidates 50 \
  --require-elasticsearch \
  --label-fallback-limit 120 \
  --definition-fallback-limit 80 \
  --label-index build/umls_biomedicine_search_label_index.sqlite \
  --code-index build/cui_code_index.sqlite \
  --relation-index build/umls_related_concepts.sqlite \
  $PUBLIC_OUTPUT_ARGS \
  --progress-plan config/pubmed_bulk_recent_1321_1320.plan.json \
  --judgments-out build/scaling_runs/pubmed_bulk_recent_1321_1320/search_quality_judgments.csv \
  "$@"
