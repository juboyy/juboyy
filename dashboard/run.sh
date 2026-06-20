#!/usr/bin/env bash
# Convenience launcher for the BTC 5m dashboard.
#
#   ./run.sh                 # demo mode on :8787
#   ./run.sh --demo
#   ./run.sh --runtime /path/to/bot/runtime --config /path/to/btc_5m_profiles.yaml
#
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8787}"
exec python3 app.py --port "$PORT" "$@"
