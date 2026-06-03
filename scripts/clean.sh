#!/usr/bin/env bash
set -euo pipefail

# Remove regenerable clutter so the working tree stays tight.
#   scripts/clean.sh           tidy: caches, build output, stray test dirs, __pycache__
#   scripts/clean.sh --corpus  also wipe the local packs/ and site/ corpus
#
# Everything removed here is gitignored and rebuilt on demand. Source, tests,
# docs, and your research in reports/ are never touched.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

before="$(du -sh "$ROOT" 2>/dev/null | cut -f1)"

tidy=(
  .mypy_cache .ruff_cache .pytest_cache
  dist build
  test-packs test-site test_packs site_test
  edgarpack.egg-info
)
for d in "${tidy[@]}"; do
  if [ -e "$ROOT/$d" ]; then
    echo "removing $d"
    rm -rf "${ROOT:?}/$d"
  fi
done

# Python bytecode under the source trees only (never .venv / .git).
find "$ROOT/edgarpack" "$ROOT/tests" "$ROOT/scripts" \
  -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

if [ "${1:-}" = "--corpus" ]; then
  for d in packs site; do
    if [ -e "$ROOT/$d" ]; then
      echo "removing $d (regenerable corpus)"
      rm -rf "${ROOT:?}/$d"
    fi
  done
fi

after="$(du -sh "$ROOT" 2>/dev/null | cut -f1)"
echo "clean done. repo size: ${before} -> ${after}"
