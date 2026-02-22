"use client";

import { CitationPill } from "@/components/china-lens/citation-pill";
import type { PackSectionView } from "@/types/china-lens";

type PackSectionProps = {
  section: PackSectionView;
  onOpenEvidence: (chunkId: string) => void;
};

export function PackSection({ section, onOpenEvidence }: PackSectionProps) {
  return (
    <section className="panel pack-section" id={section.id}>
      <div className="row between">
        <h3>{section.title}</h3>
        <span className={`coverage coverage-${section.coverage_status}`}>{section.coverage_status}</span>
      </div>
      <p className="thesis">{section.thesis}</p>
      <ul className="finding-list">
        {section.findings.map((finding) => (
          <li
            key={finding.id}
            className={finding.status === "unsupported" ? "finding finding-unsupported" : "finding"}
          >
            <span>{finding.status === "unsupported" ? `Unsupported: ${finding.claim_text}` : finding.claim_text}</span>
            {finding.citations.length > 0 ? (
              <span className="citation-row">
                {finding.citations.map((citation) => (
                  <CitationPill
                    key={`${finding.id}-${citation.chunk_id}-${citation.page}`}
                    citation={citation}
                    onOpenEvidence={onOpenEvidence}
                  />
                ))}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
      {section.unknowns.length > 0 ? (
        <div className="unknowns">
          <strong>Unknown / Not disclosed</strong>
          <ul>
            {section.unknowns.map((unknown) => (
              <li key={unknown}>{unknown}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
