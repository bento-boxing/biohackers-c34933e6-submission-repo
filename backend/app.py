"""Vercel / local entrypoint: the stateless research workbench (Scout + Challenger)."""
import os

from dotenv import load_dotenv

load_dotenv()
from devils_advocate.server import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5050")), debug=False, threaded=True)
