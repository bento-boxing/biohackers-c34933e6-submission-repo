"""Non-secret process/source provenance; historic reports are never rewritten."""
from pathlib import Path
import hashlib
import time

PIPELINE_VERSION='association-pathways-v1'

def source_hash() -> str:
    digest=hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        digest.update(path.name.encode());digest.update(path.read_bytes())
    return digest.hexdigest()[:20]

LOADED_HASH=source_hash()
LOADED_AT=time.time()

def runtime_info() -> dict:
    disk=source_hash()
    return {'pipeline_version':PIPELINE_VERSION,'source_hash':LOADED_HASH,'disk_source_hash':disk,
            'code_matches_disk':disk==LOADED_HASH,'process_loaded_at':LOADED_AT}
