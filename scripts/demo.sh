#!/usr/bin/env bash
# Offline demo: run both test suites, then start Flask (cache-only) and Next.js.
set -euo pipefail
cd "$(dirname "$0")/.."

( cd backend && . venv/bin/activate && pytest -q )
npm test

export SCOUT_CACHE_ONLY="${SCOUT_CACHE_ONLY:-1}"
( cd backend && . venv/bin/activate && FLASK_DEBUG=0 python app.py ) &
FLASK_PID=$!
trap 'kill $FLASK_PID 2>/dev/null || true' EXIT
echo "Flask on :5000 (SCOUT_CACHE_ONLY=$SCOUT_CACHE_ONLY). Starting Next.js on :3000 ..."
npm run dev
