"use client";

import type { CompanySummary } from "@/types/observatory";
import { useRouter } from "next/navigation";

export function CompanyGrid({
  companies,
}: {
  companies: CompanySummary[];
}) {
  const router = useRouter();

  return (
    <div className="obs-grid">
      {companies.map((c) => (
        <button
          key={c.cik}
          className="panel obs-card"
          onClick={() =>
            router.push(`/observatory/${encodeURIComponent(c.ticker ?? c.cik)}`)
          }
        >
          <div className="obs-card-header">
            <strong style={{ fontSize: "1.05rem" }}>
              {c.ticker ?? c.cik}
            </strong>
            <span className="obs-badge">{c.filing_count} filings</span>
          </div>
          <span className="muted" style={{ fontSize: "0.88rem" }}>
            {c.company_name}
          </span>
          <div className="obs-card-meta">
            <span>{(c.total_tokens / 1000).toFixed(0)}K tokens</span>
            <span>Latest: {c.latest_filing}</span>
          </div>
        </button>
      ))}
    </div>
  );
}
