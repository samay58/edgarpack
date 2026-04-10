/** API client for the Filing Observatory endpoints. */

import type {
  CompanySummary,
  CompanyDetail,
  DiffResult,
  SectionType,
  TimelineEntry,
  SearchResult,
  StatsResponse,
  TopicsResponse,
} from "@/types/observatory";

const API_BASE =
  process.env.NEXT_PUBLIC_OBSERVATORY_API_BASE ??
  "http://127.0.0.1:8000/api/v1/observatory";

export type ApiErrorKind = "network" | "client" | "server";

export class ObservatoryApiError extends Error {
  kind: ApiErrorKind;
  status?: number;
  body?: string;

  constructor(kind: ApiErrorKind, message: string, status?: number, body?: string) {
    super(message);
    this.name = "ObservatoryApiError";
    this.kind = kind;
    this.status = status;
    this.body = body;
  }
}

async function fetchJSON<T>(path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  } catch (err) {
    throw new ObservatoryApiError(
      "network",
      "Can't reach the EdgarPack backend. Start it with `edgarpack api --port 8000`.",
    );
  }
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    const kind: ApiErrorKind = res.status >= 500 ? "server" : "client";
    const message =
      kind === "server"
        ? `Backend error (${res.status}). ${res.statusText}.`
        : `Request rejected (${res.status}). ${body || res.statusText}`;
    throw new ObservatoryApiError(kind, message, res.status, body);
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
  opts: { detail?: "full" | "sections"; sectionTypes?: SectionType[] } = {},
): Promise<DiffResult> {
  const params = new URLSearchParams({
    form_type: formType,
    detail: opts.detail ?? "full",
  });
  if (opts.sectionTypes && opts.sectionTypes.length > 0) {
    params.set("section_types", opts.sectionTypes.join(","));
  }
  return fetchJSON<DiffResult>(
    `/companies/${encodeURIComponent(ticker)}/diff?${params.toString()}`,
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
