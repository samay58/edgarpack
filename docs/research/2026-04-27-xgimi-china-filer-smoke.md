# XGIMI China Filer Smoke

Date: 2026-04-27

Target: Chengdu XGIMI Technology Co., Ltd. / XGIMI / 688696, Shanghai Stock Exchange STAR Market.

## Source Documents

- SSE STAR company page: `https://star.sse.com.cn/star/en/marketdata/snapshot/c/5524041.shtml`
- XGIMI 2024 annual report PDF: `https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF`
- Sofina 2025 annual report for Laifen private-company evidence: `https://www.sofinagroup.com/wp-content/uploads/2026/03/annual-report-2025.pdf`

## Commands Run

```bash
mkdir -p /tmp/edgarpack-xgimi
curl -fsSL -o /tmp/edgarpack-xgimi/xgimi-2024-annual.pdf \
  https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF
```

```bash
uv run --extra sse python -c "import pymupdf4llm; print('pymupdf4llm ok')"
```

```bash
uv run --extra sse edgarpack build-sse \
  --url https://static.cninfo.com.cn/finalpage/2025-04-22/1223192484.PDF \
  --pdf /tmp/edgarpack-xgimi/xgimi-2024-annual.pdf \
  --stock-code 688696 \
  --company "Chengdu XGIMI Technology Co., Ltd." \
  --filing-date 2025-04-22 \
  --out /tmp/edgarpack-xgimi \
  --with-chunks \
  --force
```

```bash
rg -n "公司股票简况|上海证券交易所科创板|股票代码|营业收入|归属于上市公司股东的净利润|经营活动产生的现金流量净额|研发投入占营业收入的比例" \
  /tmp/edgarpack-xgimi/sse/688696/688696_2025-04-22/filing.full.md
```

## Result

The current CLI can build a usable scratch pack from the XGIMI annual report once the `sse` extra is available. The build produced:

- Output: `/tmp/edgarpack-xgimi/sse/688696/688696_2025-04-22`
- Sections: 11
- Tokens: 198,793
- Chunks: 197
- Warning: `Content before first detected section`

The pack is useful but not product-grade:

- The manifest reports `form_type: IPO-PROSPECTUS`, even though this is a 2024 annual report.
- Section IDs are prospectus-shaped or pinyin slugs, for example `ipo_s02_gong_si_jian_jie_he_zhu_yao_ca.md`.
- `query` is not connected to this pack/fact path.

## Extracted Evidence

From the generated pack:

- Listing row: `/tmp/edgarpack-xgimi/.../filing.full.md:217` has A-share, SSE STAR Market, stock short name XGIMI, code `688696`.
- FY2024 revenue: `/tmp/edgarpack-xgimi/.../sections/ipo_s02_gong_si_jian_jie_he_zhu_yao_ca.md:89` reports `3,404,605,307.88`.
- FY2024 net income attributable to listed-company shareholders: same section line 90 reports `120,142,895.56`.
- FY2024 operating cash flow: same section line 92 reports `230,241,355.89`.
- FY2024 R&D intensity: same section line 115 reports `10.80%`.

## User-Facing CLI Failures

```bash
uv run edgarpack query 688696 revenue --period lfy --citations footer
```

Current behavior: treats `688696` as SEC CIK `0000688696`, fetches SEC submissions, receives HTTP 404, then returns `Revenue: N/A`.

```bash
uv run edgarpack which 688696
```

Current behavior: resolves `688696` to CIK `0000688696` and asks for SEC packs.

```bash
uv run edgarpack query XGIMI revenue --period lfy --citations footer
uv run edgarpack which XGIMI
```

Current behavior: unknown SEC issuer name.

```bash
uv run edgarpack query laifen revenue --period lfy --citations footer
uv run edgarpack which laifen
```

Current behavior: unknown SEC issuer name.

## Laifen Check

No public-listing evidence was verified through EdgarPack. Sofina's 2025 annual report lists `Shenzhen Shuye Innovative Technology (Laifen)` as a Sofina Direct level 2/3 investment with first investment year 2023, 403,752 shares, and 4.58% ownership. That supports the working assumption that Laifen is private, but this smoke did not perform an exhaustive exchange-listing search.

## Follow-Ups (bead ids are historical; beads tracking is retired)

- `edgarpack-49u`: route A-share stock codes away from SEC CIK fallback.
- `edgarpack-z8b`: support SSE/CNINFO listed-company annual-report packs and query facts.

