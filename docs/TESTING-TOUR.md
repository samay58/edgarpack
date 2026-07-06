# Testing tour

A hands-on ladder from trivial to advanced that exercises the full surface of EdgarPack. Every command below was verified working on `main`. Run from the repo root.

## One-time setup

```bash
export EDGARPACK_USER_AGENT="Your Name you@example.com"   # required for live SEC calls
```

China / HK commands need the extra deps, so those lines carry `--extra china --extra sse`. Registration LLM extraction (level 8) also needs `ANTHROPIC_API_KEY` and `--extra llm`.

## The ladder

### 1. Is it alive (offline, instant)
```bash
uv run edgarpack identify BYDDY
```
Resolves the OTC ADR ticker to BYD and prints its `Listings:` block (SSE default, HKEX secondary). Try `identify BABA` too.

### 2. One cited SEC number
```bash
uv run edgarpack query NVDA revenue --period lfy
```
A single value with its exact filing URL. The whole product in one line: the number carries its provenance.

### 3. Period vocabulary + derived metrics + the audit trail
```bash
uv run edgarpack query NVDA revenue,net_income,gross_margin --period ltm --audit
```
LTM is computed, not filed. `--audit` shows the real derivation: `revenue` as `mrp + lfy - mrp_prior` with each component cited, and `gross_margin` as `gross_profit / revenue`. Swap `--period annual:3` for a three-year grid.

### 4. Cross-company comps
```bash
uv run edgarpack comps NVDA AMD INTC --metrics revenue,gross_margin --period lfy
uv run edgarpack compare NVDA AMD --metrics revenue --format markdown
```
`compare` flags when fiscal years differ.

### 5. The China wedge, cold start (~2-4 min first time; it builds the pack from CNINFO)
```bash
uv run --extra china --extra sse edgarpack query BYD revenue,net_income --period lfy --currency both
```
No pre-built pack needed. Returns USD and native CNY, cited to the FY2025 annual report, with the Chinese label alongside the English one and a "this is the A-share equivalent of a 10-K" line. Re-run it and it is instant (warm pack).

### 6. Dual-listing and the teaching error
```bash
uv run --extra china --extra sse edgarpack query BABA revenue --venue hkex   # auto-builds Alibaba's HK pack
uv run --extra china --extra sse edgarpack query BYD revenue --venue sec      # BYD does not file with the SEC
```
The second command is the point: instead of a blank failure, it teaches which venues do exist (`sse (002594...)`, `hkex (01211...)`).

### 7. Build an HK pack for any issuer, then query it
```bash
uv run --extra china --extra sse edgarpack build-hk 0700
uv run --extra china --extra sse edgarpack query 0700.HK net_income --period lfy --currency both
```
`build-hk` pulls Tencent's English annual report straight from HKEX and reads its currency / accounting standard from the filing itself. A cold `query 0700.HK` also auto-builds the pack for you. **Input-form note:** use `0700.HK` or `tencent`, not a bare `0700` (a bare 4-digit code is read as a SEC CIK).

### 8. Pre-IPO registration (needs `ANTHROPIC_API_KEY` + `--extra llm`)
```bash
ANTHROPIC_API_KEY=... uv run --extra china --extra sse --extra llm \
  edgarpack f1 0002004711 --period pro-forma
```
Builds the registration pack if needed and extracts cited financials from a filing that has no SEC companyfacts. Without the key it returns honest `no_api_key` placeholders rather than guesses.

### 9. Cross-market, side by side
```bash
uv run --extra china --extra sse edgarpack query BYD revenue --currency usd
uv run edgarpack query TSLA revenue --period lfy
```
Compare a Chinese A-share filer against a US filer in the same currency, both cited. (A single `comps` across markets is the natural next step but not wired yet: comps does not auto-build China packs and venue routing there is a follow-up.)

## Fastest confidence check

If you want one command that proves the whole China thesis in a single shot, it is **level 5** (`query BYD`): cold-start acquisition, correct value, USD + native, bilingual, cited. That is the same filer that returned a cited ¥80.00 before the July 2026 streamline and now returns ¥804.0 billion.

## Known fail-closed limitations (not bugs)

- HK packs built via `build-hk` carry no period dates when the filing does not state a fiscal-year-end (no fabrication).
- Some issuers fail closed on extraction: Tencent revenue (an unlabeled note-reference row), garbled subsetted-font filings (HSBC-class, a typed error, OCR is a deferred follow-up), and designed-layout A-share filers with no numbered headings (Ping An, Zijin). These show N/A, never a wrong number.
