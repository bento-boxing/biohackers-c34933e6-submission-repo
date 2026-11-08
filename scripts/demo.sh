#!/usr/bin/env bash
# Local demo: run the test suites, then start the research workbench backend (:5050) and frontend (:3000).
# The workbench backend wraps the Target Scout Flask app, so port 5000 is not needed.
set -euo pipefail
cd "$(dirname "$0")/.."

( cd backend && . venv/bin/activate && pytest -q )
( cd backend && . venv/bin/activate && python -m pytest devils_advocate/tests -q --rootdir=.. ) || true
( cd frontend && npm test )

( cd backend && . venv/bin/activate && cd .. && python -m devils_advocate.server --port 5050 ) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT
echo "Workbench backend on :5050. Starting Next.js on :3000 ..."
( cd frontend && npm run dev )
