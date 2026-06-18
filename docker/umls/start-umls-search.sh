#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
COMPOSE_FILE="${COMPOSE_FILE:-docker/umls/docker-compose.yml}"
APP_PORT="${APP_PORT:-8766}"
AUTO_OPEN_BROWSER="${AUTO_OPEN_BROWSER:-1}"
PUBLIC_SEARCH_SHOW_DOCKER_LOGS="${PUBLIC_SEARCH_SHOW_DOCKER_LOGS:-0}"
INSTALL_STATE_FILE="${INSTALL_STATE_FILE:-$ROOT_DIR/build/.umls-search-docker-installed}"
OPENED_BROWSER=0
TMP_DIR=""
COMPOSE_PID=""
PROGRESS_PID=""
PROGRESS_STATUS_FILE=""
OPENED_BROWSER_FILE=""
MODE="auto"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$(printf '\033[1m')
  DIM=$(printf '\033[2m')
  GREEN=$(printf '\033[32m')
  BLUE=$(printf '\033[34m')
  YELLOW=$(printf '\033[33m')
  RED=$(printf '\033[31m')
  RESET=$(printf '\033[0m')
else
  BOLD=""
  DIM=""
  GREEN=""
  BLUE=""
  YELLOW=""
  RED=""
  RESET=""
fi

usage() {
  cat <<'EOF'
Usage: docker/umls/start-umls-search.sh [mode] [docker compose up flags]

Modes:
  --auto             Install and run if needed; otherwise run without rebuilding.
  --install          Build the Docker image and prepare the search database, then exit.
  --install-and-run  Build/update the Docker image, prepare the database, and run the website.
  --run              Run an already installed app without building.
  --open-ready       Open the website if it is already running, then exit.

If no mode is provided, --auto is used.
EOF
}

case "${1:-}" in
  --auto|auto)
    MODE="auto"
    shift
    ;;
  --install|install)
    MODE="install"
    shift
    ;;
  --install-and-run|install-and-run)
    MODE="install-and-run"
    shift
    ;;
  --run|run)
    MODE="run"
    shift
    ;;
  --open-ready|open-ready)
    MODE="open-ready"
    shift
    ;;
  --help|-h|help)
    usage
    exit 0
    ;;
esac

cleanup() {
  stop_progress_indicator
  if [ -n "$COMPOSE_PID" ]; then
    kill "$COMPOSE_PID" 2>/dev/null || true
  fi
  if [ -n "$TMP_DIR" ]; then
    rm -rf "$TMP_DIR"
  fi
}

focus_safari_tab() {
  url="$1"
  osascript - "$url" <<'APPLESCRIPT' 2>/dev/null | grep -q '^found$'
on run argv
  set targetUrl to item 1 of argv
  if application "Safari" is not running then return "missing"
  tell application "Safari"
    repeat with browserWindow in windows
      repeat with browserTab in tabs of browserWindow
        try
          set tabUrl to URL of browserTab
          if tabUrl starts with targetUrl then
            set current tab of browserWindow to browserTab
            set index of browserWindow to 1
            activate
            return "found"
          end if
        end try
      end repeat
    end repeat
  end tell
  return "missing"
end run
APPLESCRIPT
}

focus_chrome_tab() {
  url="$1"
  osascript - "$url" <<'APPLESCRIPT' 2>/dev/null | grep -q '^found$'
on run argv
  set targetUrl to item 1 of argv
  if application "Google Chrome" is not running then return "missing"
  tell application "Google Chrome"
    repeat with browserWindow in windows
      set tabNumber to 1
      repeat with browserTab in tabs of browserWindow
        try
          set tabUrl to URL of browserTab
          if tabUrl starts with targetUrl then
            set active tab index of browserWindow to tabNumber
            set index of browserWindow to 1
            activate
            return "found"
          end if
        end try
        set tabNumber to tabNumber + 1
      end repeat
    end repeat
  end tell
  return "missing"
end run
APPLESCRIPT
}

