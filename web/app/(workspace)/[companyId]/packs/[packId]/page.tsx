import { PackWorkspace } from "@/components/china-lens/pack-workspace";
import { getDocuments, getPack } from "@/lib/api-client";

type PageProps = {
  params: Promise<{ companyId: string; packId: string }>;
};

export default async function PackDetailPage({ params }: PageProps) {
  const { companyId, packId } = await params;
  const [pack, documents] = await Promise.all([getPack(packId), getDocuments(companyId)]);

  if (!pack) {
    return (
      <div className="page-stack">
        <section className="panel">
          <h2>Pack Not Available</h2>
          <p className="muted">
            The requested pack was not found in the China Lens API. Generate a new pack from the
            Pack Builder.
          </p>
        </section>
      </div>
    );
  }

  return <PackWorkspace companyId={companyId} pack={pack} documents={documents} />;
}
