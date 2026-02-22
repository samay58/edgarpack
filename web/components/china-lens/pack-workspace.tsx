"use client";

import { useMemo, useState, useTransition } from "react";

import { EvidenceExplorer } from "@/components/china-lens/evidence-explorer";
import { PackSection } from "@/components/china-lens/pack-section";
import { askEvidence, resolveCitation } from "@/lib/api-client";
import { demoAskResponse, demoEvidenceTarget } from "@/lib/sample-data";
import type { AskResponse, DocumentView, EvidenceTarget, PackView } from "@/types/china-lens";

type PackWorkspaceProps = {
  companyId: string;
  pack: PackView;
  documents: DocumentView[];
};

export function PackWorkspace({ companyId, pack, documents }: PackWorkspaceProps) {
  const [activeEvidence, setActiveEvidence] = useState<EvidenceTarget>(demoEvidenceTarget);
  const [askInput, setAskInput] = useState("Top customers, concentration, and whether disclosed by name?");
  const [askResult, setAskResult] = useState<AskResponse>(demoAskResponse);
  const [isPending, startTransition] = useTransition();

  const coverage = useMemo(() => {
    return {
      filings: "complete",
      translation: pack.status === "partial" ? "partial" : "complete",
      tables: "complete",
      citations: pack.sections.every((section) => section.findings.some((f) => f.citations.length > 0))
        ? "complete"
        : "partial",
    };
  }, [pack]);

  const openEvidence = (chunkId: string) => {
    startTransition(async () => {
      const resolved = await resolveCitation(chunkId);
      setActiveEvidence(resolved);
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
        <h2>Pack Overview</h2>
        <ul>
          <li>Concentration disclosure is present with numeric support.</li>
          <li>Named customer disclosure is not provided in indexed filings.</li>
          <li>Governance composition is explicit and cited.</li>
        </ul>
        <div className="coverage-strip">
          <span>Filings: {coverage.filings}</span>
          <span>Translation: {coverage.translation}</span>
          <span>Tables: {coverage.tables}</span>
          <span>Citations: {coverage.citations}</span>
        </div>
      </section>

      {pack.sections.map((section) => (
        <PackSection key={section.id} section={section} onOpenEvidence={openEvidence} />
      ))}

      <section className="panel ask-panel">
        <h3>Ask (bounded to indexed evidence)</h3>
        <div className="ask-row">
          <input
            value={askInput}
            onChange={(event) => setAskInput(event.target.value)}
            aria-label="Ask a diligence question"
          />
          <button type="button" className="primary-btn" onClick={runAsk} disabled={isPending}>
            {isPending ? "Searching..." : "Ask"}
          </button>
        </div>
        <div className="ask-results">
          {askResult.answer.map((block, idx) => (
            <article key={`${block.text}-${idx}`}>
              <p>{block.text}</p>
              <div className="citation-row">
                {block.citations.map((citation) => (
                  <button
                    key={`${citation.chunk_id}-${citation.page}`}
                    type="button"
                    className="citation-pill"
                    onClick={() => openEvidence(citation.chunk_id)}
                  >
                    p.{citation.page}
                  </button>
                ))}
              </div>
            </article>
          ))}
          <p className="muted">{askResult.guidance}</p>
        </div>
      </section>

      <EvidenceExplorer documents={documents} evidenceTarget={activeEvidence} />
    </div>
  );
}
