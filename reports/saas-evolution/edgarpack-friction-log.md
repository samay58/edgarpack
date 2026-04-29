# EdgarPack Friction Log

Record product friction from using EdgarPack heavily. File follow-up beads for material issues.

| category | command_or_file | observed_behavior | expected_behavior | impact | bead_id | status |
| --- | --- | --- | --- | --- | --- | --- |
| local-runtime | `uv run edgarpack identify <ticker>` under default sandbox | Command failed before EdgarPack started: `failed to open file /Users/samaydhawan/.cache/uv/sdists-v9/.git: Operation not permitted`. | Agent workflows should have a documented hermetic invocation path or a project-local cache option that avoids false tool failures. | Raw evidence files can silently contain environment errors unless checked before notes are written. | TBD | candidate |
| filing-discovery | `edgarpack list <ticker> --form 10-K` for SHOP/TEAM | 10-K-only listing made SHOP and TEAM look like they lacked usable annual history until 40-F/20-F/F-1 were queried separately. | Investor workflow should offer an annual-report discovery mode that follows issuer form-family changes automatically. | Researchers must already know foreign-issuer form families, which weakens EdgarPack as an investor copilot. | TBD | candidate |
