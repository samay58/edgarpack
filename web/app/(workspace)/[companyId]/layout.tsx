import { AppShell } from "@/components/china-lens/app-shell";
import { getCompanies } from "@/lib/api-client";

type LayoutProps = {
  children: React.ReactNode;
  params: Promise<{ companyId: string }>;
};

export default async function WorkspaceLayout({ children, params }: LayoutProps) {
  const { companyId } = await params;
  const companies = await getCompanies();
  const current = companies.find((company) => company.id === companyId) ?? companies[0];
  const companyLabel = current
    ? `${current.display_name_en} (${current.ticker})`
    : "China Lens Workspace";

  return (
    <AppShell companyId={companyId} companyLabel={companyLabel}>
      {children}
    </AppShell>
  );
}
