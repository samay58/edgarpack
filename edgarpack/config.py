"""Configuration constants and paths for EdgarPack."""

import os
from pathlib import Path

# User-Agent must be declared per SEC requirements
# SEC requires format: "Company Name AdminContact@company.com"
# Override via EDGARPACK_USER_AGENT environment variable
USER_AGENT = os.getenv(
    "EDGARPACK_USER_AGENT",
    "EdgarPack admin@edgarpack.dev"
)

# Cache location - user-level, survives project moves
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
