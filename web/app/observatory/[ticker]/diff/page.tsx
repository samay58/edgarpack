import Link from "next/link";
import { getDiff } from "@/lib/observatory-api";
import { DiffViewer } from "@/components/observatory/diff-viewer";

export default async function DiffPage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ form_type?: string }>;
}) {
  const { ticker } = await params;
  const { form_type } = await searchParams;
  const formType = form_type ?? "10-K";

  let diff;
  try {
    diff = await getDiff(ticker, formType);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return (
      <div className="panel" style={{ padding: 24 }}>
        <h2>Diff unavailable</h2>
        <p className="muted" style={{ marginTop: 8 }}>{msg}</p>
        <Link
          href={`/observatory/${ticker}`}
          className="secondary-btn"
          style={{ display: "inline-block", marginTop: 12 }}
        >
          Back to {ticker}
        </Link>
      </div>
    );
  }

  return <DiffViewer diff={diff} ticker={ticker} />;
}
