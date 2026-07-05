# Packet: dual-listing-adr

Goal: one company, many listings, one resolution. "BABA", "9988.HK", "Alibaba", and CIK 1577552 resolve to the same entry; the American investor types the name or ADR ticker they know and lands on the right filings, with plain-language disambiguation of the venues.

Files owned: `edgarpack/identity.py`, `universe.toml` (the three pilot entries below only; the bulk universe belongs to starter-universe), `edgarpack/cli.py` (the `identify` output block, a new `--venue` flag on the query parser, and a venue pre-pass at the TOP of `_cmd_query`; the China build-if-needed block belongs to one-command-china), tests.

## Pre-made design decisions

- No new schema mechanism. `ResolvedCompany` (identity.py:48) already carries `cik`, `hk_stock_code`, and `stock_code` simultaneously; a dual-listed company is ONE `[[companies]]` block populating any subset of the three, with `listing` naming the DEFAULT venue ("SEC" | "HKEX" | "SSE"), ADR/other-venue symbols in `alt_tickers`, and names in `aliases`. Verify the universe loader actually preserves coexisting identifiers into one ResolvedCompany (it may currently treat them as exclusive; fix the loader if so).
- Venue selection: default venue = the entry's `listing`. New `--venue {sec,hkex,sse}` flag on `query` overrides. Requesting a venue whose identifier is absent raises a typed error that TEACHES: list every populated venue with its identifier and a one-line note, e.g. `BYD does not file with the SEC. Available: sse (002594, CNINFO annual reports), hkex (01211, HKEX filings).` The routing decision happens in the `_cmd_query` pre-pass: resolve the entry, apply the venue, and hand the downstream pipeline a ResolvedCompany carrying only the chosen venue's identity (so `financials()` needs no changes).
- `identify` output for multi-listing entries gains a Listings section, one line per populated venue, default marked: `Listings: SEC 20-F (CIK 1577552, ADR: BABA) [default] | HKEX 09988`. Single-listing entries keep today's output byte-identical (tests pin several).
- Pilot entries (add to universe.toml; VERIFY every identifier before committing and cite the verification source in the commit body; a live SEC ticker-map or HKEX/CNINFO check is acceptable, and if a code below is wrong, the spec is wrong and your verified value wins):
  1. Alibaba: cik 1577552, hk_stock_code 09988, listing SEC, alt_tickers BABA + 9988.HK, aliases alibaba / alibaba group.
  2. JD.com: cik 1549802, hk_stock_code 09618, listing SEC, alt_tickers JD + 9618.HK.
  3. BYD: stock_code 002594, hk_stock_code 01211, listing SSE, alt_tickers 1211.HK + BYDDY. BYD has NO SEC reporting (its US ADR is OTC): this entry is the deliberate test of the teaching error above.
- Resolution precedence is unchanged (ticker, then alt_tickers, then aliases); ADR symbols are plain alt_tickers, no special casing.
- `comps`/`compare` venue support is OUT of scope; note in your report what they would need.

## Tests

- Loader: one entry with cik + hk_stock_code + stock_code loads into one ResolvedCompany with all three populated.
- Resolution: BABA, 9988.HK, "alibaba", and 1577552 all reach the Alibaba entry.
- Venue routing: `--venue hkex` on Alibaba yields an HKEX-routed company; `--venue sec` on BYD raises the teaching error with both available venues named.
- Default venue: Alibaba without `--venue` routes SEC; BYD routes SSE.
- identify: multi-listing block renders; a single-listing filer's output is unchanged.

## Done definition

All tests green; pilot identifiers verified with sources cited in the commit body; full offline suite green.
