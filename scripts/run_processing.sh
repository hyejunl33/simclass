#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKETCH="$ROOT/app/processing/SimClass"
ACTION="${1:-run}"
OUT="${PROCESSING_OUT:-/tmp/simclass-build}"

find_processing() {
  if [ -n "${PROCESSING_BIN:-}" ] && [ -x "$PROCESSING_BIN" ]; then
    echo "$PROCESSING_BIN"
  elif command -v processing-java >/dev/null 2>&1; then
    echo "processing-java"
  elif [ -x "$HOME/opt/Processing/bin/Processing" ]; then
    echo "$HOME/opt/Processing/bin/Processing"
  elif [ -x "/opt/Processing/bin/Processing" ]; then
    echo "/opt/Processing/bin/Processing"
  else
    echo ""
  fi
}

BIN="$(find_processing)"
if [ -z "$BIN" ]; then
  echo "Processing not found."
  echo "Install Processing 4 or set PROCESSING_BIN=/path/to/Processing."
  echo "Portable download:"
  echo "  https://github.com/processing/processing4/releases"
  exit 1
fi

if [ "$BIN" = "processing-java" ]; then
  case "$ACTION" in
    build) exec processing-java --sketch="$SKETCH" --output="$OUT" --force --build ;;
    run)   exec processing-java --sketch="$SKETCH" --output="$OUT" --force --run ;;
    *) echo "usage: $0 [build|run]"; exit 2 ;;
  esac
fi

case "$ACTION" in
  build) exec "$BIN" cli --sketch="$SKETCH" --output="$OUT" --force --build ;;
  run)   exec "$BIN" cli --sketch="$SKETCH" --output="$OUT" --force --run ;;
  *) echo "usage: $0 [build|run]"; exit 2 ;;
esac
