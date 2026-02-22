export type CoverageStatus = "pending" | "partial" | "complete" | "incomplete";

export type CitationPill = {
  chunk_id: string;
  doc_id: string;
  page: number;
  citation_label: string;
};

export type FindingView = {
  id: string;
  claim_text: string;
  status: "supported" | "unsupported";
  citations: CitationPill[];
  unknown_reason?: string;
};

export type PackSectionView = {
  id: string;
  title: string;
  thesis: string;
  key_points: string[];
  findings: FindingView[];
  unknowns: string[];
  coverage_status: CoverageStatus;
  updated_at: string;
};

export type PackView = {
  id: string;
  company_id: string;
  status: "queued" | "running" | "ready" | "partial" | "failed" | "canceled";
  time_range: string;
  sections: PackSectionView[];
  build_logs: string[];
};

export type EvidenceTarget = {
  chunk_id: string;
  doc_id: string;
  page: number;
  text_zh: string;
  text_en: string;
  citation_label: string;
};

export type AskAnswer = {
  text: string;
  citations: CitationPill[];
};

export type AskResponse = {
  answer: AskAnswer[];
  not_found: boolean;
  guidance: string;
};

export type CompanyView = {
  id: string;
  display_name_en: string;
  display_name_zh: string;
  ticker: string;
  exchange: string;
};

export type DocumentView = {
  id: string;
  title: string;
  filing_type: string;
  filing_date: string;
  source: string;
  pages: number;
};
