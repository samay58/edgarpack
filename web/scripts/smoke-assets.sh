#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:3000}"
ROUTES="/cmp_tencent_0700/overview /cmp_tencent_0700/packs /cmp_tencent_0700/evidence"
all_assets_tmp="$(mktemp)"

for route in $ROUTES; do
  html="$(curl -fsSL "${BASE_URL}${route}")"
  route_assets="$(
    printf "%s" "$html" \
      | rg -o 'href="/_next/static/[^"]+"|src="/_next/static/[^"]+"' \
      | sed -E 's/^(href|src)="([^"]+)"$/\2/' \
      | sort -u
  )"

  if [[ -z "$route_assets" ]]; then
    echo "No Next static assets found for route: ${route}" >&2
    rm -f "$all_assets_tmp"
    exit 1
  fi

  printf "%s\n" "$route_assets" >> "$all_assets_tmp"
done

unique_assets_tmp="$(mktemp)"
sort -u "$all_assets_tmp" > "$unique_assets_tmp"

while IFS= read -r asset; do
  [[ -z "$asset" ]] && continue
  code="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${asset}")"
  if (( code >= 400 )); then
    echo "Asset failed: ${asset} returned ${code}" >&2
    rm -f "$all_assets_tmp" "$unique_assets_tmp"
    exit 1
  fi
done < "$unique_assets_tmp"

route_count="$(printf "%s\n" $ROUTES | wc -l | tr -d '[:space:]')"
asset_count="$(wc -l < "$unique_assets_tmp" | tr -d '[:space:]')"
echo "OK: verified ${route_count} routes and ${asset_count} Next static assets at ${BASE_URL}"
rm -f "$all_assets_tmp" "$unique_assets_tmp"
