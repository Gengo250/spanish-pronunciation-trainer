#!/usr/bin/env bash
# Sobe o treinador de pronúncia: backend (FastAPI) + frontend (Vite).
#
#   ./run.sh           primeiro plano; Ctrl+C derruba os dois
#   ./run.sh --bg      segundo plano; sobrevive ao fechamento do terminal
#   ./run.sh --stop    derruba o que foi iniciado com --bg
#   ./run.sh --status  mostra o que está de pé
#   ./run.sh --logs    acompanha os logs do modo --bg
#
# Em primeiro plano os processos são filhos do terminal: fechar a janela mata os
# dois. O --bg resolve isso colocando cada servidor na própria sessão (setsid),
# fora do alcance do SIGHUP que o terminal dispara ao fechar.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
BACK_PORT="${BACK_PORT:-8000}"
FRONT_PORT="${FRONT_PORT:-5173}"

mkdir -p "$RUN_DIR"

die() { echo "erro: $*" >&2; exit 1; }
port_busy() { ss -ltn 2>/dev/null | grep -q ":$1 "; }
alive() { [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null; }

check_deps() {
  command -v uv  >/dev/null || die "uv não encontrado."
  command -v npm >/dev/null || die "npm não encontrado."
  [[ -d "$ROOT/frontend/node_modules" ]] ||
    die "frontend sem dependências. Rode: cd frontend && npm install"
  command -v ffmpeg    >/dev/null || echo "aviso: ffmpeg ausente — a gravação não será decodificada."
  command -v espeak-ng >/dev/null || echo "aviso: espeak-ng ausente — sem fonemas de referência."
  [[ -f "$ROOT/.env" ]] ||
    echo "aviso: .env ausente — copie de .env.example, senão o áudio de referência falha."
}

ensure_ports_free() {
  if port_busy "$BACK_PORT"; then
    die "porta $BACK_PORT ocupada. Rode ./run.sh --stop primeiro."
  fi
  if port_busy "$FRONT_PORT"; then
    die "porta $FRONT_PORT ocupada. Rode ./run.sh --stop primeiro."
  fi
}

# Põe um servidor na própria sessão e grava o PID REAL.
#
# O `bash -c 'echo $$ …; exec …'` existe por causa de um erro que custou caro:
# gravar o `$!` de `setsid` guarda o PID do próprio setsid, que morre logo em
# seguida. O --stop então "parava" um processo inexistente e deixava o servidor
# de pé segurando a porta. Aqui o shell interno grava o próprio PID e se
# substitui pelo servidor com `exec`, então o PID continua válido — e, por ser
# líder de sessão, `kill -- -PID` derruba o processo e seus filhos.
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
      echo "  $name: rodando (pid $(cat "$RUN_DIR/$name.pid"))"
      any=0
    else
      echo "  $name: parado"
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
      echo "  $name parado (pid $pid)"
      stopped=1
    fi
    rm -f "$pid_file"
  done
  # Rede de segurança. Um `--bg` interrompido no meio deixa servidor de pé sem
  # pid file, e aí o caminho acima não acha nada para matar. Avisar e sair seria
  # mentir: "parar" tem de parar. Quem segura a porta é dono da aplicação, então
  # derrubamos pela porta.
  for port in "$BACK_PORT" "$FRONT_PORT"; do
    port_busy "$port" || continue
    pids=$(ss -ltnp 2>/dev/null | grep ":$port " |
           grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
    for pid in $pids; do
      kill -TERM "$pid" 2>/dev/null || true
      for _ in $(seq 15); do kill -0 "$pid" 2>/dev/null || break; sleep 0.2; done
      kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
      echo "  processo órfão na porta $port parado (pid $pid)"
      stopped=1
    done
  done

  [[ $stopped -eq 1 ]] || echo "  nada estava rodando"

  for port in "$BACK_PORT" "$FRONT_PORT"; do
    port_busy "$port" && echo "  aviso: porta $port continua ocupada por outro processo."
  done
  return 0
}

start_background() {
  check_deps
  ensure_ports_free
  echo "subindo em segundo plano…"

  spawn backend  "$ROOT/backend"  uv run uvicorn sptrainer.api.app:app \
        --host 127.0.0.1 --port "$BACK_PORT"
  spawn frontend "$ROOT/frontend" npm run dev -- --port "$FRONT_PORT"

  if curl -sf --retry 45 --retry-delay 1 --retry-connrefused --max-time 90 \
       "http://127.0.0.1:$BACK_PORT/api/health" > /dev/null 2>&1; then
    echo "  backend respondeu."
  else
    echo "  backend NÃO respondeu — veja $RUN_DIR/backend.log"
  fi

  echo
  status || true
  echo
  echo "  logs:  ./run.sh --logs"
  echo "  parar: ./run.sh --stop"
}

start_foreground() {
  check_deps
  ensure_ports_free
  echo "subindo em primeiro plano. Ctrl+C derruba os dois."
  echo "  interface: http://localhost:$FRONT_PORT"
  echo

  ( cd "$ROOT/backend" && exec uv run uvicorn sptrainer.api.app:app \
      --host 127.0.0.1 --port "$BACK_PORT" --reload ) &
  local back=$!
  ( cd "$ROOT/frontend" && exec npm run dev -- --port "$FRONT_PORT" ) &
  local front=$!

  # Sem o trap, Ctrl+C deixaria um dos dois órfão segurando a porta.
  trap 'echo; echo "parando…"; kill "$back" "$front" 2>/dev/null || true' INT TERM
  wait
}

case "${1:---fg}" in
  --bg)     start_background ;;
  --stop)   stop ;;
  --status) status || true ;;
  --logs)   tail -f "$RUN_DIR"/backend.log "$RUN_DIR"/frontend.log ;;
  --fg|"")  start_foreground ;;
  -h|--help) sed -n '2,13p' "${BASH_SOURCE[0]}" | sed 's/^# \?//' ;;
  *) die "opção desconhecida: $1 (use --fg, --bg, --stop, --status, --logs)" ;;
esac
