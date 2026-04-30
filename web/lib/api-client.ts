import { demoAskResponse, demoCompany, demoDocuments, demoEvidenceTarget, demoPack } from "@/lib/sample-data";
import type {
  AskResponse,
  CompanyView,
  CreatePackResponse,
  DocumentView,
  EvidenceTarget,
  PackStatusResponse,
  PackView,
} from "@/types/china-lens";

const API_BASE = process.env.NEXT_PUBLIC_CHINA_LENS_API_BASE ?? "http://127.0.0.1:8000/api/v1";
const DEMO_MODE = process.env.NEXT_PUBLIC_CHINA_LENS_DEMO === "1";

async function safeFetch<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function safeJsonRequest<T>(path: string, body: unknown): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export async function getCompanies(): Promise<CompanyView[]> {
  const companies = await safeFetch<CompanyView[]>("/companies");
  return companies ?? (DEMO_MODE ? [demoCompany] : []);
}

export async function getDocuments(companyId: string): Promise<DocumentView[]> {
  const docs = await safeFetch<DocumentView[]>(`/documents?company_id=${companyId}`);
  return docs ?? (DEMO_MODE ? demoDocuments : []);
}

export async function getPack(packId: string): Promise<PackView | null> {
  if (DEMO_MODE && packId.startsWith("pack_demo_")) {
    return demoPack;
  }
  const pack = await safeFetch<PackView>(`/packs/${packId}`);
  return pack ?? null;
}

export async function createPack(companyId: string): Promise<CreatePackResponse | null> {
  if (DEMO_MODE) {
    return { pack_id: demoPack.id, job_id: "job_demo_001", status: demoPack.status };
  }
  return safeJsonRequest<CreatePackResponse>("/packs", { company_id: companyId });
}

export async function getPackStatus(packId: string): Promise<PackStatusResponse | null> {
  if (DEMO_MODE && packId.startsWith("pack_demo_")) {
    return {
      pack_id: demoPack.id,
      job_id: "job_demo_001",
      status: "completed",
      stage: "index",
      progress_pct: 100,
      stage_progress: {
        download: 100,
        extract: 100,
        translate: 100,
        summarize: 100,
        index: 100,
      },
      cancel_requested: false,
      logs: demoPack.build_logs,
    };
  }
  return safeFetch<PackStatusResponse>(`/packs/${packId}/status`);
}

export async function resolveCitation(chunkId: string): Promise<EvidenceTarget | null> {
  const resolved = await safeJsonRequest<EvidenceTarget>("/citations/resolve", {
    chunk_id: chunkId,
  });
  return resolved ?? (DEMO_MODE ? demoEvidenceTarget : null);
}

export async function askEvidence(
  question: string,
  companyId: string,
  packId?: string,
): Promise<AskResponse> {
  const response = await safeJsonRequest<AskResponse>("/ask", {
    question,
    company_id: companyId,
    ...(packId ? { pack_id: packId } : {}),
  });
  if (response) {
    return response;
  }
  if (DEMO_MODE) {
    return demoAskResponse;
  }
  return {
    answer: [{ text: "Unable to reach China Lens API.", citations: [] }],
    not_found: true,
    guidance: "Start the API server, then retry the evidence-bounded question.",
  };
}
