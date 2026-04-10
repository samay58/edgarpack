import Link from "next/link";

const stages = ["Download", "Extract", "Translate", "Summarize", "Index"];

type PageProps = {
  params: Promise<{ companyId: string }>;
};

export default async function PacksPage({ params }: PageProps) {
  const { companyId } = await params;

  return (
    <div className="page-stack">
      <section className="panel">
        <div className="row between">
          <h2>Pack Builder</h2>
          <Link href={`/${companyId}/packs/pack_demo_001`} className="primary-btn link-btn">
            Open Latest Pack
          </Link>
        </div>
        <p className="muted">Interruptible pipeline with partial results and stage-level retries.</p>
        <div className="builder-grid">
          <label>
            Company
            <input value="Tencent Holdings Limited" readOnly />
          </label>
          <label>
            Time Range
            <input value="Last annual + last 2 interim" readOnly />
          </label>
          <label>
            Translation Mode
            <input value="Key sections only" readOnly />
          </label>
          <label>
            Template
            <input value="Investor diligence" readOnly />
          </label>
        </div>
        <ol className="stage-list">
          {stages.map((stage) => (
            <li key={stage}>
              <span>{stage}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
