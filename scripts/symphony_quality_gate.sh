#!/usr/bin/env bash
set -euo pipefail

cache_dir="${EDGARPACK_CACHE_DIR:-/tmp/edgarpack-symphony-cache-$$}"
export EDGARPACK_CACHE_DIR="$cache_dir"

echo "Using EDGARPACK_CACHE_DIR=$EDGARPACK_CACHE_DIR"

uv run --extra dev --extra china --extra sse ruff check .
uv run --extra dev --extra china --extra sse pytest -q

if [[ "${SYMPHONY_CHINA_GOLDEN:-0}" == "1" ]]; then
  uv run --extra dev --extra china --extra sse pytest \
    tests/test_china_query_hk.py \
    tests/test_china_query_eval.py \
    tests/test_citation_registry.py \
    -q
fi
