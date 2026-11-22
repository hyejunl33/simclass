#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../server"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
source .venv/bin/activate
exec uvicorn app.main:app --reload --host 0.0.0.0 --port 8010
