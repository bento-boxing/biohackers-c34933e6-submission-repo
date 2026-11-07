from pathlib import Path

import pytest

DEMO_CACHE = Path(__file__).parent.parent / "data" / "demo_cache"


@pytest.fixture
def client():
    from pipeline.http import HttpClient

    return HttpClient(read_dirs=[DEMO_CACHE], cache_only=True)
