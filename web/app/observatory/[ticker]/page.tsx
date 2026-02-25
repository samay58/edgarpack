import { getCompany, getDiff } from "@/lib/observatory-api";
import { CompanyDetail } from "@/components/observatory/company-detail";

export default async function CompanyPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;

  let company;
  let diff;
  try {
    company = await getCompany(ticker);
  } catch {
    return (
      <div className="panel" style={{ padding: 24 }}>
        <h2>Company not found</h2>
        <p className="muted" style={{ marginTop: 8 }}>
          No filings found for <strong>{ticker}</strong>. Run{" "}
          <code>edgarpack harvest</code> first.
        </p>
      </div>
    );
  }

  try {
    diff = await getDiff(ticker);
  } catch {
    diff = null;
  }

  return <CompanyDetail company={company} diff={diff} />;
}
