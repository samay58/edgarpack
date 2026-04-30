# Financial Table Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve user-facing financial/table presentation with the smallest durable rendering layer, without pretending already-flattened SEC table text still has recoverable structure.

**Architecture:** Add a narrow presentation layer that recognizes two cases: real GFM pipe tables and flattened financial ledger blocks. Real pipe tables render as semantic, horizontally scrollable tables. Flattened SEC table prose renders as a compact ledger/preformatted block so it is readable and inspectable, but not falsely restructured. Keep parsing/extraction untouched.

**Tech Stack:** Python stdlib HTML escaping and regex helpers, existing static report/site renderers, existing Next/React web UI, pytest, TypeScript build/lint.

---

## Scope

In scope:

- Static diff report paragraph rendering in `edgarpack/diff/html_report.py`.
- Static pack site markdown/table styling in `edgarpack/site/build.py` and `edgarpack/site/styles.py`.
- Web Observatory paragraph rendering in `web/components/observatory/diff-viewer.tsx` and `web/components/observatory/timeline-view.tsx`.
- Tests that prove real pipe tables become tables, flattened ledger blocks become readable ledger blocks, and ordinary prose remains prose.

Out of scope:

- Reconstructing multi-row SEC tables from slash-separated text.
- Changing `edgarpack/parse/md_render.py` table extraction.
- Adding markdown/HTML rendering dependencies.
- Changing financial facts, citations, chunk IDs, or claim generation.
- Broad redesign of the Observatory or China Lens UI.

## Design Boundary

The important distinction:

1. **Recoverable structure:** text contains a valid GFM table block, for example a header row, separator row, and one or more body rows. Render it as `<table>`.
2. **Lost structure:** text is already a flattened blockquote/ledger such as `> Total ... $ / 42,736 / $ / (1,625 / )`. Render it as a financial ledger block, preserving text and line breaks.

Do not use heuristics that infer column names or row spans from slash-separated prose. That path is brittle and should be a separate parser project if it ever becomes worth doing.

## File Structure

- Modify: `edgarpack/diff/html_report.py`
  - Owns static diff report HTML. Add small private helpers for rendering paragraph text as prose/table/ledger.
  - Add report-local CSS classes for `financial-table-wrap`, `financial-table`, and `financial-ledger`.

- Modify: `tests/test_diff_report.py`
  - Add coverage for GFM table rendering and flattened ledger rendering in static reports.

- Modify: `edgarpack/site/build.py`
  - Wrap rendered GFM tables in a scroll container from `_table_to_html`.
  - Add simple alignment classes based on numeric-looking cells.

- Modify: `edgarpack/site/styles.py`
  - Improve static pack table readability with horizontal scroll, tighter cells, tabular numbers, sticky-ish header styling where safe, and print-safe fallback.

- Create: `web/components/observatory/filing-text.tsx`
  - Small React renderer for paragraph text: detects GFM table blocks, detects flattened financial ledger blocks, otherwise returns prose with optional highlighted tokens.

- Modify: `web/components/observatory/diff-viewer.tsx`
  - Replace direct paragraph text rendering with `FilingText`.

- Modify: `web/components/observatory/timeline-view.tsx`
  - Replace direct timeline preview/diff paragraph rendering with `FilingText`.

- Modify: `web/app/globals.css`
  - Add shared Observatory table/ledger styles. Keep visual language consistent with existing `obs-para` surfaces.

## Task 1: Static Diff Report Table And Ledger Renderer

**Files:**

- Modify: `edgarpack/diff/html_report.py`
- Test: `tests/test_diff_report.py`

- [ ] **Step 1: Add failing static report tests**

Add two tests near the existing `render_pair_report_html` tests:

