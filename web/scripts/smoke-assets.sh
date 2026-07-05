#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:3000}"
ROUTES="/observatory"
all_assets_tmp="$(mktemp)"
unique_assets_tmp="$(mktemp)"

cleanup() {
  rm -f "$all_assets_tmp" "$unique_assets_tmp"
}
trap cleanup EXIT

if ! curl -fsS -o /dev/null "$BASE_URL"; then
  echo "Next app is not reachable at ${BASE_URL}. Start it with \`npm --prefix web run dev\` or set BASE_URL." >&2
  exit 1
fi

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
    exit 1
  fi

  printf "%s\n" "$route_assets" >> "$all_assets_tmp"
done

sort -u "$all_assets_tmp" > "$unique_assets_tmp"

while IFS= read -r asset; do
  [[ -z "$asset" ]] && continue
  code="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}${asset}")"
  if (( code >= 400 )); then
    echo "Asset failed: ${asset} returned ${code}" >&2
    exit 1
  fi
done < "$unique_assets_tmp"

route_count="$(printf "%s\n" $ROUTES | wc -l | tr -d '[:space:]')"
asset_count="$(wc -l < "$unique_assets_tmp" | tr -d '[:space:]')"
echo "OK: verified ${route_count} routes and ${asset_count} Next static assets at ${BASE_URL}"
