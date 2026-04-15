#!/bin/bash
# Reproducibility: download MiniMax + Zhipu IPO prospectuses from hkexnews.
set -euo pipefail

OUT_DIR="tests/fixtures/china_packs"
mkdir -p "$OUT_DIR/minimax_2024" "$OUT_DIR/zhipu_2024"

curl -fL --retry 3 --retry-delay 2 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)" \
  -o "$OUT_DIR/minimax_2024/source.pdf" \
  "https://www1.hkexnews.hk/listedco/listconews/sehk/2025/1231/2025123100025.pdf"

curl -fL --retry 3 --retry-delay 2 \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0)" \
  -o "$OUT_DIR/zhipu_2024/source.pdf" \
  "https://www1.hkexnews.hk/listedco/listconews/sehk/2025/1230/2025123000017.pdf"

echo "Downloaded:"
ls -lh "$OUT_DIR"/*/source.pdf
