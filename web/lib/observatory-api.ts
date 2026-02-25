/** API client for the Filing Observatory endpoints. */

import type {
  CompanySummary,
  CompanyDetail,
  DiffResult,
  TimelineEntry,
  SearchResult,
  StatsResponse,
  TopicsResponse,
} from "@/types/observatory";

const API_BASE =
  process.env.NEXT_PUBLIC_OBSERVATORY_API_BASE ??
  "http://127.0.0.1:8000/api/v1/observatory";

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export async function getCompanies(): Promise<CompanySummary[]> {
  return fetchJSON<CompanySummary[]>("/companies");
}

export async function getCompany(ticker: string): Promise<CompanyDetail> {
  return fetchJSON<CompanyDetail>(`/companies/${encodeURIComponent(ticker)}`);
}

export async function getDiff(
  ticker: string,
  formType = "10-K",
): Promise<DiffResult> {
  return fetchJSON<DiffResult>(
    `/companies/${encodeURIComponent(ticker)}/diff?form_type=${encodeURIComponent(formType)}`,
  );
}

export async function getTimeline(
  ticker: string,
  sectionId: string,
  formType = "10-K",
): Promise<TimelineEntry[]> {
  return fetchJSON<TimelineEntry[]>(
    `/companies/${encodeURIComponent(ticker)}/timeline/${encodeURIComponent(sectionId)}?form_type=${encodeURIComponent(formType)}`,
  );
}

export async function searchCorpus(
  query: string,
  opts: { topic?: string; ticker?: string; formType?: string; limit?: number } = {},
): Promise<SearchResult> {
  const params = new URLSearchParams({ q: query });
  if (opts.topic) params.set("topic", opts.topic);
  if (opts.ticker) params.set("ticker", opts.ticker);
  if (opts.formType) params.set("form_type", opts.formType);
  if (opts.limit) params.set("limit", String(opts.limit));
  return fetchJSON<SearchResult>(`/search?${params}`);
}

export async function getStats(): Promise<StatsResponse> {
  return fetchJSON<StatsResponse>("/stats");
}

export async function getTopics(): Promise<TopicsResponse> {
  return fetchJSON<TopicsResponse>("/topics");
}
