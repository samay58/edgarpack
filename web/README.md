# EdgarPack Web

A Next.js frontend over the EdgarPack packs and the Filing Observatory API. Two workspaces in one shell:

- **China Lens**: pack viewer with citation pills, evidence explorer, and a bounded ask panel.
- **Filing Observatory**: company grid, side-by-side 10-K diff, single-section timeline across filings, and cross-corpus search.

## Run

```bash
cd web
npm install
npm run dev
```

Open http://localhost:3000. The app talks to the FastAPI backend at `http://127.0.0.1:8000/api/v1` by default. Point it elsewhere via:

```bash
export NEXT_PUBLIC_OBSERVATORY_API_BASE="http://127.0.0.1:8000/api/v1/observatory"
```

Start the backend with `edgarpack api --port 8000`. If the API isn't up, the China Lens side falls back to deterministic fixture data for UI iteration; the Observatory side shows an actionable error.

## Observatory endpoints the UI consumes

- `GET /observatory/companies`
- `GET /observatory/companies/{ticker}`
- `GET /observatory/companies/{ticker}/diff?detail=sections|full&section_types=...`
- `GET /observatory/companies/{ticker}/timeline/{section_id}`
- `GET /observatory/search`
- `GET /observatory/stats`, `/observatory/topics`

## Smoke check

```bash
npm run smoke:assets
# OK: verified 3 routes and <N> Next static assets at http://localhost:3000
```

## Build

```bash
npm run lint
npm run build
```

## Unstyled page

Stale `.next` artifacts are the usual cause. Nuke and restart:

```bash
rm -rf .next
npm run dev
```

Then hard-refresh (`Cmd+Shift+R`).
