"use client";

import type {
  CompanyDetail as CompanyDetailType,
  DiffResult,
} from "@/types/observatory";
import { useRouter } from "next/navigation";

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export function CompanyDetail({
  company,
  diff,
}: {
  company: CompanyDetailType;
  diff: DiffResult | null;
}) {
  const router = useRouter();

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: 14 }}>
        <div className="row between">
          <div>
            <h2 style={{ fontSize: "1.1rem" }}>
              {company.ticker} &mdash; {company.company_name}
            </h2>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              CIK {company.cik} &middot; {company.filing_count} filings
            </span>
          </div>
          <div className="topbar-actions">
            {diff && (
              <button
                className="primary-btn"
                onClick={() =>
                  router.push(`/observatory/${company.ticker}/diff`)
                }
              >
                View diff ({pct(diff.overall_change_intensity)} changed)
              </button>
            )}
          </div>
        </div>
      </div>

      {diff && (
        <div className="panel" style={{ padding: 14 }}>
          <h3 style={{ fontSize: "0.95rem", marginBottom: 8 }}>
            Latest diff: {diff.before_date} vs {diff.after_date}
          </h3>
          <div className="obs-stat-row">
            <span className="obs-stat">
              <strong>{diff.sections_unchanged}</strong> unchanged
            </span>
            <span className="obs-stat obs-stat-modified">
              <strong>{diff.sections_modified}</strong> modified
            </span>
            <span className="obs-stat obs-stat-added">
              <strong>{diff.sections_added}</strong> added
            </span>
            <span className="obs-stat obs-stat-removed">
              <strong>{diff.sections_removed}</strong> removed
            </span>
          </div>
          <div className="obs-section-bars" style={{ marginTop: 12 }}>
            {diff.section_deltas
              .filter((d) => d.change_type !== "unchanged")
              .sort((a, b) => b.change_intensity - a.change_intensity)
              .slice(0, 8)
              .map((d) => (
                <button
                  key={d.section_id}
                  className="obs-section-bar"
                  onClick={() =>
                    router.push(
                      `/observatory/${company.ticker}/timeline/${encodeURIComponent(d.section_id)}`,
                    )
                  }
                >
                  <span className="obs-bar-title">{d.title || d.section_id}</span>
                  <span className="obs-bar-fill">
                    <span
                      className={`obs-fill obs-fill-${d.change_type}`}
                      style={{ width: pct(d.change_intensity) }}
                    />
                  </span>
                  <span className="obs-bar-pct">{pct(d.change_intensity)}</span>
                </button>
              ))}
          </div>
        </div>
      )}

      <div className="panel" style={{ padding: 14 }}>
        <h3 style={{ fontSize: "0.95rem", marginBottom: 8 }}>Filings</h3>
        <table className="obs-table">
          <thead>
            <tr>
              <th>Form</th>
              <th>Date</th>
              <th>Sections</th>
              <th>Tokens</th>
              <th>Accession</th>
            </tr>
          </thead>
          <tbody>
            {company.filings.map((f) => (
              <tr key={f.accession}>
                <td>
                  <span className="obs-badge">{f.form_type}</span>
                </td>
                <td>{f.filing_date}</td>
                <td>{f.sections_count}</td>
                <td>{(f.tokens_total / 1000).toFixed(0)}K</td>
                <td className="muted" style={{ fontSize: "0.82rem" }}>
                  {f.accession}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
