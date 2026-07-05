"""Registration-filing (S-1 / F-1) financial extraction.

Split across `snapshot` (dataclasses + cache), `table_parse` (deterministic
summary-table parser), `llm` (Haiku extraction + row gate), and `integrate`
(snapshot -> CitedValue and the query augmentation entry point). The
`edgarpack.query.s1_financials` module is a compatibility shim re-exporting
this package's public surface.
"""
