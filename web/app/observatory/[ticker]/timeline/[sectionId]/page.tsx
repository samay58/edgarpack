import Link from "next/link";
import { getTimeline } from "@/lib/observatory-api";
import { TimelineView } from "@/components/observatory/timeline-view";

export default async function TimelinePage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string; sectionId: string }>;
  searchParams: Promise<{ form_type?: string }>;
}) {
  const { ticker, sectionId } = await params;
  const { form_type } = await searchParams;
  const formType = form_type ?? "10-K";

  let entries;
  try {
    entries = await getTimeline(ticker, sectionId, formType);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return (
      <div className="panel" style={{ padding: 24 }}>
        <h2>Timeline unavailable</h2>
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

  return (
    <TimelineView
      entries={entries}
      ticker={ticker}
      sectionId={sectionId}
    />
  );
}
