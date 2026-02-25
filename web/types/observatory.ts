/** TypeScript types for the Filing Observatory API. */

export type CompanySummary = {
  cik: string;
  ticker: string | null;
  company_name: string;
  filing_count: number;
  latest_filing: string;
  total_tokens: number;
};

export type FilingSummary = {
  accession: string;
  form_type: string;
  filing_date: string;
  sections_count: number;
  tokens_total: number;
};

export type CompanyDetail = {
  ticker: string;
  company_name: string;
  cik: string | null;
  filing_count: number;
  filings: FilingSummary[];
};

export type ChangeType = "unchanged" | "modified" | "added" | "removed";
export type SectionType =
  | "prose"
  | "financial_statement"
  | "signature"
  | "exhibit_index";

export type ParagraphDelta = {
  change_type: ChangeType;
  old_text: string | null;
  new_text: string | null;
  similarity: number;
  old_word_count: number;
  new_word_count: number;
  is_boilerplate: boolean;
};

export type SectionDelta = {
  section_id: string;
  title: string;
  change_type: ChangeType;
  section_type: SectionType;
  paragraphs_added: number;
  paragraphs_removed: number;
  paragraphs_modified: number;
  paragraphs_unchanged: number;
  change_intensity: number;
  interest_score: number;
  paragraph_deltas: ParagraphDelta[];
};

export type DiffResult = {
  company: string;
  form_type: string;
  before_accession: string;
  before_date: string;
  after_accession: string;
  after_date: string;
  sections_unchanged: number;
  sections_modified: number;
  sections_added: number;
  sections_removed: number;
  overall_change_intensity: number;
  section_deltas: SectionDelta[];
};

export type TimelineEntry = {
  accession: string;
  filing_date: string;
  section_found: boolean;
  delta: SectionDelta | null;
  content_preview: string;
  tokens: number;
};

export type SearchHit = {
  chunk_id: string;
  section_id: string;
  accession: string;
  cik: string;
  ticker: string | null;
  company_name: string | null;
  form_type: string;
  filing_date: string;
  snippet: string;
  topics: string[];
  rank: number;
};

export type SearchResult = {
  query: string;
  total_hits: number;
  hits: SearchHit[];
  companies: string[];
  topics_found: string[];
};

export type TopicEntry = {
  tag: string;
  count: number;
};

export type TopicCategory = {
  name: string;
  description: string;
  topics: TopicEntry[];
};

export type TopicsResponse = {
  categories: TopicCategory[];
};

export type RegistryStats = {
  total_packs: number;
  companies: number;
  total_tokens: number;
  total_sections: number;
  earliest_filing: string;
  latest_filing: string;
};

export type StatsResponse = {
  registry: RegistryStats;
  index: {
    total_chunks: number;
    topics: Record<string, number>;
  };
};
