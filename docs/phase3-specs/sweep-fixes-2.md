# Packet: sweep-fixes-2

Goal: close the four fail-closed coverage gaps the re-sweep found (21/25 -> potentially 25/25 minus the two designed-layout filers). All four reproduced with mechanisms and real-world shapes recorded in the re-sweep artifacts (session scratchpad `resweep-25/`, notably `notes_prior_sweep_mechanisms.md`, `analysis.json`, and the per-filer packs).

Files owned: `edgarpack/sse/annual_facts.py`, `edgarpack/sse/sectionize_cn.py`, `edgarpack/config.py` (PARSER_VERSION line only), tests.

## Fixes

1. `cmb-split-chapters` (P1). CMB splits what the CSRC template usually compounds: `第一章 公司简介` and `第二章 会计数据和财务指标摘要` are separate chapters, but `_ANNUAL_REPORT_SECTIONS` (`sectionize_cn.py` ~56-59) only recognizes the compound `公司简介和主要财务指标` title, so both chapters fall back to pinyin-slug ids and `write_annual_facts` (which scans only the `annual_s02` prefix) never sees the key table. Extend the canonical mapping: a standalone chapter titled with the accounting-data family (`会计数据和财务指标摘要`, `主要会计数据`, `会计数据摘要` variants) maps to the same canonical key-financials id (`annual_s02_company_profile_key_financials`); a standalone `公司简介` chapter maps to the profile id. This changes SSE section ids for such filers: bump PARSER_VERSION 0.2.3 -> 0.2.4 with the standing verified-safe rationale restated. Regression test from CMB's real chapter titles.

2. `smic-separator` (P1). SMIC's key table layout is title / separator / marker row (`||||单位：千元|币种：人民币|`) / separator / year header: an extra separator sits between marker and header, and `_find_unit_scale` (~166-188) breaks at the first separator scanning upward, never reaching the marker. Skip separator rows while scanning upward; terminate on a blank line, heading, or scan-window limit instead. Regression test from SMIC's exact layout (values in 千元, so the fix must also produce correctly scaled facts).

3. `longi-adjusted-revenue` (P2). Revenue's `label_contains="营业收入"` substring-matches LONGi's adjusted variant `扣除...后的营业收入` too; two differing candidates in the same table manufacture a conflict and revenue fails closed for every year. Exclude rows whose label contains `扣除` from matching the plain revenue spec (same exclusion family as the existing ratio/`其中：` rules). Regression: headline + adjusted rows coexist, headline extracts, no conflict warning.

4. `eastmoney-total-revenue` (P2). Financial/brokerage filers title the headline revenue row `营业总收入`, which the contiguous-substring match on `营业收入` cannot see (总 breaks it). Accept `营业总收入` as an additional revenue label. If a table carries BOTH labels with differing values, the existing conflict machinery fails closed as today (do not add a preference rule; that would be a new judgment). Regression: 营业总收入-only table extracts revenue; both-labels-differing still fails closed.

## Constraints

`tests/eval/china_golden.yaml`, the fixture packs, and every existing annual_facts/sectionize test stay green untouched. The two designed-layout filers (Ping An, Zijin) remain out of scope.

## Done definition

Four regression tests green; PARSER_VERSION 0.2.4; full offline suite green.
