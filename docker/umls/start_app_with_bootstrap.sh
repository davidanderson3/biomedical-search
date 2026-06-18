#!/bin/sh
set -eu

HOST="${HOST:-0.0.0.0}"
SAPBERT_PRELOAD="${SAPBERT_PRELOAD:-1}"
ELASTIC_AUTO_LOAD="${ELASTIC_AUTO_LOAD:-1}"

progress() {
  echo "[install $(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
}

progress "Startup check: making sure this computer has enough memory, CPU, and disk space."
python3 scripts/public_search_preflight.py

progress "Phase 1/4: checking the search data files. These files contain the medical terms, documents, definitions, and source details used by the app."
python3 scripts/ensure_public_search_payload.py

if [ "$SAPBERT_PRELOAD" != "0" ]; then
  progress "Phase 2/4: checking the packaged medical language model, SapBERT. This helps the app match typed searches to related medical terms."
  python3 scripts/ensure_sapbert_cache.py
else
  progress "Phase 2/4: skipping the SapBERT packaged-model check because SAPBERT_PRELOAD=0. Searches will work only if SapBERT is available."
fi

if [ "$ELASTIC_AUTO_LOAD" != "0" ]; then
  progress "Phase 3/4: checking the search database. On the first run, UMLS Search copies the packaged search database into Docker; this can take several minutes."
  sh docker/umls/load_sapbert_elastic.sh
else
  progress "Phase 3/4: skipping the search database check because ELASTIC_AUTO_LOAD=0. The database must already be ready."
fi

progress "Phase 4/4: starting the website. The app is loading names, definitions, codes, and source details before it is ready."
exec sh scripts/start_search_quality_server.sh --host "$HOST" "$@"
