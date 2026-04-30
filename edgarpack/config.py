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

# SEC rate limit: 10 requests per second by default. CI can opt into a more
# conservative lane because hosted runners share outbound IP pools.
RATE_LIMIT = _env_float("EDGARPACK_SEC_RATE_LIMIT", 10.0)

# Parser versioning for determinism tracking
PARSER_VERSION = "0.2.1"
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