```python
def test_pair_report_html_renders_markdown_table_as_semantic_table(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old disclosure.")
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "\n\n".join(
            [
                "Debt maturity table:",
                "| Maturity | Cost | Fair value |",
                "| --- | ---: | ---: |",
                "| One year or less | $35,108 | $34,952 |",
                "| Total | $85,589 | $84,259 |",
            ]
        ),
    )

    html = render_pair_report_html(build_pair_report(before, after))

    assert '<div class="financial-table-wrap">' in html
    assert '<table class="financial-table">' in html
    assert "<th>Maturity</th>" in html
    assert '<td class="num">$85,589</td>' in html
    assert "| Maturity | Cost | Fair value |" not in html


def test_pair_report_html_renders_flattened_financial_block_as_ledger(tmp_path) -> None:
    before = _write_pack(tmp_path, "S1-001", "Old disclosure.")
    after = _write_pack(
        tmp_path,
        "S1A-002",
        "\n\n".join(
            [
                "Unrealized losses table:",
                "> **Less than 12 Months**\n>"
                "\n> Less than 12 Months / 12 Months or Greater / Total\n"
                "> U.S. government and agency securities ... $ / 37,177 / $ / (1,462 / )\n"
                "> Total ................................... $ / 42,736 / $ / (1,625 / )",
            ]
        ),
    )

    html = render_pair_report_html(build_pair_report(before, after))

    assert '<pre class="financial-ledger">' in html
    assert "U.S. government and agency securities" in html
    assert "&gt; U.S. government" not in html
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
uv run --extra dev pytest tests/test_diff_report.py::test_pair_report_html_renders_markdown_table_as_semantic_table tests/test_diff_report.py::test_pair_report_html_renders_flattened_financial_block_as_ledger -q
```

Expected: both tests fail because paragraph text is currently escaped as prose.

- [ ] **Step 3: Implement the private renderer helpers**

Add private helpers in `edgarpack/diff/html_report.py` below `_span_html`:

```python
def _is_numeric_cell(text: str) -> bool:
    cleaned = text.strip().replace(",", "")
    return bool(cleaned) and bool(
        __import__("re").fullmatch(r"[$€£¥]?\(?-?\d+(?:\.\d+)?%?\)?", cleaned)
    )


def _split_table_row(line: str) -> list[str]:
    raw = line.strip().strip("|")
    return [cell.strip().replace(r"\|", "|") for cell in raw.split("|")]


def _is_gfm_table(text: str) -> bool:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    if not lines[0].startswith("|") or not lines[1].startswith("|"):
        return False
    cells = _split_table_row(lines[1])
    return bool(cells) and all(set(cell.replace(":", "").strip()) <= {"-"} for cell in cells)


def _table_block_html(text: str) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    rows = [_split_table_row(line) for line in lines]
    header = rows[0]
    body_rows = rows[2:]
    out = ['<div class="financial-table-wrap"><table class="financial-table">', "<thead>", "<tr>"]
    for cell in header:
        out.append(f"<th>{escape(cell)}</th>")
    out.extend(["</tr>", "</thead>", "<tbody>"])
    for row in body_rows:
        out.append("<tr>")
        for cell in row:
            cls = ' class="num"' if _is_numeric_cell(cell) else ""
            out.append(f"<td{cls}>{escape(cell)}</td>")
        out.append("</tr>")
    out.extend(["</tbody>", "</table></div>"])
    return "".join(out)


def _is_flattened_financial_ledger(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    slash_lines = sum(1 for line in lines if line.count("/") >= 2)
    dotted_lines = sum(1 for line in lines if "..." in line or "...." in line)
    money_lines = sum(1 for line in lines if "$" in line or "(" in line and ")" in line)
    return slash_lines >= 2 and (dotted_lines >= 1 or money_lines >= 1)


def _clean_ledger_text(text: str) -> str:
    lines = []
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            stripped = stripped[1:].lstrip()
        stripped = stripped.replace("**", "")
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _paragraph_content_html(text: str) -> str:
    if _is_gfm_table(text):
        return _table_block_html(text)
    if _is_flattened_financial_ledger(text):
        return f'<pre class="financial-ledger">{escape(_clean_ledger_text(text))}</pre>'
    return escape(text)
```

