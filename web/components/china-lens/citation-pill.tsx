"use client";

import type { CitationPill } from "@/types/china-lens";

type CitationPillProps = {
  citation: CitationPill;
  onOpenEvidence: (chunkId: string) => void;
};

export function CitationPill({ citation, onOpenEvidence }: CitationPillProps) {
  return (
    <button
      type="button"
      className="citation-pill"
      onClick={() => onOpenEvidence(citation.chunk_id)}
      title={citation.citation_label}
      aria-label={`Open evidence for ${citation.citation_label}`}
    >
      p.{citation.page}
    </button>
  );
}
