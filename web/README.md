# Rogo China Lens Web Shell

This Next.js app provides the interactive workspace shell for:
- command palette navigation (`Cmd+K`)
- pack view rendering with citation pills
- evidence explorer layout
- bounded ask panel UX

## Run

```bash
cd web
npm install
npm run dev
```

Set `NEXT_PUBLIC_CHINA_LENS_API_BASE` to point at FastAPI:

```bash
export NEXT_PUBLIC_CHINA_LENS_API_BASE="http://127.0.0.1:8000/api/v1"
```

If the API is unavailable, the app falls back to deterministic fixture data for local UI iteration.
