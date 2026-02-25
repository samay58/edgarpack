"use client";

import { useState } from "react";
import Link from "next/link";
import type { TimelineEntry, ParagraphDelta } from "@/types/observatory";

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function EntryCard({
  entry,
  index,
}: {
  entry: TimelineEntry;
  index: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const d = entry.delta;

  if (!entry.section_found) {
    return (
      <div className="panel obs-timeline-entry obs-timeline-missing">
        <div className="obs-timeline-dot" />
        <div style={{ padding: 12 }}>
          <strong>{entry.filing_date}</strong>
          <span className="muted" style={{ marginLeft: 8 }}>
            Section not present
          </span>
        </div>
      </div>
    );
  }

  const isFirst = index === 0 || !d;

  return (
    <div className="panel obs-timeline-entry">
      <div className="obs-timeline-dot" />
      <button
        className="obs-timeline-header"
        onClick={() => !isFirst && setExpanded(!expanded)}
      >
        <div className="row between" style={{ width: "100%" }}>
          <div>
            <strong>{entry.filing_date}</strong>
            {isFirst && (
              <span className="obs-change-badge obs-change-added" style={{ marginLeft: 8 }}>
                baseline
              </span>
            )}
            {d && d.change_type === "unchanged" && (
              <span className="obs-change-badge obs-change-unchanged" style={{ marginLeft: 8 }}>
                unchanged
              </span>
            )}
            {d && d.change_type === "modified" && (
              <span className="obs-change-badge obs-change-modified" style={{ marginLeft: 8 }}>
                {pct(d.change_intensity)} changed
              </span>
            )}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <span className="muted" style={{ fontSize: "0.82rem" }}>
              {entry.tokens.toLocaleString()} tokens
            </span>
            {!isFirst && d && d.change_type === "modified" && (
              <span style={{ fontSize: "0.85rem" }}>{expanded ? "−" : "+"}</span>
            )}
          </div>
        </div>
        {d && d.change_type === "modified" && (
          <div className="muted" style={{ fontSize: "0.82rem", marginTop: 4 }}>
            +{d.paragraphs_added} added, −{d.paragraphs_removed} removed, ~
            {d.paragraphs_modified} modified
          </div>
        )}
      </button>
      {expanded && d && (
        <div className="obs-paras">
          {d.paragraph_deltas
            .filter((p: ParagraphDelta) => p.change_type !== "unchanged")
            .map((p: ParagraphDelta, i: number) => (
              <div key={i} className={`obs-para obs-para-${p.change_type}`}>
                {p.old_text && (
                  <div className="obs-para-old">{p.old_text}</div>
                )}
                {p.new_text && (
                  <div className="obs-para-new">{p.new_text}</div>
                )}
              </div>
            ))}
        </div>
      )}
      {expanded && isFirst && entry.content_preview && (
        <div className="obs-paras">
          <div className="obs-para" style={{ opacity: 0.7 }}>
            <div className="obs-para-new">{entry.content_preview}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export function TimelineView({
  entries,
  ticker,
  sectionId,
}: {
  entries: TimelineEntry[];
  ticker: string;
  sectionId: string;
}) {
  const title = entries.find((e) => e.delta)?.delta?.title ?? sectionId;

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: 14 }}>
        <div className="row between">
          <div>
            <h2 style={{ fontSize: "1.05rem" }}>
              {ticker}: {title}
            </h2>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              Section evolution across {entries.length} filings
            </span>
          </div>
          <Link
            href={`/observatory/${ticker}/diff`}
            className="secondary-btn"
          >
            View full diff
          </Link>
        </div>
      </div>

      <div className="obs-timeline">
        {entries.map((entry, i) => (
          <EntryCard key={entry.accession} entry={entry} index={i} />
        ))}
      </div>
    </div>
  );
}