focus_edge_tab() {
  url="$1"
  osascript - "$url" <<'APPLESCRIPT' 2>/dev/null | grep -q '^found$'
on run argv
  set targetUrl to item 1 of argv
  if application "Microsoft Edge" is not running then return "missing"
  tell application "Microsoft Edge"
    repeat with browserWindow in windows
      set tabNumber to 1
      repeat with browserTab in tabs of browserWindow
        try
          set tabUrl to URL of browserTab
          if tabUrl starts with targetUrl then
            set active tab index of browserWindow to tabNumber
            set index of browserWindow to 1
            activate
            return "found"
          end if
        end try
        set tabNumber to tabNumber + 1
      end repeat
    end repeat
  end tell
  return "missing"
end run
APPLESCRIPT
}

focus_existing_browser_tab() {
  url="$1"
  if [ "$(uname -s 2>/dev/null || printf unknown)" != "Darwin" ]; then
    return 1
  fi
  if ! command -v osascript >/dev/null 2>&1; then
    return 1
  fi
  focus_safari_tab "$url" || focus_chrome_tab "$url" || focus_edge_tab "$url"
}

open_browser() {
  url="http://127.0.0.1:${APP_PORT}/"
  case "$(uname -s 2>/dev/null || printf unknown)" in
    Darwin)
      focus_existing_browser_tab "$url" || open "$url" >/dev/null 2>&1
      ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1
      else
        return 1
      fi
      ;;
    CYGWIN*|MINGW*|MSYS*)
      cmd.exe /C start "" "$url" >/dev/null 2>&1
      ;;
    *)
      return 1
      ;;
  esac
}

app_ready() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsS "http://127.0.0.1:${APP_PORT}/api/health" >/dev/null 2>&1
    return $?
  fi
  return 1
}

strip_compose_prefix() {
  line="$1"
  case "$line" in
    *" | "*) printf '%s\n' "${line#* | }" ;;
    *) printf '%s\n' "$line" ;;
  esac
}

useful_line() {
  line="$1"
  case "$line" in
    *"[install "*|*"Loading result details for the website."*|*"Finished loading search data:"*|*"Website ready:"*|*"Stopping server"*)
      return 0
      ;;
  esac
  printf '%s\n' "$line" | grep -Eiq 'error|failed|cannot|missing|invalid|denied|unavailable|exited|killed|traceback|exception'
}

print_user_line() {
  line="$1"
  message=$(strip_compose_prefix "$line")
  if [ "$PUBLIC_SEARCH_SHOW_DOCKER_LOGS" = "1" ] || useful_line "$message"; then
    cleaned=$(printf '%s\n' "$message" | sed 's/^\[install [^]]*\] /[install] /')
    printf '%s\n' "$cleaned"
    if useful_line "$message"; then
      update_progress_status "$cleaned"
    fi
  fi
}

print_header() {
  title="$1"
  subtitle="$2"
  printf '\n%b============================================================%b\n' "$BLUE" "$RESET"
  printf '%bUMLS Search%b\n' "$BOLD" "$RESET"
  printf '%s\n' "$title"
  if [ -n "$subtitle" ]; then
    printf '%b%s%b\n' "$DIM" "$subtitle" "$RESET"
  fi
  printf '%b============================================================%b\n\n' "$BLUE" "$RESET"
}

print_step() {
  printf '%b[setup]%b %s\n' "$BLUE" "$RESET" "$1"
}

print_success() {
  printf '%b[done]%b %s\n' "$GREEN" "$RESET" "$1"
}

print_warning() {
  printf '%b[notice]%b %s\n' "$YELLOW" "$RESET" "$1"
}

print_error() {
  printf '%b[error]%b %s\n' "$RED" "$RESET" "$1"
}

open_ready_app() {
  if [ -n "${OPENED_BROWSER_FILE:-}" ] && [ -e "$OPENED_BROWSER_FILE" ]; then
    return 0
  fi
  if [ -n "${OPENED_BROWSER_FILE:-}" ]; then
    : > "$OPENED_BROWSER_FILE" 2>/dev/null || true
  fi
  mark_installed
  print_success "Website is ready at http://127.0.0.1:${APP_PORT}/"
  if [ "$AUTO_OPEN_BROWSER" != "0" ]; then
    if open_browser; then
      printf '[ready] Opened http://127.0.0.1:%s/ in the default browser.\n' "$APP_PORT"
    else
      printf '[ready] Open http://127.0.0.1:%s/ in your browser.\n' "$APP_PORT"
    fi
  fi
}

