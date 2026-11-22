#!/usr/bin/env bash
set -euo pipefail
exec env SIMCLASS_MODE=mock "$(dirname "$0")/start_server.sh"