- [ ] **Step 4: Wire helpers into `_prose_html`**

Change `_prose_html` so spans still win for modified prose, while raw table/ledger paragraphs get special rendering:

```python
def _prose_html(para: ReportParagraphDelta, side: str, css_class: str) -> str:
    if side == "old":
        spans = para.old_spans
        text = para.old_text
    else:
        spans = para.new_spans
        text = para.new_text
    content = "".join(_span_html(span) for span in spans) if spans else _paragraph_content_html(text or "")
    return f'<div class="prose {css_class}">{content}</div>'
```

- [ ] **Step 5: Add CSS to the static report style block**

Add inside `_CSS` near `.prose`:

```css
.financial-table-wrap {
  overflow-x: auto;
  margin: .2rem 0;
  border: 1px solid #d8cfba;
  background: #fffdf8;
}
.financial-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-family: var(--code);
  font-size: .86rem;
  line-height: 1.35;
}
.financial-table th,
.financial-table td {
  padding: .42rem .55rem;
  border-bottom: 1px solid #e8dfca;
  border-right: 1px solid #e8dfca;
  text-align: left;
  vertical-align: top;
  white-space: nowrap;
}
.financial-table th {
  color: var(--muted);
  background: #fbf7ee;
  font-weight: 700;
}
.financial-table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.financial-ledger {
  margin: .2rem 0;
  padding: .75rem .85rem;
  overflow-x: auto;
  border: 1px solid #d8cfba;
  background: #fffdf8;
  color: var(--ink);
  font-family: var(--code);
  font-size: .84rem;
  line-height: 1.45;
  white-space: pre;
}
```

- [ ] **Step 6: Verify focused tests pass**

Run:

```bash
uv run --extra dev pytest tests/test_diff_report.py::test_pair_report_html_renders_markdown_table_as_semantic_table tests/test_diff_report.py::test_pair_report_html_renders_flattened_financial_block_as_ledger -q
```

Expected: `2 passed`.

## Task 2: Static Pack Site Table Polish

**Files:**

- Modify: `edgarpack/site/build.py`
- Modify: `edgarpack/site/styles.py`
- Test: add to an existing site/build test if present, otherwise add to `tests/test_site_build.py`

- [ ] **Step 1: Add focused table HTML test**

If `tests/test_site_build.py` exists, append this test there. If it does not exist, create it with imports for `_markdown_to_html`.

```python
from edgarpack.site.build import _markdown_to_html


def test_static_site_wraps_financial_tables_for_scanning() -> None:
    html = _markdown_to_html(
        "\n".join(
            [
                "| Maturity | Cost | Fair value |",
                "| --- | ---: | ---: |",
                "| One year or less | $35,108 | $34,952 |",
                "| Total | $85,589 | $84,259 |",
            ]
        )
    )

    assert '<div class="table-scroll">' in html
    assert "<table>" in html
    assert '<td class="num">$85,589</td>' in html
```

- [ ] **Step 2: Run focused test and verify it fails**

Run:

```bash
uv run --extra dev pytest tests/test_site_build.py::test_static_site_wraps_financial_tables_for_scanning -q
```

Expected: FAIL until `_table_to_html` wraps tables and marks numeric cells.

- [ ] **Step 3: Update `_table_to_html`**

In `edgarpack/site/build.py`, add a private numeric helper near `_table_to_html`:

```python
def _looks_numeric_cell(text: str) -> bool:
    cleaned = text.strip().replace(",", "")
    return bool(re.fullmatch(r"[$€£¥]?\(?-?\d+(?:\.\d+)?%?\)?", cleaned))
```

Then change `_table_to_html` to start with:

```python
out = ['<div class="table-scroll">', "<table>", "<thead>", "<tr>"]
```

and close with:

```python
out.extend(["</tbody>", "</table>", "</div>"])
```

When rendering `td`, use:

```python
cls = ' class="num"' if _looks_numeric_cell(c) else ""
out.append(f"<td{cls}>{_inline(c)}</td>")
```

