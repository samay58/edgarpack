# Codex Handoff: Smoke Test Round 2 Bug Fixes

## Context

EdgarPack is a query layer over SEC EDGAR XBRL data. Handspread is a downstream comps engine that uses edgarpack for fundamentals and Finnhub for market data. A 20-company live smoke test on 2026-02-16 surfaced 6 bugs across both repos. Three are in edgarpack's period selection logic (`query/periods.py`), two are in handspread's growth/market modules, one is in handspread's EPS resolution.

Repos:
- `~/Projects/active/edgarpack` (edgarpack)
- `~/Projects/active/handspread` (handspread)

Run tests with:
```bash
cd ~/Projects/active/edgarpack && python3 -m unittest discover -s tests
cd ~/Projects/active/handspread && .venv/bin/python -m pytest tests/ -x -v
```

Lint:
```bash
cd ~/Projects/active/edgarpack && ruff check . && ruff format --check .
cd ~/Projects/active/handspread && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .
```

Open beads issues track each bug. Run `bd list --status=open` in each repo to see them.

---

## Bug 1 (P1): GOOGL LTM-1 Revenue +100.4% (should be ~14%)

**Issue**: `edgarpack-1pk`
**File**: `edgarpack/query/periods.py`, lines 372-380
**Symptom**: GOOGL shows +100.4% revenue YoY. The LTM-1 value is ~$175B instead of ~$307B.

**Root cause**: The Q4/FY early-return optimization at line 372 fires for all `years_back` values, not just `years_back=0`. When `years_back=1` (LTM-1), the code finds the current-year Q4 entry (which matches "Q4 is basically the full year"), and returns the current FY annual value instead of the prior-year annual value.

```python
# Line 372-380 - the early return fires unconditionally
if _is_q4_entry(mrp_entry, lfy_entries):
    for e in lfy_entries:
        if (e.get("fp", "").upper() == "FY" ...):
            return _make_cited(e, ...)  # Returns current FY, not prior FY
```

**Fix**: Guard the Q4/FY early-return so it only fires when `years_back == 0`. When `years_back > 0`, the code should fall through to the normal LTM formula which correctly offsets by year.

**Verification**: After fixing, GOOGL revenue growth should be ~14% (LTM ~$350B, LTM-1 ~$307B). Add a test case in `tests/test_periods.py` that constructs a companyfacts blob with 2 years of quarterly data and verifies LTM-1 returns the prior year's value, not the current year's.

---

## Bug 2 (P1): HMC Revenue Growth +282.4% (annual-only stub periods)

**Issue**: `edgarpack-eux`
**File**: `edgarpack/query/periods.py`, lines 320-347
**Symptom**: HMC (Honda, March FY, 20-F annual-only filer) shows +282.4% revenue YoY.

**Root cause**: The annual-only fallback path (lines 320-347) doesn't validate period duration. For `years_back=1`, it finds entries with `fy = max_fy - 1` but doesn't check whether those entries cover a full fiscal year. HMC's companyfacts contains stub/transition period entries (e.g., a 3-month transitional period) that have the correct `fy` tag but cover only a fraction of the year. The code picks one of these short periods as LTM-1, producing a value ~4x too small.

**Fix**: In the annual-only fallback, after selecting entries with the target `fy`, validate that the selected entry's period duration is at least 300 days (a full fiscal year is ~365 days). If all entries for that `fy` are shorter than 300 days, return None instead of a misleadingly small value. You can compute duration from the `start` and `end` date strings in the entry.

**Verification**: HMC revenue growth should be a reasonable number (single-digit %) or None if prior year data is genuinely unavailable. Add a test with mock companyfacts containing a 90-day stub period alongside a full-year period for the same `fy`. Verify the stub is skipped and the full-year entry is selected.

---

## Bug 3 (P1): EPD EPS -46.4% vs Net Income -1.1% (per-share LTM additivity)

