import { PackWorkspace } from "@/components/china-lens/pack-workspace";
import { getDocuments, getPack } from "@/lib/api-client";

type PageProps = {
  params: Promise<{ companyId: string; packId: string }>;
};

export default async function PackDetailPage({ params }: PageProps) {
  const { companyId, packId } = await params;
  const [pack, documents] = await Promise.all([getPack(packId), getDocuments(companyId)]);

  return <PackWorkspace companyId={companyId} pack={pack} documents={documents} />;
}
