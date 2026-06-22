#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # Use the local Python environment for the API when it exists.
  source ".venv/bin/activate"
fi

api_pid=""
editor_pid=""
started_pid=""

cleanup() {
  trap - INT TERM HUP EXIT

  local pids=()
  [[ -n "$api_pid" ]] && pids+=("$api_pid")
  [[ -n "$editor_pid" ]] && pids+=("$editor_pid")

  if ((${#pids[@]})); then
    echo
    echo "Stopping dev servers..."
    for pid in "${pids[@]}"; do
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    done
    wait "${pids[@]}" 2>/dev/null || true
  fi
}

start_group() {
  perl -MPOSIX=setsid -e 'setsid or die "setsid failed: $!"; exec @ARGV or die "exec failed: $!"' "$@" &
  started_pid="$!"
}

trap cleanup INT TERM HUP EXIT

echo "Starting API on http://127.0.0.1:8000"
start_group pnpm dev:api
api_pid="$started_pid"

echo "Starting editor on http://localhost:5173"
start_group pnpm dev:editor
editor_pid="$started_pid"

echo
echo "Dev servers are running. Press Ctrl-C to stop both."

while true; do
  if ! kill -0 "$api_pid" 2>/dev/null; then
    wait "$api_pid" 2>/dev/null || exit $?
    exit 0
  fi

  if ! kill -0 "$editor_pid" 2>/dev/null; then
    wait "$editor_pid" 2>/dev/null || exit $?
    exit 0
  fi

  sleep 1
done