format_elapsed() {
  elapsed="$1"
  minutes=$((elapsed / 60))
  seconds=$((elapsed % 60))
  printf '%02d:%02d' "$minutes" "$seconds"
}

update_progress_status() {
  if [ -n "${PROGRESS_STATUS_FILE:-}" ]; then
    printf '%s\n' "$1" > "$PROGRESS_STATUS_FILE" 2>/dev/null || true
  fi
}

start_progress_indicator() {
  status="$1"
  PROGRESS_STATUS_FILE="$TMP_DIR/progress-status"
  update_progress_status "$status"
  printf '%b[progress]%b %s %s\n' "$BLUE" "$RESET" "$(format_elapsed 0)" "$status"
  (
    elapsed=0
    while :; do
      sleep 15
      elapsed=$((elapsed + 15))
      if [ -n "$COMPOSE_PID" ] && ! kill -0 "$COMPOSE_PID" 2>/dev/null; then
        break
      fi
      if app_ready; then
        open_ready_app
        break
      fi
      latest=$(cat "$PROGRESS_STATUS_FILE" 2>/dev/null || printf 'Working')
      printf '%b[progress]%b %s %s\n' "$BLUE" "$RESET" "$(format_elapsed "$elapsed")" "$latest"
    done
  ) &
  PROGRESS_PID=$!
}

stop_progress_indicator() {
  if [ -n "${PROGRESS_PID:-}" ]; then
    kill "$PROGRESS_PID" 2>/dev/null || true
    wait "$PROGRESS_PID" 2>/dev/null || true
    PROGRESS_PID=""
  fi
}

mark_installed() {
  mkdir -p "$(dirname "$INSTALL_STATE_FILE")" 2>/dev/null || true
  {
    printf 'installed_at=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'app_port=%s\n' "$APP_PORT"
  } > "$INSTALL_STATE_FILE" 2>/dev/null || true
}

compose_app_image_exists() {
  image_id=$(
    cd "$ROOT_DIR" &&
      docker compose -f "$COMPOSE_FILE" images -q app 2>/dev/null |
      sed -n '1p'
  )
  [ -n "$image_id" ] && docker image inspect "$image_id" >/dev/null 2>&1
}

has_build_control() {
  for arg do
    case "$arg" in
      --build|--no-build)
        return 0
        ;;
    esac
  done
  return 1
}

run_quiet_compose() {
  description="$1"
  shift
  print_step "$description"
  if [ "$PUBLIC_SEARCH_SHOW_DOCKER_LOGS" = "1" ]; then
    (
      cd "$ROOT_DIR"
      docker compose "$@"
    )
    return $?
  fi

  log_file=$(mktemp "${TMPDIR:-/tmp}/umls-compose.XXXXXX")
  (
    cd "$ROOT_DIR"
    docker compose "$@"
  ) >"$log_file" 2>&1 &
  quiet_pid=$!
  elapsed=0
  while kill -0 "$quiet_pid" 2>/dev/null; do
    sleep 5
    elapsed=$((elapsed + 5))
    if kill -0 "$quiet_pid" 2>/dev/null; then
      latest=$(grep -E '\[install |Copying the search database|Website ready|error|failed|cannot|missing|invalid' "$log_file" 2>/dev/null | tail -n 1 || true)
      if [ -n "$latest" ]; then
        latest=$(strip_compose_prefix "$latest" | sed 's/^\[install [^]]*\] /[install] /')
      else
        latest="$description"
      fi
      printf '%b[progress]%b %s %s\n' "$BLUE" "$RESET" "$(format_elapsed "$elapsed")" "$latest"
    fi
  done
  set +e
  wait "$quiet_pid"
  quiet_status=$?
  set -e
  if [ "$quiet_status" -eq 0 ]; then
    rm -f "$log_file"
    return 0
  fi

  print_error "Docker reported a problem. Recent details:"
  tail -n 80 "$log_file" 2>/dev/null || cat "$log_file"
  rm -f "$log_file"
  return 1
}

latest_app_progress() {
  (
    cd "$ROOT_DIR" &&
      docker compose -f "$COMPOSE_FILE" logs --tail=120 app 2>/dev/null
  ) | while IFS= read -r line; do
    message=$(strip_compose_prefix "$line")
    if useful_line "$message"; then
      printf '%s\n' "$message" | sed 's/^\[install [^]]*\] /[install] /'
    fi
  done | tail -n 1
}

