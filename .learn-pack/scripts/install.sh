#!/usr/bin/env bash
# install.sh — wire up the vendored .learn-pack/ to Claude Code and Codex CLI.
#
# What this does:
#   1. Symlinks .learn-pack/ into .claude/skills/learn-pack/ in the host repo.
#   2. Writes a stub at ~/.codex/prompts/learn-pack.md that points back here.
#   3. Appends a one-liner to AGENTS.md (or CLAUDE.md if AGENTS.md is absent)
#      so a fresh agent session sees the skill exists.
#
# Idempotent. Safe to re-run. Use --uninstall to undo.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LEARN_PACK_DIR="${REPO_ROOT}/.learn-pack"
PROJECT_NAME="$(basename "${REPO_ROOT}")"

if [[ ! -d "${LEARN_PACK_DIR}" ]]; then
  echo "error: ${LEARN_PACK_DIR} not found." >&2
  exit 1
fi

UNINSTALL=0
if [[ "${1:-}" == "--uninstall" ]]; then
  UNINSTALL=1
fi

CLAUDE_SKILLS_DIR="${REPO_ROOT}/.claude/skills"
CLAUDE_SKILL_LINK="${CLAUDE_SKILLS_DIR}/learn-pack"
CODEX_PROMPT_FILE="${HOME}/.codex/prompts/learn-pack.md"
AGENT_NOTE="Run \`/learn-pack\` (or invoke the learn-pack skill) to (re)generate docs/learn/. See .learn-pack/SKILL.md."

if [[ ${UNINSTALL} -eq 1 ]]; then
  echo "uninstalling learn-pack from ${PROJECT_NAME}..."
  [[ -L "${CLAUDE_SKILL_LINK}" ]] && rm "${CLAUDE_SKILL_LINK}" && echo "  removed: .claude/skills/learn-pack"
  [[ -f "${CODEX_PROMPT_FILE}" ]] && rm "${CODEX_PROMPT_FILE}" && echo "  removed: ~/.codex/prompts/learn-pack.md"
  echo "  note: not editing AGENTS.md / CLAUDE.md automatically. remove the learn-pack line by hand if you want."
  exit 0
fi

# 1. Claude Code: symlink into .claude/skills/
mkdir -p "${CLAUDE_SKILLS_DIR}"
if [[ -L "${CLAUDE_SKILL_LINK}" || -e "${CLAUDE_SKILL_LINK}" ]]; then
  echo "exists:  .claude/skills/learn-pack (skipped)"
else
  ln -s "../../.learn-pack" "${CLAUDE_SKILL_LINK}"
  echo "linked:  .claude/skills/learn-pack -> ../../.learn-pack"
fi

# 2. Codex CLI: stub prompt that points at the vendored playbook
mkdir -p "$(dirname "${CODEX_PROMPT_FILE}")"
if [[ -f "${CODEX_PROMPT_FILE}" ]]; then
  echo "exists:  ~/.codex/prompts/learn-pack.md (skipped — multiple repos may share this)"
else
  cat > "${CODEX_PROMPT_FILE}" <<EOF
The learn-pack skill is vendored inside the host repo at .learn-pack/.

Read and follow:
- .learn-pack/SKILL.md (the playbook)
- .learn-pack/PRINCIPLES.md (read before writing anything)

If .learn-pack/ does not exist in the current repo, this skill is not installed here. Tell the user.

If docs/learn/manifest.yml does not exist, run Phase 1 (discovery) and produce the manifest. Stop after the manifest. Do not write trails or refs in the same turn.

If docs/learn/manifest.yml exists, run Phase 2 (fill) one item at a time, top to bottom. Wait for user review between items. Never batch.
EOF
  echo "created: ~/.codex/prompts/learn-pack.md"
fi

# 3. AGENTS.md / CLAUDE.md note
NOTE_TARGET=""
if [[ -f "${REPO_ROOT}/AGENTS.md" ]]; then
  NOTE_TARGET="${REPO_ROOT}/AGENTS.md"
elif [[ -f "${REPO_ROOT}/CLAUDE.md" ]]; then
  NOTE_TARGET="${REPO_ROOT}/CLAUDE.md"
fi

if [[ -n "${NOTE_TARGET}" ]]; then
  if grep -q "learn-pack" "${NOTE_TARGET}"; then
    echo "exists:  $(basename "${NOTE_TARGET}") already mentions learn-pack (skipped)"
  else
    {
      echo ""
      echo "## learn-pack"
      echo ""
      echo "${AGENT_NOTE}"
    } >> "${NOTE_TARGET}"
    echo "appended: $(basename "${NOTE_TARGET}")"
  fi
else
  echo "note:    no AGENTS.md or CLAUDE.md found. skipping the agent-discovery hint."
fi

echo
echo "install complete. learn-pack is wired up for ${PROJECT_NAME}."
echo
echo "next:"
echo "  .learn-pack/scripts/scaffold.sh    # creates docs/learn/ skeleton"
echo "  then ask the agent to run discovery"
