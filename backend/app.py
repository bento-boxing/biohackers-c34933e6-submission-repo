"""Vercel / local entrypoint: the stateless research workbench (Scout + Challenger)."""
import os
import sys
from pathlib import Path

# Vercel imports this file by path from another working directory, so backend/ is not on
# sys.path by default. Put it first so `devils_advocate` and `pipeline` resolve.
BACKEND_DIR = str(Path(__file__).resolve().parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from devils_advocate.server import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=False, threaded=True)