- [ ] **Step 4: Update static site CSS**

In `edgarpack/site/styles.py`, replace the current table block with:

```css
.table-scroll {
  width: 100%;
  overflow-x: auto;
  margin: 0.75rem 0;
  border: 1px solid var(--border);
  background: #fff;
}
table {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  margin: 0;
}
th, td {
  border-bottom: 1px solid var(--border);
  border-right: 1px solid var(--border);
  padding: 0.38rem 0.55rem;
  vertical-align: top;
  white-space: nowrap;
}
th {
  text-align: left;
  color: var(--muted);
  font-weight: 600;
  background: #f3f3f3;
}
td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
tbody tr:nth-child(even) { background: #fcfcfc; }
```

- [ ] **Step 5: Verify focused test passes**

Run:

```bash
uv run --extra dev pytest tests/test_site_build.py::test_static_site_wraps_financial_tables_for_scanning -q
```

Expected: `1 passed`.

## Task 3: Web Observatory Filing Text Renderer

**Files:**

- Create: `web/components/observatory/filing-text.tsx`
- Modify: `web/components/observatory/diff-viewer.tsx`
- Modify: `web/components/observatory/timeline-view.tsx`
- Modify: `web/app/globals.css`

- [ ] **Step 1: Create the renderer component**

Create `web/components/observatory/filing-text.tsx`:

```tsx
import type { ReactNode } from "react";

type FilingTextProps = {
  text: string;
  children?: ReactNode;
};

function splitTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}

function isGfmTable(text: string): boolean {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  if (lines.length < 3) return false;
  if (!lines[0].startsWith("|") || !lines[1].startsWith("|")) return false;
  const separators = splitTableRow(lines[1]);
  return separators.length > 0 && separators.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isNumericCell(text: string): boolean {
  return /^[$€£¥]?\(?-?\d[\d,.]*%?\)?$/.test(text.trim());
}

function isFlattenedFinancialLedger(text: string): boolean {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  if (lines.length < 3) return false;
  const slashLines = lines.filter((line) => (line.match(/\//g) ?? []).length >= 2).length;
  const dottedLines = lines.filter((line) => line.includes("...")).length;
  const moneyLines = lines.filter((line) => line.includes("$") || /\([\d,.\s/]+\)/.test(line)).length;
  return slashLines >= 2 && (dottedLines >= 1 || moneyLines >= 1);
}

function cleanLedgerText(text: string): string {
  return text
    .split("\n")
    .map((line) => line.trim().replace(/^>\s?/, "").replaceAll("**", ""))
    .filter(Boolean)
    .join("\n");
}

function TableBlock({ text }: { text: string }) {
  const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
  const header = splitTableRow(lines[0]);
  const rows = lines.slice(2).map(splitTableRow);
  return (
    <div className="obs-financial-table-wrap">
      <table className="obs-financial-table">
        <thead>
          <tr>
            {header.map((cell, i) => (
              <th key={`${cell}-${i}`}>{cell}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, c) => (
                <td key={`${r}-${c}`} className={isNumericCell(cell) ? "num" : undefined}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FilingText({ text, children }: FilingTextProps) {
  if (isGfmTable(text)) return <TableBlock text={text} />;
  if (isFlattenedFinancialLedger(text)) {
    return <pre className="obs-financial-ledger">{cleanLedgerText(text)}</pre>;
  }
  return <>{children ?? text}</>;
}
```

- [ ] **Step 2: Wire `DiffViewer`**

Import:

```tsx
import { FilingText } from "@/components/observatory/filing-text";
```

In `ParagraphDiff`, replace direct `delta.old_text` and `delta.new_text` rendering with:

```tsx
<FilingText text={delta.old_text}>
  {delta.old_text}
</FilingText>
```

and highlighted modified blocks with:

```tsx
<FilingText text={delta.old_text}>
  {renderHighlightedText(delta.old_text, oldOnly, "old")}
</FilingText>
```

