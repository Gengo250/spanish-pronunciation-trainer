#!/usr/bin/env bash
# Starts the pronunciation trainer: backend (FastAPI) + frontend (Vite).
#
#   ./run.sh           foreground; Ctrl+C brings both down
#   ./run.sh --bg      background; survives closing the terminal
#   ./run.sh --stop    stops whatever was started with --bg
#   ./run.sh --status  shows what is up
#   ./run.sh --logs    follows the logs from --bg mode
#
# In the foreground the processes are children of the terminal: closing the
# window kills both. --bg fixes that by putting each server in its own session
# (setsid), out of reach of the SIGHUP the terminal fires on close.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
BACK_PORT="${BACK_PORT:-8000}"
FRONT_PORT="${FRONT_PORT:-5173}"

mkdir -p "$RUN_DIR"

die() { echo "error: $*" >&2; exit 1; }
port_busy() { ss -ltn 2>/dev/null | grep -q ":$1 "; }
alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

check_deps() {
  command -v uv  >/dev/null || die "uv not found."
  command -v npm >/dev/null || die "npm not found."
  [[ -d "$ROOT/frontend/node_modules" ]] ||
    die "frontend dependencies missing. Run: cd frontend && npm install"
  command -v ffmpeg    >/dev/null || echo "warning: ffmpeg missing — recordings will not be decoded."
  command -v espeak-ng >/dev/null || echo "warning: espeak-ng missing — no reference phonemes."
  [[ -f "$ROOT/.env" ]] ||
    echo "warning: .env missing — copy it from .env.example, or reference audio will fail."
}

ensure_ports_free() {
  if port_busy "$BACK_PORT"; then
    die "port $BACK_PORT is busy. Run ./run.sh --stop first."
  fi
  if port_busy "$FRONT_PORT"; then
    die "port $FRONT_PORT is busy. Run ./run.sh --stop first."
  fi
}

# Puts a server in its own session and records the REAL pid.
#
# The `bash -c 'echo $$ …; exec …'` is there because of a bug that cost dearly:
# recording the `$!` of `setsid` stores the pid of setsid itself, which dies
# right afterwards. --stop would then "stop" a process that no longer existed
# and leave the server up holding the port. Here the inner shell records its own
# pid and replaces itself with the server via `exec`, so the pid stays valid —
# and, being a session leader, `kill -- -PID` takes down the process and its
# children.
spawn() {
  local name="$1" dir="$2"; shift 2
  local pid_file="$RUN_DIR/$name.pid" log="$RUN_DIR/$name.log"
  local quoted; printf -v quoted '%q ' "$@"
  setsid bash -c "cd $(printf '%q' "$dir") && echo \$\$ > $(printf '%q' "$pid_file") && exec $quoted" \
    > "$log" 2>&1 < /dev/null &
  disown 2>/dev/null || true
}

status() {
  local any=1
  for name in backend frontend; do
    if alive "$RUN_DIR/$name.pid"; then
      echo "  $name: running (pid $(cat "$RUN_DIR/$name.pid"))"
      any=0
    else
      echo "  $name: stopped"
    fi
  done
  echo
  echo "  interface: http://localhost:$FRONT_PORT"
  echo "  api:       http://127.0.0.1:$BACK_PORT/api/health"
  return $any
}

stop() {
  local stopped=0
  for name in frontend backend; do
    local pid_file="$RUN_DIR/$name.pid"
    if alive "$pid_file"; then
      local pid; pid="$(cat "$pid_file")"
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
      kill -0 "$pid" 2>/dev/null && kill -KILL -- "-$pid" 2>/dev/null
      echo "  $name stopped (pid $pid)"
      stopped=1
    fi
    rm -f "$pid_file"
  done
  # Safety net. A `--bg` interrupted halfway leaves a server up with no pid
  # file, and the path above then finds nothing to kill. Warning and exiting
  # would be a lie: "stop" has to stop. Whoever holds the port owns the app, so
  # we take it down by port.
  for port in "$BACK_PORT" "$FRONT_PORT"; do
    port_busy "$port" || continue
    pids=$(ss -ltnp 2>/dev/null | grep ":$port " |
           grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
    for pid in $pids; do
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 15); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
      echo "  orphan process on port $port stopped (pid $pid)"
      stopped=1
    done
  done

  [[ $stopped -eq 1 ]] || echo "  nothing was running"

  for port in "$BACK_PORT" "$FRONT_PORT"; do
    port_busy "$port" && echo "  warning: port $port is still held by another process."
  done
  return 0
}

start_background() {
  check_deps
  ensure_ports_free
  echo "starting in the background…"

  spawn backend  "$ROOT/backend"  uv run uvicorn sptrainer.api.app:app \
        --host 127.0.0.1 --port "$BACK_PORT"
  spawn frontend "$ROOT/frontend" npm run dev -- --port "$FRONT_PORT"

  if curl -sf --retry 45 --retry-delay 1 --retry-connrefused --max-time 90 \
       "http://127.0.0.1:$BACK_PORT/api/health" > /dev/null 2>&1; then
    echo "  backend responded."
  else
    echo "  backend did NOT respond — see $RUN_DIR/backend.log"
  fi

  echo
  status || true
  echo
  echo "  logs: ./run.sh --logs"
  echo "  stop: ./run.sh --stop"
}

start_foreground() {
  check_deps
  ensure_ports_free
  echo "starting in the foreground. Ctrl+C brings both down."
  echo "  interface: http://localhost:$FRONT_PORT"
  echo

  ( cd "$ROOT/backend" && exec uv run uvicorn sptrainer.api.app:app \
      --host 127.0.0.1 --port "$BACK_PORT" --reload ) &
  local back=$!
  ( cd "$ROOT/frontend" && exec npm run dev -- --port "$FRONT_PORT" ) &
  local front=$!

  # Without the trap, Ctrl+C would leave one of the two orphaned on the port.
  trap 'echo; echo "stopping…"; kill "$back" "$front" 2>/dev/null || true' INT TERM
  wait
}

case "${1:---fg}" in
  --bg)     start_background ;;
  --stop)   stop ;;
  --status) status || true ;;
  --logs)   tail -f "$RUN_DIR"/backend.log "$RUN_DIR"/frontend.log ;;
  --fg|"")  start_foreground ;;
  -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \?//' ;;
  *) die "unknown option: $1 (use --fg, --bg, --stop, --status, --logs)" ;;
esac
