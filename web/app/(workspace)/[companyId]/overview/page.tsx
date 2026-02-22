import Link from "next/link";

import { getDocuments } from "@/lib/api-client";

type PageProps = {
  params: Promise<{ companyId: string }>;
};

export default async function OverviewPage({ params }: PageProps) {
  const { companyId } = await params;
  const documents = await getDocuments(companyId);

  return (
    <div className="page-stack">
      <section className="panel">
        <h2>Overview</h2>
        <p className="muted">
          Primary-source workspace optimized for fast pack generation and evidence verification.
        </p>
        <div className="quick-actions">
          <Link href={`/${companyId}/packs`} className="primary-btn link-btn">
            Generate Pack
          </Link>
          <Link href={`/${companyId}/evidence`} className="secondary-btn link-btn">
            Open Evidence Explorer
          </Link>
        </div>
      </section>

      <section className="panel">
        <h3>Indexed Documents</h3>
        <ul className="doc-list">
          {documents.map((document) => (
            <li key={document.id}>
              <strong>{document.title}</strong>
              <span className="muted">
                {document.filing_date} · {document.source} · {document.pages} pages
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
