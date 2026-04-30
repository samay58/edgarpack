import type { ReactNode } from "react";

type FilingTextProps = {
  text: string;
  children?: ReactNode;
};

function isEscapedPipe(line: string, index: number): boolean {
  let backslashes = 0;
  for (let i = index - 1; i >= 0 && line[i] === "\\"; i -= 1) {
    backslashes += 1;
  }
  return backslashes % 2 === 1;
}

function stripOuterTableDelimiters(line: string): string {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) {
    trimmed = trimmed.slice(1);
  }
  if (trimmed.endsWith("|") && !isEscapedPipe(trimmed, trimmed.length - 1)) {
    trimmed = trimmed.slice(0, -1);
  }
  return trimmed;
}

function splitTableRow(line: string): string[] {
  const cells: string[] = [];
  let cell = "";
  const innerLine = stripOuterTableDelimiters(line);

  for (let i = 0; i < innerLine.length; i += 1) {
    const char = innerLine[i];
    if (char === "|" && !isEscapedPipe(innerLine, i)) {
      cells.push(cell.trim().replaceAll("\\|", "|"));
      cell = "";
      continue;
    }
    cell += char;
  }

  cells.push(cell.trim().replaceAll("\\|", "|"));
  return cells;
}

function getTableLines(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function isTableSeparator(line: string): boolean {
  const cells = splitTableRow(line);
  return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isGfmTable(text: string): boolean {
  const lines = getTableLines(text);
  if (lines.length < 2) return false;
  if (!lines[0].includes("|") || !lines[1].includes("|")) return false;

  const header = splitTableRow(lines[0]);
  const separators = splitTableRow(lines[1]);
  const bodyRows = lines.slice(2).map(splitTableRow);
  return (
    header.length >= 2 &&
    header.length === separators.length &&
    header.every((cell) => cell.length > 0) &&
    isTableSeparator(lines[1]) &&
    bodyRows.every((row) => row.length === header.length)
  );
}

function isNumericCell(text: string): boolean {
  return /^[$€£¥]?\(?-?\d[\d,.]*(?:%|x|bps)?\)?$/i.test(text.trim());
}

function isFlattenedFinancialLedger(text: string): boolean {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 3) return false;

  const slashLines = lines.filter((line) => (line.match(/\//g) ?? []).length >= 2).length;
  const dottedOrMoneyLines = lines.filter(
    (line) => line.includes("...") || line.includes("$") || /\([\d,.\s/]+\)/.test(line),
  ).length;
  return slashLines >= 2 && dottedOrMoneyLines >= 1;
}

function cleanLedgerText(text: string): string {
  return text
    .split("\n")
    .map((line) => line.trim().replace(/^>\s?/, "").replaceAll("**", ""))
    .join("\n")
    .trim();
}

function TableBlock({ text }: { text: string }) {
  const lines = getTableLines(text);
  const header = splitTableRow(lines[0]);
  const rows = lines.slice(2).map(splitTableRow);

  return (
    <div className="obs-financial-table-wrap">
      <table className="obs-financial-table">
        <thead>
          <tr>
            {header.map((cell, columnIndex) => (
              <th key={`header-${columnIndex}`}>{cell}</th>
            ))}
          </tr>
        </thead>
        {rows.length > 0 && (
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                {row.map((cell, columnIndex) => (
                  <td
                    key={`cell-${rowIndex}-${columnIndex}`}
                    className={isNumericCell(cell) ? "num" : undefined}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        )}
      </table>
    </div>
  );
}

export function FilingText({ text, children }: FilingTextProps) {
  const hasHighlightedChildren = children !== undefined && typeof children !== "string";
  if (hasHighlightedChildren) return <>{children}</>;
  if (isGfmTable(text)) return <TableBlock text={text} />;
  if (isFlattenedFinancialLedger(text)) {
    return <pre className="obs-financial-ledger">{cleanLedgerText(text)}</pre>;
  }
  return <>{children ?? text}</>;
}
