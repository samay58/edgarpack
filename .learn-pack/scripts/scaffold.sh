#!/usr/bin/env bash
# scaffold.sh — create docs/learn/ skeleton in the host repo.
# Works whether the skill is vendored (.learn-pack/) or installed globally.
# Idempotent. Safe to re-run. Never overwrites existing files.

set -euo pipefail

# Templates live next to this script, in ../templates, wherever the skill lives.
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="${SKILL_DIR}/templates"

# The host repo is the current git repo, or the current directory if it is not one.
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DOCS_LEARN="${REPO_ROOT}/docs/learn"

if [[ ! -f "${TEMPLATES}/manifest.yml.tmpl" ]]; then
  echo "error: templates not found at ${TEMPLATES}. is the skill install intact?" >&2
  exit 1
fi

mkdir -p "${DOCS_LEARN}/ref"

# Manifest stub. Only created if missing.
if [[ ! -f "${DOCS_LEARN}/manifest.yml" ]]; then
  PROJECT_NAME="$(basename "${REPO_ROOT}")"
  DATE="$(date +%Y-%m-%d)"
  sed \
    -e "s/{{PROJECT_NAME}}/${PROJECT_NAME}/g" \
    -e "s/{{DATE}}/${DATE}/g" \
    "${TEMPLATES}/manifest.yml.tmpl" \
    > "${DOCS_LEARN}/manifest.yml"
  echo "created: docs/learn/manifest.yml"
else
  echo "exists:  docs/learn/manifest.yml (skipped)"
fi

# README placeholder. Only created if missing. Filled in during Phase 2.
if [[ ! -f "${DOCS_LEARN}/README.md" ]]; then
  cat > "${DOCS_LEARN}/README.md" <<'EOF'
# Learn (placeholder)

This file will be replaced during Phase 2 of the learn-pack workflow.
The manifest in this directory is the input for that phase.
EOF
  echo "created: docs/learn/README.md (placeholder)"
else
  echo "exists:  docs/learn/README.md (skipped)"
fi

echo
echo "scaffold complete. next:"
echo "  1. tell the agent: 'run learn-pack discovery on this repo'"
echo "  2. agent fills docs/learn/manifest.yml"
echo "  3. you review the manifest"
echo "  4. agent fills trails and refs one at a time"
