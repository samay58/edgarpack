#!/usr/bin/env bash
# sync-global.sh — push this vendored .learn-pack/ out to the universal skill homes
# so `learn-pack` is available for cold-start in any repo, in Claude Code and Codex.
#
# The in-repo .learn-pack/ is the source of truth. This overwrites the global copies.
# Run it from the in-repo copy after you improve the skill.
#
# Targets:
#   ~/.agents/skills/learn-pack/    canonical copy
#   ~/.claude/skills/learn-pack     symlink -> ../../.agents/skills/learn-pack
#   ~/.codex/skills/learn-pack/     copy (Codex loads real directories, not symlinks)
#   ~/.codex/prompts/learn-pack.md  stub: prefer a repo-local .learn-pack/, else the global copy
#
# Idempotent. Use --uninstall to remove all four.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the .learn-pack/ dir

AGENTS_DIR="${HOME}/.agents/skills/learn-pack"
CLAUDE_LINK="${HOME}/.claude/skills/learn-pack"
CODEX_SKILL="${HOME}/.codex/skills/learn-pack"
CODEX_PROMPT="${HOME}/.codex/prompts/learn-pack.md"

if [[ "${1:-}" == "--uninstall" ]]; then
  [[ -d "${AGENTS_DIR}" ]] && rm -rf "${AGENTS_DIR}" && echo "removed ${AGENTS_DIR}"
  [[ -L "${CLAUDE_LINK}" ]] && rm "${CLAUDE_LINK}" && echo "removed ${CLAUDE_LINK}"
  [[ -d "${CODEX_SKILL}" ]] && rm -rf "${CODEX_SKILL}" && echo "removed ${CODEX_SKILL}"
  [[ -f "${CODEX_PROMPT}" ]] && rm "${CODEX_PROMPT}" && echo "removed ${CODEX_PROMPT}"
  exit 0
fi

# Refuse to clobber a global dir that exists but is not a learn-pack copy.
guard() {
  local dir="$1"
  if [[ -e "${dir}/SKILL.md" ]] && ! grep -q "^name: learn-pack" "${dir}/SKILL.md"; then
    echo "error: ${dir} exists and is not a learn-pack copy. Aborting." >&2
    exit 1
  fi
}
guard "${AGENTS_DIR}"
guard "${CODEX_SKILL}"

mkdir -p "${AGENTS_DIR}" "${CODEX_SKILL}"
rsync -a --delete --exclude '.DS_Store' "${SRC}/" "${AGENTS_DIR}/"
rsync -a --delete --exclude '.DS_Store' "${SRC}/" "${CODEX_SKILL}/"
echo "copied: ${AGENTS_DIR}"
echo "copied: ${CODEX_SKILL}"

mkdir -p "$(dirname "${CLAUDE_LINK}")"
if [[ -L "${CLAUDE_LINK}" || -e "${CLAUDE_LINK}" ]]; then
  echo "exists: ${CLAUDE_LINK}"
else
  ln -s "../../.agents/skills/learn-pack" "${CLAUDE_LINK}"
  echo "linked: ${CLAUDE_LINK} -> ../../.agents/skills/learn-pack"
fi

mkdir -p "$(dirname "${CODEX_PROMPT}")"
cat > "${CODEX_PROMPT}" <<'EOF'
The learn-pack skill generates docs/learn/ for the current repo.

Find the playbook in this order:
1. a repo-local .learn-pack/ (a vendored copy in the host repo), or
2. ~/.agents/skills/learn-pack/ (the global cold-start copy).

Read and follow SKILL.md and PRINCIPLES.md from whichever you find first.

If docs/learn/manifest.yml does not exist, run Phase 1 (discovery) and produce the manifest. Stop after the manifest. Do not write trails or refs in the same turn.

If docs/learn/manifest.yml exists, run Phase 2 (fill) one item at a time, top to bottom. Wait for user review between items. Never batch.
EOF
echo "wrote:  ${CODEX_PROMPT}"

echo
echo "learn-pack synced. Available for cold-start in a new session."
