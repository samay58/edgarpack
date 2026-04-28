# Filing Selection Notes

Use this file for judgment calls: missing exact-year filings, predecessor mappings, S-1 or 10-K fallback, left-censored public-company life arcs, and companies where "founder" is not a meaningful filing concept.

## Notes

### Validation Slice Identity And Filing Coverage

- Microsoft, Walmart, Intel, Exxon Mobil, Coca-Cola, and General Electric have exact or near-exact 1996 DEF 14A coverage through EdgarPack.
- Microsoft, Walmart, Intel, Apple, Exxon Mobil, Coca-Cola, General Electric, and JPMorgan Chase have pre-EDGAR IPO histories; life-arc rows must be labeled left-censored.
- Nvidia has an EDGAR S-1 from 1998 and proxy coverage from 1999 onward.
- Alphabet resolves to current CIK 0001652044, but IPO-stage evidence is under Google Inc CIK 0001288776.
- Meta Platforms has an EDGAR S-1 from 2012; its public-plus-20 comparison point is after 2026 and should not be filled as evidence.
- Broadcom resolves to current CIK 0001730168, but life-arc evidence may require Avago Technologies CIK 0001441634.
- JPMorgan Chase has 1996 proxy coverage under CIK 0000019617, but the 1996 interpretation should preserve predecessor and merger continuity notes.

### Pre-2000 Raw Text Limitation

Several pre-2000 SEC accessions can be retrieved as raw `.txt` filings, but the current EdgarPack build path produced SEC directory-listing packs rather than parsed proxy text. Validation rows for those filings use `raw_sec_txt` evidence anchors and must not be treated as normal sectionized EdgarPack chunks.

Affected validation rows include Microsoft 1996, Walmart 1996, Intel 1996, Exxon 1996, Coca-Cola 1996, GE 1996, and Nvidia's 1998 S-1.
