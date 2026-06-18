#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PUBLIC_SEARCH_CLICK_LAUNCHER=1 exec sh "$ROOT_DIR/docker/umls/mac-launcher.sh" install "$@"
