#!/bin/bash
set -euo pipefail

# EdgarPack daily refresh: harvest new filings + rebuild search index.
# Intended to run via launchd (see scripts/com.edgarpack.refresh.plist).

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${HOME}/.edgarpack/logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/refresh-$(date +%Y%m%d).log"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOGFILE"; }

cd "$PROJECT_DIR"

log "=== EdgarPack daily refresh ==="

# Harvest new filings (delta planner skips already-built)
log "Starting harvest..."
.venv/bin/edgarpack harvest \
    --universe universe.toml \
    --out ./packs \
    --refresh \
    --with-chunks 2>&1 | tee -a "$LOGFILE"

# Index only newly harvested packs
log "Starting incremental index..."
.venv/bin/edgarpack index --packs ./packs --incremental 2>&1 | tee -a "$LOGFILE"

log "=== Done ==="
