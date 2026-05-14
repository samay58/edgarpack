# Filing Distill

`edgarpack distill` compresses one existing filing pack into a small cited surface.

Use it when the filing is too large to scan directly and you want the substance without a memo.

```bash
edgarpack distill run lime-s1 --pack packs/0001699963/0001628280-26-032523
edgarpack distill check reports/lime-s1
```

You can also resolve a pack by accession:

```bash
edgarpack distill run lime-s1 \
  --company "Neutron Holdings" \
  --accession 0001628280-26-032523
```

The command writes:

- `index.md`: human scan surface.
- `findings.csv`: non-financial disclosures.
- `metrics.csv`: financials and KPIs.
- `evidence.jsonl`: evidence records for tools and LLMs.
- `gaps.csv`: missing, ambiguous, or unsafe extraction areas.
- `filing-map.md`: high-signal sections.
- `run-log.md`: source pack and generated files.
- `bundle.json`: machine-readable manifest.

The rule is simple: rows need evidence. If EdgarPack cannot support something, it belongs in `gaps.csv`, not in confident prose.

Version 1 uses existing packs only. It does not fetch filings, rewrite `which`, normalize tables, or generate memos.
