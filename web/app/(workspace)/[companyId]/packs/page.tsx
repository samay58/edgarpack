import { PackBuilder } from "@/components/china-lens/pack-builder";

type PageProps = {
  params: Promise<{ companyId: string }>;
};

export default async function PacksPage({ params }: PageProps) {
  const { companyId } = await params;

  return (
    <div className="page-stack">
      <PackBuilder companyId={companyId} />
    </div>
  );
}
