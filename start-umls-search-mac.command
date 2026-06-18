#!/bin/sh
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PUBLIC_SEARCH_CLICK_LAUNCHER=1 exec sh "$SCRIPT_DIR/docker/umls/mac-launcher.sh" auto "$@"
