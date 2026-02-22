"use client";

import type { DocumentView, EvidenceTarget } from "@/types/china-lens";

type EvidenceExplorerProps = {
  documents: DocumentView[];
  evidenceTarget: EvidenceTarget;
};

export function EvidenceExplorer({ documents, evidenceTarget }: EvidenceExplorerProps) {
  return (
    <div className="evidence-grid panel">
      <aside className="evidence-doc-list">
        <h3>Documents</h3>
        <ul>
          {documents.map((doc) => (
            <li key={doc.id} className={doc.id === evidenceTarget.doc_id ? "active" : ""}>
              <div>{doc.title}</div>
              <small>{doc.filing_date}</small>
            </li>
          ))}
        </ul>
      </aside>
      <div className="evidence-viewer">
        <h3>PDF View</h3>
        <div className="pdf-placeholder">
          <span>{evidenceTarget.citation_label}</span>
          <small>Page {evidenceTarget.page}</small>
        </div>
      </div>
      <aside className="evidence-snippet">
        <h3>Extracted Evidence</h3>
        <div className="snippet-toggle">
          <span className="tag">CN</span>
          <p>{evidenceTarget.text_zh}</p>
        </div>
        <div className="snippet-toggle">
          <span className="tag">EN</span>
          <p>{evidenceTarget.text_en}</p>
        </div>
        <button type="button" className="secondary-btn">
          Copy citation
        </button>
      </aside>
    </div>
  );
}
