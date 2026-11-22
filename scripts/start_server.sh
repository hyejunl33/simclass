#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${SIMCLASS_PORT:-8010}"
MODE="${SIMCLASS_MODE:-auto}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b-instruct-q4_K_M}"
JUDGE_MODEL="${JUDGE_MODEL:-qwen2.5:7b-instruct-q4_K_M}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

PY="$ROOT/server/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "[simclass] creating server/.venv"
  python3 -m venv "$ROOT/server/.venv"
  "$ROOT/server/.venv/bin/pip" install -q -r "$ROOT/server/requirements.txt"
  PY="$ROOT/server/.venv/bin/python"
fi

if ! "$PY" -c "import uvicorn" >/dev/null 2>&1; then
  echo "[simclass] installing server requirements"
  "$ROOT/server/.venv/bin/pip" install -q -r "$ROOT/server/requirements.txt"
fi

is_macos() { [ "$(uname -s)" = "Darwin" ]; }
is_arm64() { [ "$(uname -m)" = "arm64" ] || [ "$(uname -m)" = "aarch64" ]; }

if [ "$MODE" = "auto" ]; then
  if curl -sf -m 2 "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    MODE="full"
  else
    MODE="mock"
  fi
fi

LLM_MODE="mock"
ASR_MODE="mock"
TTS_MODE="mock"

if [ "$MODE" = "full" ]; then
  if ! curl -sf -m 2 "$OLLAMA_URL/api/tags" | grep -q "$OLLAMA_MODEL"; then
    echo "[simclass] $OLLAMA_MODEL is not pulled; falling back to mock LLM"
    MODE="mock"
  fi
fi

if [ "$MODE" = "full" ]; then
  LLM_MODE="ollama"
  if is_macos && is_arm64; then
    ASR_MODE="mlx"
    TTS_MODE="say"
  elif is_macos; then
    TTS_MODE="say"
  fi
fi

echo "============================================================"
echo " SimClass server"
echo " mode:   $MODE"
echo " LLM:    $LLM_MODE ($OLLAMA_MODEL)"
echo " judge:  $JUDGE_MODEL"
echo " ASR:    $ASR_MODE"
echo " TTS:    $TTS_MODE"
echo " URL:    http://0.0.0.0:$PORT"
echo " health: http://127.0.0.1:$PORT/health"
echo "============================================================"

exec env \
  LLM_MODE="$LLM_MODE" \
  OLLAMA_MODEL="$OLLAMA_MODEL" \
  JUDGE_MODEL="$JUDGE_MODEL" \
  OLLAMA_URL="$OLLAMA_URL/api/chat" \
  ASR_MODE="$ASR_MODE" \
  TTS_MODE="$TTS_MODE" \
  TTS_VOICE="${TTS_VOICE:-Yuna}" \
  "$PY" -m uvicorn app.main:app \
    --app-dir "$ROOT/server" \
    --host 0.0.0.0 \
    --port "$PORT"
