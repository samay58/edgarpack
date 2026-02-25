import { getCompanies, getStats } from "@/lib/observatory-api";
import { CompanyGrid } from "@/components/observatory/company-grid";

export default async function ObservatoryHome() {
  let companies;
  let stats;
  try {
    [companies, stats] = await Promise.all([getCompanies(), getStats()]);
  } catch {
    return (
      <div className="panel" style={{ padding: 24 }}>
        <h2>API unavailable</h2>
        <p className="muted" style={{ marginTop: 8 }}>
          Start the backend with{" "}
          <code>edgarpack api --port 8000</code> and ensure packs are
          harvested.
        </p>
      </div>
    );
  }

  const reg = stats.registry;

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: 14 }}>
        <div className="row between">
          <div>
            <span style={{ fontSize: "0.9rem" }}>
              <strong>{reg.companies}</strong> companies
            </span>
            <span className="muted" style={{ margin: "0 8px" }}>|</span>
            <span style={{ fontSize: "0.9rem" }}>
              <strong>{reg.total_packs}</strong> filings
            </span>
            <span className="muted" style={{ margin: "0 8px" }}>|</span>
            <span style={{ fontSize: "0.9rem" }}>
              <strong>{stats.index.total_chunks.toLocaleString()}</strong> indexed
              chunks
            </span>
          </div>
          <span className="muted" style={{ fontSize: "0.82rem" }}>
            {reg.earliest_filing} to {reg.latest_filing}
          </span>
        </div>
      </div>
      <CompanyGrid companies={companies} />
    </div>
  );
}