Repeat for `delta.new_text`.

- [ ] **Step 3: Wire `TimelineView`**

Import `FilingText` and wrap the text in expanded paragraph blocks:

```tsx
<FilingText text={p.old_text}>
  {renderHighlightedText(p.old_text, oldOnly, "old")}
</FilingText>
```

For `entry.content_preview`, use:

```tsx
<FilingText text={entry.content_preview}>{entry.content_preview}</FilingText>
```

- [ ] **Step 4: Add web CSS**

Add to `web/app/globals.css` near the existing `.obs-para` styles:

```css
.obs-financial-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--obs-line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.78);
}

.obs-financial-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.35;
}

.obs-financial-table th,
.obs-financial-table td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(142, 160, 196, 0.28);
  border-right: 1px solid rgba(142, 160, 196, 0.2);
  white-space: nowrap;
  text-align: left;
  vertical-align: top;
}

.obs-financial-table th {
  color: var(--obs-muted);
  background: rgba(247, 250, 255, 0.9);
  font-weight: 700;
}

.obs-financial-table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.obs-financial-ledger {
  margin: 0;
  overflow-x: auto;
  border: 1px solid var(--obs-line);
  border-radius: 8px;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.78);
  color: var(--obs-ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre;
}
```

- [ ] **Step 5: Run web validation**

Run:

```bash
npm --prefix web run build
```

Expected: Next build succeeds.

## Task 4: Visual Smoke Check With Existing Artifacts

**Files:**

- No code files unless visual smoke reveals clipping/overflow.

- [ ] **Step 1: Regenerate or open the static NVDA report**

If `reports/nvda-10k.html` still exists, open it directly. Otherwise regenerate the report using the same CLI path that produced it.

Expected visual result:

- The “Debt Investment Maturities” pipe table is semantic and horizontally scrolls if needed.
- The “Less than 12 Months” flattened block is compact ledger text, not giant prose.
- Evidence lines remain visible and unchanged.

- [ ] **Step 2: Run a desktop and mobile web smoke**

Start the web app only if needed:

```bash
npm --prefix web run dev
```

Expected visual result:

- Diff paragraphs with tables do not force page-width overflow.
- Tables scroll inside the paragraph card.
- Ledger blocks preserve lines and do not wrap into unreadable slash soup.
- Reduced-motion behavior is unchanged because no new motion is introduced.

## Task 5: Quality Gates And Handoff

**Files:**

- No additional files.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
uv run --extra dev pytest tests/test_diff_report.py tests/test_site_build.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run default quality gate**

Run:

```bash
scripts/symphony_quality_gate.sh
```

Expected: ruff and pytest pass.

- [ ] **Step 3: Run web build**

Run:

```bash
npm --prefix web run build
```

Expected: Next build succeeds.

- [ ] **Step 4: Commit**

Run:

```bash
git add edgarpack/diff/html_report.py edgarpack/site/build.py edgarpack/site/styles.py tests/test_diff_report.py tests/test_site_build.py web/components/observatory/filing-text.tsx web/components/observatory/diff-viewer.tsx web/components/observatory/timeline-view.tsx web/app/globals.css
git commit -m "Improve financial table presentation"
```

- [ ] **Step 5: Push and open PR**

Run:

```bash
git push -u origin codex/sem-13-table-presentation
gh pr create --title "SEM-13: Improve financial table presentation" --body-file /tmp/sem-13-pr.md
```

PR body must include:

- Linear issue: `SEM-13`
- What changed.
- Tests run.
- Remaining risk: flattened SEC ledgers are readability-only, not reconstructed tables.

## Self-Review

- Spec coverage: The plan covers static diff reports, static pack HTML tables, and web Observatory paragraph presentation. It deliberately excludes parser reconstruction.
- Placeholder scan: No unresolved placeholder markers are present.
- Type consistency: Python helper names are private and local. React component name is consistently `FilingText`.
- Risk check: Numeric-cell detection is presentation-only and must not feed back into facts, citations, or claims.
