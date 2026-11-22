#!/usr/bin/env bash
set -euo pipefail

HOST="${MAC_MINI_HOST:-}"
USER_NAME="${MAC_MINI_USER:-}"

if [ -z "$HOST" ]; then
  echo "usage: MAC_MINI_HOST=<ip-or-host> [MAC_MINI_USER=<user>] $0"
  echo "example: MAC_MINI_HOST=192.168.0.42 MAC_MINI_USER=hyejun $0"
  exit 2
fi

echo "== ping =="
ping -c 1 -W 2 "$HOST"

echo "== health =="
curl -fsS "http://$HOST:8010/health"

echo
echo "== ssh =="
if [ -z "$USER_NAME" ]; then
  echo "MAC_MINI_USER not set; skipping SSH check."
else
  ssh -o ConnectTimeout=5 -o BatchMode=yes "$USER_NAME@$HOST" "echo ssh-ok"
fi

echo
echo "Next: set app/processing/SimClass/data/server.txt to http://$HOST:8010"
