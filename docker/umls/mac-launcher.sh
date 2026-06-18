#!/bin/sh
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
LAUNCHER="$ROOT_DIR/docker/umls/start-umls-search.sh"
COMPOSE_FILE="${COMPOSE_FILE:-docker/umls/docker-compose.yml}"
APP_PORT="${APP_PORT:-8766}"
ELASTIC_BUILD_FROM_SHARDS="${ELASTIC_BUILD_FROM_SHARDS:-0}"
ELASTIC_SNAPSHOT_REPO="${ELASTIC_SNAPSHOT_REPO:-qe-public-search-sapbert}"
MODE="${1:-auto}"
if [ "$#" -gt 0 ]; then
  shift
fi

pause_before_close() {
  printf '\nPress Return to close this window.'
  if [ -r /dev/tty ]; then
    read _ 2>/dev/null </dev/tty || true
  else
    read _ 2>/dev/null || true
  fi
}

close_click_terminal_window() {
  if [ "${PUBLIC_SEARCH_CLICK_LAUNCHER:-0}" != "1" ]; then
    return 0
  fi
  if [ "$(uname -s 2>/dev/null || printf unknown)" != "Darwin" ]; then
    return 0
  fi
  if ! command -v osascript >/dev/null 2>&1; then
    return 0
  fi
  TTY_PATH=$(tty 2>/dev/null || true)
  case "$TTY_PATH" in
    /dev/*)
      ;;
    *)
      return 0
      ;;
  esac

  (
    sleep 0.3
    osascript - "$TTY_PATH" <<'APPLESCRIPT'
on run argv
  set targetTty to item 1 of argv
  tell application "Terminal"
    repeat with browserWindow in windows
      repeat with terminalTab in tabs of browserWindow
        try
          if tty of terminalTab is targetTty then
            close browserWindow saving no
            return "closed"
          end if
        end try
      end repeat
    end repeat
  end tell
  return "missing"
end run
APPLESCRIPT
  ) >/dev/null 2>&1 &
}

docker_ready() {
  docker info >/dev/null 2>&1
}

start_docker_desktop() {
  if [ "$(uname -s 2>/dev/null || printf unknown)" != "Darwin" ]; then
    return 1
  fi
  if ! command -v open >/dev/null 2>&1; then
    return 1
  fi

  if open -a Docker >/dev/null 2>&1; then
    return 0
  fi
  if [ -d /Applications/Docker.app ]; then
    open /Applications/Docker.app >/dev/null 2>&1
    return $?
  fi
  if [ -d "$HOME/Applications/Docker.app" ]; then
    open "$HOME/Applications/Docker.app" >/dev/null 2>&1
    return $?
  fi

  return 1
}

wait_for_docker() {
  seconds=0
  printf '[install] Waiting for Docker Desktop to finish starting'
  while [ "$seconds" -lt 120 ]; do
    if docker_ready; then
      printf '\n[install] Docker Desktop is ready.\n'
      return 0
    fi
    printf '.'
    sleep 2
    seconds=$((seconds + 2))
  done
  printf '\n'
  return 1
}

clean_macos_metadata() {
  find "$ROOT_DIR" \( -name '.DS_Store' -o -name '._*' \) -type f -exec rm -f {} + 2>/dev/null || true
}

required_snapshot_ready() {
  if [ -n "${PUBLIC_SEARCH_PAYLOAD_REPO:-}" ]; then
    return 0
  fi
  if [ "$ELASTIC_BUILD_FROM_SHARDS" = "1" ]; then
    return 0
  fi
  SNAPSHOT_DIR="${ELASTIC_SNAPSHOT_DIR:-$ROOT_DIR/build/elasticsearch_snapshots/$ELASTIC_SNAPSHOT_REPO}"
  [ -d "$SNAPSHOT_DIR" ] && find "$SNAPSHOT_DIR" -type f -print -quit 2>/dev/null | grep -q .
}

open_docker_install_page() {
  if command -v open >/dev/null 2>&1; then
    open "https://www.docker.com/products/docker-desktop/" >/dev/null 2>&1 || true
  fi
}

compose_app_image_exists() {
  IMAGE_ID=$(
    cd "$ROOT_DIR" &&
      docker compose -f "$COMPOSE_FILE" images -q app 2>/dev/null |
      sed -n '1p'
  )
  [ -n "$IMAGE_ID" ] && docker image inspect "$IMAGE_ID" >/dev/null 2>&1
}

require_install_payload() {
  if required_snapshot_ready; then
    return 0
  fi
  printf '[install] The packaged search database is missing from build/elasticsearch_snapshots/%s.\n' "$ELASTIC_SNAPSHOT_REPO"
  printf '[install] UMLS Search requires that database for installation. Rebuild or replace this release package, then run this file again.\n'
  pause_before_close
  exit 1
}

clean_macos_metadata

case "$MODE" in
  auto|install|run)
    ;;
  *)
    printf '[install] Unknown launcher mode: %s\n' "$MODE"
    pause_before_close
    exit 2
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  printf '[install] Docker Desktop was not found. Opening the official Docker Desktop install page.\n'
  printf '[install] Install and start Docker Desktop, then run this file again.\n'
  open_docker_install_page
  pause_before_close
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  printf '[install] Docker Compose is not available. Start Docker Desktop, then run this file again.\n'
  pause_before_close
  exit 1
fi

if ! docker_ready; then
  printf '[install] Docker Desktop is installed but is not running. Starting Docker Desktop now.\n'
  if start_docker_desktop && wait_for_docker; then
    :
  else
    printf '[install] Docker Desktop did not become ready. If Docker shows setup prompts, finish them, then run this file again.\n'
    pause_before_close
    exit 1
  fi
fi

if [ "$MODE" = "run" ] || [ "$MODE" = "auto" ]; then
  if APP_PORT="$APP_PORT" sh "$LAUNCHER" --open-ready; then
    close_click_terminal_window
    exit 0
  fi
fi

case "$MODE" in
  install)
    require_install_payload
    printf '[install] Installing UMLS Search. This builds the Docker app image and prepares the search database.\n'
    APP_PORT="$APP_PORT" sh "$LAUNCHER" --install "$@"
    STATUS=$?
    if [ "$STATUS" -eq 0 ]; then
      printf '\n[install] UMLS Search install is complete. Use install-run-commands/run-umls-search-mac.command to start the website.\n'
    else
      printf '\n[install] UMLS Search install stopped with an error.\n'
    fi
    ;;
  run)
    if ! compose_app_image_exists; then
      printf '[run] UMLS Search is not installed yet. Run install-run-commands/install-umls-search-mac.command first, or use start-umls-search-mac.command to install and start automatically.\n'
      pause_before_close
      exit 1
    fi
    printf '[run] Starting UMLS Search. The browser will open when it is ready.\n'
    APP_PORT="$APP_PORT" sh "$LAUNCHER" --run "$@"
    STATUS=$?
    printf '\n[run] UMLS Search is running.\n'
    ;;
  auto)
    if compose_app_image_exists; then
      FINAL_LABEL="run"
      printf '[run] Starting UMLS Search. The browser will open when it is ready.\n'
      APP_PORT="$APP_PORT" sh "$LAUNCHER" --run "$@"
    else
      FINAL_LABEL="install"
      require_install_payload
      printf '[install] UMLS Search is not installed yet. Installing and starting now. The browser will open when it is ready.\n'
      APP_PORT="$APP_PORT" sh "$LAUNCHER" --install-and-run "$@"
    fi
    STATUS=$?
    printf '\n[%s] UMLS Search is running.\n' "$FINAL_LABEL"
    ;;
esac

if [ "$STATUS" -eq 0 ]; then
  close_click_terminal_window
  exit 0
fi

pause_before_close
exit "$STATUS"
