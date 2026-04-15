"use client";

import { useState } from "react";

import { EvidenceExplorer, type ReadingMode } from "@/components/china-lens/evidence-explorer";
import type { DocumentView, EvidenceTarget } from "@/types/china-lens";

type EvidencePageShellProps = {
  documents: DocumentView[];
  evidenceTarget?: EvidenceTarget | null;
};

export function EvidencePageShell({ documents, evidenceTarget }: EvidencePageShellProps) {
  const [readingMode, setReadingMode] = useState<ReadingMode>("en");

  return (
    <EvidenceExplorer
      documents={documents}
      evidenceTarget={evidenceTarget}
      readingMode={readingMode}
      onReadingModeChange={setReadingMode}
      isLoading={false}
    />
  );
}
