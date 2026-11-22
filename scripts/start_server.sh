#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${SIMCLASS_PORT:-8010}"
MODE="${SIMCLASS_MODE:-auto}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:3b-instruct-q4_K_M}"
JUDGE_MODEL="${JUDGE_MODEL:-qwen2.5:7b-instruct-q4_K_M}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"
VENV="${SIMCLASS_VENV:-$ROOT/server/.venv}"

is_macos() { [ "$(uname -s)" = "Darwin" ]; }
is_arm64() { [ "$(uname -m)" = "arm64" ] || [ "$(uname -m)" = "aarch64" ]; }

REQ="$ROOT/server/requirements.txt"
if is_macos && is_arm64; then
  REQ="$ROOT/server/requirements-mac.txt"
fi

find_uv() {
  if command -v uv >/dev/null 2>&1; then
    command -v uv
  elif [ -x "$HOME/.local/bin/uv" ]; then
    echo "$HOME/.local/bin/uv"
  elif [ -x "$HOME/.cargo/bin/uv" ]; then
    echo "$HOME/.cargo/bin/uv"
  else
    echo ""
  fi
}

UV="$(find_uv)"
PY="$VENV/bin/python"

if [ ! -x "$PY" ]; then
  echo "[simclass] creating virtual environment at $VENV"
  if [ -n "$UV" ]; then
    "$UV" venv --python 3.12 "$VENV"
  else
    python3 -m venv "$VENV"
  fi
  PY="$VENV/bin/python"
  if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "[simclass] Python 3.10+ is required. Install uv or set SIMCLASS_VENV."
    exit 1
  fi
  echo "[simclass] installing $REQ"
  if [ -n "$UV" ]; then
    "$UV" pip install --python "$PY" -q -r "$REQ"
  else
    "$VENV/bin/pip" install -q -r "$REQ"
  fi
fi

if ! "$PY" -c "import uvicorn" >/dev/null 2>&1; then
  echo "[simclass] installing $REQ"
  if [ -n "$UV" ]; then
    "$UV" pip install --python "$PY" -q -r "$REQ"
  else
    "$VENV/bin/pip" install -q -r "$REQ"
  fi
fi

if is_macos && is_arm64 && [ "$MODE" != "mock" ]; then
  if ! "$PY" -c "import mlx_whisper" >/dev/null 2>&1; then
    echo "[simclass] installing mlx-whisper"
    if [ -n "$UV" ]; then
      "$UV" pip install --python "$PY" -q -r "$ROOT/server/requirements-mac.txt"
    else
      "$VENV/bin/pip" install -q -r "$ROOT/server/requirements-mac.txt"
    fi
  fi
fi

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
echo " venv:   $VENV"
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
