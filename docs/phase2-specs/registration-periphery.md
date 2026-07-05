# Packet: registration-periphery

Goal: the `f1`/`s1` shortcuts stop being blind to amendments, and pre-IPO queries stop re-hitting SEC's 404 endpoint on every call.

Files owned: `edgarpack/sec/submissions.py`, `edgarpack/sec/xbrl.py`, `edgarpack/sec/cache.py` (only if the negative cache needs it), `edgarpack/query/s1_financials.py` ONLY the `has_registration_pack_for_cik` helper (~1219-1231; the rest of that file is owned by the s1-core packet: touch nothing else in it), `edgarpack/cli.py` only the registration shortcut filing-selection block (~1628-1636), tests.
Interface contract: expose a `matches_registration_family(form_type: str, base: str) -> bool` helper in `submissions.py` (F-1 matches F-1 and F-1/A; S-1 matches S-1 and S-1/A; exact accession pinning bypasses it). Both your call sites and any future caller use it; document it with a docstring stating the family rule.

## Fixes

1. `amendments`. Three blind spots make `edgarpack f1 X` anchor on the original filing forever:
   - `get_latest_filing` (`submissions.py` ~257) matches `normalize_form_type(form) == target`, so F-1/A never matches a target of F-1.
   - It scans only the `filings.recent` window with no pagination (unlike `get_filing_by_accession`); a filer with many later filings can page the F-1 family out of `recent`.
   - `has_registration_pack_for_cik` normalizes F-1/A to F-1/A, which never equals F-1, so an existing amendment pack fails the exists-check and triggers a redundant original-F-1 build.
   Fix all three: "latest F-1" means the newest of {F-1, F-1/A} by filing date (tie: accession), selection paginates past `filings.recent` when the family is not found there, the exists-check accepts family members, and the shortcut's build step (`cli.py` ~1628-1636) builds the selected (possibly amended) filing. `--accession` pinning keeps working unchanged. Tests: a submissions fixture where the newest family member is an F-1/A on page two of the filing history.

2. `negative-404-cache`. Pre-IPO filers with no companyfacts re-hit SEC with a fresh 404 every query (`xbrl.py` ~72-73). Cache the 404-means-no-XBRL result with a 1-day TTL. HARD CONSTRAINT (the repo's no-silent-imputation boundary): a cached negative behaves exactly like a fresh 404 (returns `{}`, diagnostic-free); network/HTTP failures still raise `XBRLFetchError` and are NEVER negatively cached; a cache-layer error falls through to a live fetch. Tests: second query within TTL does not hit the network; a fetch error is not cached; post-TTL re-fetches.

## Done definition

Both fixes tested; the family helper documented; no edits anywhere in `s1_financials.py` beyond the named helper; full offline suite green.