**Issue**: `edgarpack-joc`
**File**: `edgarpack/query/periods.py`, line 423 (LTM formula)
**Also**: `edgarpack/query/concepts.py`, lines 74-83 (eps_basic, eps_diluted config)
**Symptom**: EPD (Enterprise Products Partners) shows EPS growth of -46.4% while net income growth is -1.1%. The EPS values themselves are wrong because the LTM formula sums per-share values.

**Root cause**: The LTM formula `ltm_val = mrp_val + lfy_val - prior_val` works for extensive quantities (revenue, net income, cash flow) but not for intensive/ratio quantities (EPS, dividends per share). EPS is not additive across periods. Q1 EPS + Q2 EPS != H1 EPS because the denominator (diluted share count) differs each quarter.

Both `eps_basic` and `eps_diluted` have `duration=True` in `concepts.py`, which correctly marks them as period metrics. But the LTM construction code treats all period metrics as additive.

**Fix options** (pick one):
1. **Add a `per_share: bool` flag to MetricMeta** and skip LTM construction for per-share metrics, returning only the LFY (latest fiscal year) value instead. This is the cleanest approach since per-share LTM is fundamentally undefined from XBRL data alone (you'd need the exact weighted average share count for the trailing 12-month window).
2. **Return None for LTM on per-share metrics** with a warning explaining that per-share LTM requires consistent denominators. Mark `eps_basic`, `eps_diluted`, and `dividends_per_share` as non-LTM-able.

The same fix should apply to `dividends_per_share`.

**Verification**: After fixing, EPD's `eps_diluted` for LTM period should either return the LFY value or None with a warning. It should not return a summed value. Add a test that constructs mock data with varying per-share values across quarters and verifies LTM doesn't naively sum them.

---

## Bug 4 (P1): ADR Share Count Inflation (TSM $9.5T, BABA, PBR, HMC)

**Issue**: `hs-jzc`
**File**: `handspread/market/finnhub_client.py`
**Symptom**: TSM computed market cap is $9.5T (should be ~$950B). BABA, PBR, HMC also have inflated computed values, though their vendor market cap values are correct.

**Root cause**: Finnhub's `shareOutstanding` field returns the full ordinary share count for foreign companies, not the ADR-equivalent count. TSM has 25.93B ordinary shares. At the $366 ADR price, computed mcap = $9.5T. The real mcap is ~$950B because each ADR represents 5 ordinary shares.

The vendor `marketCapitalization` field is correct for most tickers (already fixed with currency cross-check), but the computed fallback path (price * shares) remains inflated for ADRs.

**Fix**: Detect ADR inflation by comparing vendor mcap to computed mcap. When vendor mcap is available and valid, derive an implied share count: `implied_shares = vendor_mcap / price`. If this differs significantly from `shareOutstanding`, attach a warning to the shares_outstanding MarketValue noting the ADR ratio discrepancy.

For the computed mcap fallback (when vendor is unavailable or rejected), consider using the implied ADR-adjusted share count when the ratio exceeds a threshold (e.g., 3x).

This is a data quality issue, not a code bug per se. The fix is about adding warnings and potentially adjusting the fallback computation. Don't over-engineer. A warning is the minimum viable fix.

**Verification**: TSM should either show ~$950B (vendor mcap) or carry a clear warning about ADR share inflation on the computed value. The currency cross-check already handles the TSM vendor mcap case (falls back to computed because TWD). The deeper fix is making the computed fallback less wrong.

---

## Bug 5 (P2): Split Divergence False Positives (DDOG, PBR, HMC)

**Issue**: `hs-z8i`
**File**: `handspread/analysis/growth.py`
**Symptom**: DDOG, PBR, HMC all have EPS growth nulled out with "stock split contamination" warnings, but none of these companies had recent stock splits.

**Root cause**: The split detection heuristic compares revenue growth (positive) against EPS growth (negative). If revenue growth > +20% and EPS growth < -20%, it flags the EPS as split-contaminated. But this fires for legitimate scenarios:
- DDOG: Revenue +26.3%, EPS -24.1% (real, driven by increased SBC and investment)
- PBR: Revenue +22.1%, EPS -58.2% (real, driven by commodity price swings and FX)
- HMC: Revenue growth inflated by Bug 2, making the divergence look worse

**Fix**: Tighten the heuristic. Options:
1. **Widen the threshold**: Change from (rev > +20% and eps < -20%) to (rev > +40% and eps < -60%). This would catch a 10:1 split (NVDA case: rev +65%, eps -90%) but not normal operating divergence.
2. **Use magnitude ratio**: Instead of absolute thresholds, check if `abs(eps_growth / rev_growth) > 3`. A 10:1 split would show rev +65% and eps -90%, ratio = 1.4, which might not trigger. Reconsider.
3. **Check the underlying data for split markers**: The edgarpack CitedValue warnings already carry a split flag when the LTM-derived value differs from LFY by > 5x. Only null EPS growth when the *source data* carries a split warning, not based on growth divergence. This is the most principled approach.

Option 3 is preferred. The split divergence check was added as a backup, but it creates false positives. The edgarpack-level split detection (already implemented) is more reliable because it looks at the actual per-share values, not derived growth rates.

**Verification**: After fixing, DDOG, PBR, HMC should show their actual EPS growth rates (even if ugly). NVDA should still be caught by the edgarpack-level split warning.

---

## Bug 6 (P3): BRK-B EPS Dual-Class Resolution

**Issue**: `hs-7q3`
**File**: `edgarpack/query/concepts.py` (eps concepts), `edgarpack/query/periods.py` (value selection)
**Symptom**: BRK-B shows EPS of $68,396 (Class A EPS) instead of ~$45.56 (Class B, which is 1/1500th of Class A).

**Root cause**: The `EarningsPerShareDiluted` XBRL concept doesn't distinguish between share classes. For Berkshire, the SEC filing contains both Class A and Class B EPS values under the same concept tag, differentiated by XBRL dimensions (member tags). EdgarPack's concept resolution picks the first/highest value, which is Class A.

**Fix**: This is hard to fix generically because XBRL dimensional data is complex. Pragmatic options:
1. **Ticker-aware override**: If the queried ticker is "BRK-B", prefer the Class B EPS entry. This is hacky but correct for the most prominent dual-class case.
2. **Dimensional filtering**: Parse the XBRL dimensions on EPS entries and prefer the entry tagged with CommonClassB or similar member. This is more general but requires understanding XBRL dimensional taxonomy.
3. **Accept the limitation**: Add a warning when multiple EPS values exist for the same period, noting that dual-class companies may report per-class EPS. Let the downstream consumer decide.

Option 3 is the minimum viable fix. Option 2 is ideal if the XBRL dimensional data is accessible in the companyfacts JSON.

**Verification**: BRK-B EPS should either show Class B EPS (~$45.56) or carry a warning about dual-class ambiguity. Check what the SEC companyfacts JSON actually contains for BRK (CIK 0001067983) to determine which fix is feasible.

---

## Priority Order

1. **Bug 1** (GOOGL): Quick fix, high impact, clear root cause. Guard the early-return with `years_back == 0`.
2. **Bug 2** (HMC): Medium fix, validate period duration in annual-only path.
3. **Bug 3** (EPD): Design decision needed on per-share LTM handling. Add `per_share` flag or return None.
4. **Bug 5** (split false positives): Remove the growth-divergence heuristic, rely on edgarpack-level split detection.
5. **Bug 4** (ADR shares): Warning-only fix in handspread. Lower urgency because vendor mcap is correct for most ADRs.
6. **Bug 6** (BRK-B): Accept limitation with warning. Lowest priority.

## After Fixing

1. Run all tests in both repos
2. Run lint in both repos
3. Close the beads issues: `bd close edgarpack-1pk edgarpack-eux edgarpack-joc` and `bd close hs-z8i hs-jzc hs-7q3`
4. `bd sync` in both repos
5. Commit and push both repos
