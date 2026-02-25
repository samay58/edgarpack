# Rogo China Lens Web Shell

This Next.js app provides the interactive workspace shell for:
- command palette navigation (`Cmd+K`)
- pack view rendering with citation pills
- evidence explorer layout
- bounded ask panel UX
- filing observatory views (company grid, diff viewer, timeline, cross-corpus search)

## Run

```bash
cd web
npm install
npm run dev:clean
```

Set `NEXT_PUBLIC_CHINA_LENS_API_BASE` to point at FastAPI:

```bash
export NEXT_PUBLIC_CHINA_LENS_API_BASE="http://127.0.0.1:8000/api/v1"
```

If the API is unavailable, the app falls back to deterministic fixture data for local UI iteration.

## Observatory Endpoints Used By The UI

- `GET /observatory/companies`
- `GET /observatory/companies/{ticker}`
- `GET /observatory/companies/{ticker}/diff?detail=sections|full&section_types=...`
- `GET /observatory/companies/{ticker}/timeline/{section_id}`
- `GET /observatory/search`

## Test (quick smoke)

Start the frontend first, then run:

```bash
cd web
npm run smoke:assets
```

Expected output:

```text
OK: verified 3 routes and <N> Next static assets at http://localhost:3000
```

## Troubleshooting: page looks unstyled

If the page renders as plain HTML, stale `.next` artifacts are usually the cause.

```bash
cd web
rm -rf .next
npm run dev:clean
```

Then hard-refresh the browser (`Cmd+Shift+R` on macOS).
