"""Configuration constants and paths for EdgarPack."""

import os
from pathlib import Path

# SEC requires every request to identify the caller in the format
# "Name email@example.com". No default is supplied: callers must set
# EDGARPACK_USER_AGENT before making any network calls. SECClient validates.
USER_AGENT = os.getenv("EDGARPACK_USER_AGENT", "")

# Cache location. User-level so it survives project moves.
CACHE_DIR = Path(os.getenv("EDGARPACK_CACHE_DIR", Path.home() / ".edgarpack" / "cache"))

# SEC rate limit: 10 requests per second
RATE_LIMIT = 10

# Parser versioning for determinism tracking
PARSER_VERSION = "0.1.0"
SCHEMA_VERSION = 1

# SEC API endpoints
SEC_DATA_BASE = "https://data.sec.gov"
SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

# HTTP client settings
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 60.0
MAX_RETRIES = 3

# Token counting model
TIKTOKEN_ENCODING = "cl100k_base"

# Chunking defaults
DEFAULT_CHUNK_MIN_TOKENS = 800
DEFAULT_CHUNK_MAX_TOKENS = 1200