wait_for_app_ready() {
  timeout="${APP_READY_TIMEOUT:-900}"
  elapsed=0
  last_progress=""

  while [ "$elapsed" -lt "$timeout" ]; do
    if app_ready; then
      open_ready_app
      return 0
    fi
    sleep 5
    elapsed=$((elapsed + 5))
    if [ $((elapsed % 15)) -eq 0 ]; then
      latest=$(latest_app_progress || true)
      if [ -z "$latest" ]; then
        latest="Starting Docker containers."
      fi
      if [ "$latest" != "$last_progress" ]; then
        last_progress="$latest"
      fi
      printf '%b[progress]%b %s %s\n' "$BLUE" "$RESET" "$(format_elapsed "$elapsed")" "$last_progress"
    fi
  done

  print_error "UMLS Search did not become ready within ${timeout}s. Recent app logs:"
  (
    cd "$ROOT_DIR" &&
      docker compose -f "$COMPOSE_FILE" logs --tail=80 app 2>/dev/null
  ) || true
  return 1
}

run_compose_up() {
  build_flag="$1"
  shift

  if app_ready; then
    open_ready_app
    print_step "UMLS Search is already running."
    return 0
  fi

  TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/umls.XXXXXX")
  OPENED_BROWSER_FILE="$TMP_DIR/opened-browser"

  print_step "Preparing UMLS Search with Docker."
  if [ -n "$build_flag" ]; then
    run_quiet_compose "Starting Docker containers." -f "$COMPOSE_FILE" up -d "$build_flag" "$@" app
  else
    run_quiet_compose "Starting Docker containers." -f "$COMPOSE_FILE" up -d "$@" app
  fi
  wait_for_app_ready
  STATUS=$?
  cleanup
  return "$STATUS"
}

install_only() {
  if [ "$#" -gt 0 ]; then
    print_warning "Install-only mode ignores Docker Compose runtime flags. Use --install-and-run to pass Compose up flags while starting the app."
  fi

  print_header "Install only" "Builds the Docker image and prepares the packaged search database."
  run_quiet_compose "Step 1/3: Building the UMLS Search Docker image." -f "$COMPOSE_FILE" --profile load build app elastic-loader
  run_quiet_compose "Step 2/3: Starting the search database service." -f "$COMPOSE_FILE" up -d elasticsearch
  run_quiet_compose "Step 3/3: Preparing the packaged search database in Docker." -f "$COMPOSE_FILE" --profile load run --rm elastic-loader

  mark_installed
  (
    cd "$ROOT_DIR"
    docker compose -f "$COMPOSE_FILE" stop elasticsearch >/dev/null 2>&1 || true
  )
  print_success "Install is complete."
}

trap 'cleanup; exit 130' INT TERM

case "$MODE" in
  open-ready)
    if app_ready; then
      open_ready_app
      exit 0
    fi
    exit 1
    ;;
  install)
    install_only "$@"
    exit 0
    ;;
  run)
    if ! has_build_control "$@"; then
      if ! compose_app_image_exists; then
        printf '[run] UMLS Search is not installed yet. Run an install-only launcher first, or rerun this script with --install-and-run.\n'
        exit 1
      fi
      BUILD_FLAG="--no-build"
    else
      BUILD_FLAG=""
    fi
    print_header "Starting UMLS Search" "The website will open when it is ready."
    ;;
  install-and-run)
    if has_build_control "$@"; then
      BUILD_FLAG=""
    else
      BUILD_FLAG="--build"
    fi
    print_header "Install and start" "Builds or updates the app if needed, then opens the website."
    ;;
  auto)
    if has_build_control "$@"; then
      BUILD_FLAG=""
    elif compose_app_image_exists; then
      BUILD_FLAG="--no-build"
      print_header "Starting UMLS Search" "The website will open when it is ready."
    else
      BUILD_FLAG="--build"
      print_header "First start" "No installed app image was found; installing and starting now."
    fi
    ;;
  *)
    usage
    exit 2
    ;;
esac

run_compose_up "$BUILD_FLAG" "$@"
exit "$?"
