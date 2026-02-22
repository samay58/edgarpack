import { EvidenceExplorer } from "@/components/china-lens/evidence-explorer";
import { getDocuments } from "@/lib/api-client";
import { demoEvidenceTarget } from "@/lib/sample-data";

type PageProps = {
  params: Promise<{ companyId: string }>;
};

export default async function EvidencePage({ params }: PageProps) {
  const { companyId } = await params;
  const documents = await getDocuments(companyId);

  return (
    <div className="page-stack">
      <section className="panel">
        <h2>Evidence Explorer</h2>
        <p className="muted">Open citations to jump directly to source page and snippet.</p>
      </section>
      <EvidenceExplorer documents={documents} evidenceTarget={demoEvidenceTarget} />
    </div>
  );
}
