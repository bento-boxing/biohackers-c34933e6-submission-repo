"""Where the backend may write. Vercel Functions only allow writes under /tmp."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
VERCEL_DATA_ROOT = Path("/tmp/target-scout")


def data_dir(name: str) -> Path:
    """Writable directory for `name` ("cache", "runs").

    SCOUT_DATA_DIR overrides everything; on Vercel (VERCEL=1) use /tmp, which is
    per-instance and wiped when the instance is recycled; locally use backend/<name>.
    """
    if os.environ.get("SCOUT_DATA_DIR"):
        return Path(os.environ["SCOUT_DATA_DIR"]) / name
    if os.environ.get("VERCEL") == "1":
        return VERCEL_DATA_ROOT / name
    return BACKEND_DIR / name
