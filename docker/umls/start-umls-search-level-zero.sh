#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

export COMPOSE_FILE="${COMPOSE_FILE:-docker/umls/docker-compose.level-zero.yml}"
export APP_PORT="${APP_PORT:-8776}"
export ELASTIC_PORT="${ELASTIC_PORT:-9210}"
export PUBLIC_SEARCH_PAYLOAD_PROFILE="${PUBLIC_SEARCH_PAYLOAD_PROFILE:-level-zero}"
export INCLUDE_CODE_INDEX="${INCLUDE_CODE_INDEX:-0}"
export ELASTIC_BUILD_FROM_SHARDS="${ELASTIC_BUILD_FROM_SHARDS:-1}"
export ELASTIC_EXPECTED_DOCS="${ELASTIC_EXPECTED_DOCS:-60967}"
export ELASTIC_INDEX="${ELASTIC_INDEX:-qe-level-zero-sapbert-cls}"
export ELASTIC_SNAPSHOT_REPO="${ELASTIC_SNAPSHOT_REPO:-qe-level-zero-sapbert}"
export ELASTIC_SNAPSHOT_DIR="${ELASTIC_SNAPSHOT_DIR:-/workspace/build/elasticsearch_snapshots/qe-level-zero-sapbert}"
export INSTALL_STATE_FILE="${INSTALL_STATE_FILE:-$ROOT_DIR/build/.umls-search-docker-level-zero-installed}"

exec sh "$SCRIPT_DIR/start-umls-search.sh" "$@"
