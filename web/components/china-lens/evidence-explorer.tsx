"use client";

import type { DocumentView, EvidenceTarget } from "@/types/china-lens";

export type ReadingMode = "en" | "bilingual" | "cn";

type EvidenceExplorerProps = {
  documents: DocumentView[];
  evidenceTarget?: EvidenceTarget | null;
  readingMode: ReadingMode;
  onReadingModeChange: (mode: ReadingMode) => void;
  isLoading?: boolean;
};

export function EvidenceExplorer({
  documents,
  evidenceTarget,
  readingMode,
  onReadingModeChange,
  isLoading = false,
}: EvidenceExplorerProps) {
  return (
    <div className="evidence-grid panel">
      <aside className="evidence-doc-list">
        <h3>Documents</h3>
        <ul>
          {documents.map((doc) => (
            <li key={doc.id} className={doc.id === evidenceTarget?.doc_id ? "active" : ""}>
              <div>{doc.title}</div>
              <small>{doc.filing_date}</small>
            </li>
          ))}
        </ul>
      </aside>
      <div className="evidence-viewer">
        <h3>PDF View</h3>
        <div className="pdf-placeholder">
          <span>
            {isLoading
              ? "Resolving citation..."
              : evidenceTarget?.citation_label ?? "Select a citation"}
          </span>
          <small>{evidenceTarget ? `Page ${evidenceTarget.page}` : "No source selected"}</small>
        </div>
      </div>
      <aside className="evidence-snippet">
        <div className="row between">
          <h3>Extracted Evidence</h3>
          <div className="mode-switch" role="group" aria-label="Evidence reading mode">
            <button
              type="button"
              className={readingMode === "en" ? "mode-btn active" : "mode-btn"}
              onClick={() => onReadingModeChange("en")}
            >
              EN
            </button>
            <button
              type="button"
              className={readingMode === "bilingual" ? "mode-btn active" : "mode-btn"}
              onClick={() => onReadingModeChange("bilingual")}
            >
              EN+CN
            </button>
            <button
              type="button"
              className={readingMode === "cn" ? "mode-btn active" : "mode-btn"}
              onClick={() => onReadingModeChange("cn")}
            >
              CN
            </button>
          </div>
        </div>
        {evidenceTarget && readingMode !== "cn" ? (
          <div className="snippet-toggle">
            <span className="tag">EN</span>
            <p>{evidenceTarget.text_en}</p>
          </div>
        ) : null}
        {evidenceTarget && readingMode !== "en" ? (
          <div className="snippet-toggle">
            <span className="tag">CN</span>
            <p>{evidenceTarget.text_zh}</p>
          </div>
        ) : null}
        {!evidenceTarget && !isLoading ? (
          <p className="muted">Open a citation to inspect the indexed source snippet.</p>
        ) : null}
        <div className="evidence-actions">
          <button
            type="button"
            className="secondary-btn"
            disabled={!evidenceTarget}
            onClick={() => {
              if (evidenceTarget) {
                navigator.clipboard.writeText(evidenceTarget.citation_label);
              }
            }}
          >
            Copy citation
          </button>
          <button
            type="button"
            className="secondary-btn"
            disabled={!evidenceTarget}
            onClick={() => {
              if (evidenceTarget) {
                navigator.clipboard.writeText(
                  readingMode === "cn" ? evidenceTarget.text_zh : evidenceTarget.text_en,
                );
              }
            }}
          >
            Copy snippet
          </button>
        </div>
      </aside>
    </div>
  );
}
