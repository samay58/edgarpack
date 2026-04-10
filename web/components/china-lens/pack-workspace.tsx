"use client";

import { useRef, useState, useTransition } from "react";

import { CitationPill } from "@/components/china-lens/citation-pill";
import {
  EvidenceExplorer,
  type ReadingMode,
} from "@/components/china-lens/evidence-explorer";
import { PackSection } from "@/components/china-lens/pack-section";
import { askEvidence, resolveCitation } from "@/lib/api-client";
import { demoAskResponse, demoEvidenceTarget } from "@/lib/sample-data";
import type { AskResponse, DocumentView, EvidenceTarget, PackView } from "@/types/china-lens";

const DEMO_ASK_PLACEHOLDER =
  "Top customers, concentration, and whether disclosed by name?";

type PackWorkspaceProps = {
  companyId: string;
  pack: PackView;
  documents: DocumentView[];
};

export function PackWorkspace({ companyId, pack, documents }: PackWorkspaceProps) {
  const [activeEvidence, setActiveEvidence] = useState<EvidenceTarget>(demoEvidenceTarget);
  const [askInput, setAskInput] = useState(DEMO_ASK_PLACEHOLDER);
  const [askResult, setAskResult] = useState<AskResponse>(demoAskResponse);
  const [readingMode, setReadingMode] = useState<ReadingMode>("en");
  const [findingFilter, setFindingFilter] = useState<"all" | "supported" | "unsupported">(
    "supported",
  );
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [isPending, startTransition] = useTransition();
  const citationCache = useRef<Record<string, EvidenceTarget>>({});

  const coverage = {
    filings: "complete",
    translation: pack.status === "partial" ? "partial" : "complete",
    tables: "complete",
    citations: pack.sections.every((section) =>
      section.findings.some((f) => f.citations.length > 0),
    )
      ? "complete"
      : "partial",
  };

  const sectionLinks = pack.sections.map((section) => ({
    id: section.id,
    title: section.title,
  }));

  const visibleSections = pack.sections
    .map((section) => {
      const findings =
        findingFilter === "all"
          ? section.findings
          : section.findings.filter((finding) =>
              findingFilter === "supported"
                ? finding.status === "supported"
                : finding.status === "unsupported",
            );
      return {
        ...section,
        findings,
        key_points: findings.map((finding) => finding.claim_text),
      };
    })
    .filter((section) => findingFilter === "all" || section.findings.length > 0);

  const openEvidence = (chunkId: string) => {
    const cached = citationCache.current[chunkId];
    if (cached) {
      setActiveEvidence(cached);
      return;
    }
    setEvidenceLoading(true);
    startTransition(async () => {
      try {
        const resolved = await resolveCitation(chunkId);
        citationCache.current[chunkId] = resolved;
        setActiveEvidence(resolved);
      } finally {
        setEvidenceLoading(false);
      }
    });
  };

  const runAsk = () => {
    startTransition(async () => {
      const result = await askEvidence(askInput, companyId);
      setAskResult(result);
    });
  };

  return (
    <div className="page-stack">
      <section className="panel summary-panel">
        <div className="row between">
          <h2>Pack Overview</h2>
          <div className="filter-controls">
            <span className="muted control-label">Read</span>
            <button
              type="button"
              className={readingMode === "en" ? "mode-btn active" : "mode-btn"}
              onClick={() => setReadingMode("en")}
            >
              EN
            </button>
            <button
              type="button"
              className={readingMode === "bilingual" ? "mode-btn active" : "mode-btn"}
              onClick={() => setReadingMode("bilingual")}
            >
              EN+CN
            </button>
          </div>
        </div>
        <ul>
          <li>Concentration disclosure is present with numeric support.</li>
          <li>Named customer disclosure is not provided in indexed filings.</li>
          <li>Governance composition is explicit and cited.</li>
        </ul>
        <div className="section-jump" aria-label="Jump to section">
          {sectionLinks.map((section) => (
            <a key={section.id} href={`#${section.id}`} className="jump-chip">
              {section.title}
            </a>
          ))}
        </div>
        <div className="coverage-strip">
          <span>Filings: {coverage.filings}</span>
          <span>Translation: {coverage.translation}</span>
          <span>Tables: {coverage.tables}</span>
          <span>Citations: {coverage.citations}</span>
        </div>
        <div className="filter-controls">
          <span className="muted control-label">Findings</span>
          <button
            type="button"
            className={findingFilter === "supported" ? "mode-btn active" : "mode-btn"}
            onClick={() => setFindingFilter("supported")}
          >
            Supported
          </button>
          <button
            type="button"
            className={findingFilter === "all" ? "mode-btn active" : "mode-btn"}
            onClick={() => setFindingFilter("all")}
          >
            All
          </button>
          <button
            type="button"
            className={findingFilter === "unsupported" ? "mode-btn active" : "mode-btn"}
            onClick={() => setFindingFilter("unsupported")}
          >
            Unsupported
          </button>
        </div>
      </section>

      {visibleSections.map((section) => (
        <PackSection key={section.id} section={section} onOpenEvidence={openEvidence} />
      ))}

      <section className="panel ask-panel">
        <h3>Ask (bounded to indexed evidence)</h3>
        <div className="ask-row">
          <input
            value={askInput}
            onChange={(event) => setAskInput(event.target.value)}
            aria-label="Ask a diligence question"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                runAsk();
              }
            }}
          />
          <button type="button" className="primary-btn" onClick={runAsk} disabled={isPending}>
            {isPending ? "Searching..." : "Ask"}
          </button>
        </div>
        <section className="ask-results" aria-live="polite">
          {askResult.answer.map((block, idx) => (
            <article key={`${block.text}-${idx}`}>
              <p>{block.text}</p>
              <div className="citation-row">
                {block.citations.map((citation) => (
                  <CitationPill
                    key={`${citation.chunk_id}-${citation.page}`}
                    citation={citation}
                    onOpenEvidence={openEvidence}
                  />
                ))}
              </div>
            </article>
          ))}
          <p className="muted">{askResult.guidance}</p>
        </section>
      </section>

      <EvidenceExplorer
        documents={documents}
        evidenceTarget={activeEvidence}
        readingMode={readingMode}
        onReadingModeChange={setReadingMode}
        isLoading={evidenceLoading}
      />
    </div>
  );
}
