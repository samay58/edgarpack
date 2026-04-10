import { getCompanies, getStats } from "@/lib/observatory-api";
import { CompanyGrid } from "@/components/observatory/company-grid";

export default async function ObservatoryHome() {
  let companies;
  let stats;
  try {
    [companies, stats] = await Promise.all([getCompanies(), getStats()]);
  } catch {
    return (
      <div className="panel obs-api-unavailable">
        <h2>Backend isn&apos;t running</h2>
        <p className="muted">
          Start it with <code>edgarpack api --port 8000</code>, then reload.
        </p>
      </div>
    );
  }

  const reg = stats.registry;

  return (
    <div className="page-stack">
      <div className="panel obs-stats-bar">
        <div className="row between">
          <div className="obs-stats-line" role="group" aria-label="Corpus statistics">
            <span>
              <strong>{reg.companies}</strong> companies
            </span>
            <span>
              <strong>{reg.total_packs}</strong> filings
            </span>
            <span>
              <strong>{stats.index.total_chunks.toLocaleString()}</strong> indexed chunks
            </span>
          </div>
          <span className="muted obs-stats-range">
            {reg.earliest_filing} to {reg.latest_filing}
          </span>
        </div>
      </div>
      <CompanyGrid companies={companies} />
    </div>
  );
}
