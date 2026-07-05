"""Configuration constants and paths for EdgarPack."""

import os
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


# SEC requires every request to identify the caller in the format
# "Name email@example.com". No default is supplied: callers must set
# EDGARPACK_USER_AGENT before making any network calls. SECClient validates.
USER_AGENT = os.getenv("EDGARPACK_USER_AGENT", "")

# Cache location. User-level so it survives project moves.
CACHE_DIR = Path(os.getenv("EDGARPACK_CACHE_DIR", Path.home() / ".edgarpack" / "cache"))

# Canonical on-disk output locations. Path('packs') == Path('./packs')
# (pathlib strips the leading './'), so these unify the spellings that were
# scattered as argparse defaults without changing any behavior.
DEFAULT_PACKS_DIR = Path("packs")
DEFAULT_SITE_DIR = Path("site")
DEFAULT_REPORTS_DIR = Path("reports")

# SEC fair-access limit is 10 requests/second. EdgarPack defaults below that
# ceiling so local builds have headroom for browser/user activity sharing the
# same outbound IP. Override with care via EDGARPACK_SEC_RATE_LIMIT.
RATE_LIMIT = _env_float("EDGARPACK_SEC_RATE_LIMIT", 5.0)

# Parser versioning for determinism tracking
PARSER_VERSION = "0.2.3"
SCHEMA_VERSION = 1

# SEC API endpoints
SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# HTTP client settings
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60.0
MAX_RETRIES = _env_int("EDGARPACK_SEC_MAX_RETRIES", 3)

# Token counting model
TIKTOKEN_ENCODING = "cl100k_base"

# Chunking defaults
DEFAULT_CHUNK_MIN_TOKENS = 800
DEFAULT_CHUNK_MAX_TOKENS = 1200
