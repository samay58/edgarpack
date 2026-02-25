"use client";

import { useState } from "react";
import Link from "next/link";
import type { DiffResult, SectionDelta, ParagraphDelta } from "@/types/observatory";

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function ParagraphDiff({ delta }: { delta: ParagraphDelta }) {
  if (delta.change_type === "unchanged") return null;

  return (
    <div className={`obs-para obs-para-${delta.change_type}`}>
      {delta.change_type === "removed" && delta.old_text && (
        <div className="obs-para-old">{delta.old_text}</div>
      )}
      {delta.change_type === "added" && delta.new_text && (
        <div className="obs-para-new">{delta.new_text}</div>
      )}
      {delta.change_type === "modified" && (
        <>
          {delta.old_text && (
            <div className="obs-para-old">{delta.old_text}</div>
          )}
          {delta.new_text && (
            <div className="obs-para-new">{delta.new_text}</div>
          )}
          <span className="muted" style={{ fontSize: "0.78rem" }}>
            {(delta.similarity * 100).toFixed(0)}% similar
          </span>
        </>
      )}
    </div>
  );
}

function SectionDetail({
  delta,
  ticker,
}: {
  delta: SectionDelta;
  ticker: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const changedParas = delta.paragraph_deltas.filter(
    (p) => p.change_type !== "unchanged",
  );

  return (
    <div className="panel obs-section-detail">
      <button
        className="obs-section-header"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="row between" style={{ width: "100%" }}>
          <div>
            <strong>{delta.title || delta.section_id}</strong>
            <span
              className={`obs-change-badge obs-change-${delta.change_type}`}
              style={{ marginLeft: 8 }}
            >
              {delta.change_type}
            </span>
          </div>
          <div className="row" style={{ gap: 12 }}>
            <span style={{ fontSize: "0.85rem" }}>{pct(delta.change_intensity)}</span>
            <Link
              href={`/observatory/${ticker}/timeline/${encodeURIComponent(delta.section_id)}`}
              className="secondary-btn"
              style={{ fontSize: "0.8rem", padding: "4px 8px" }}
              onClick={(e) => e.stopPropagation()}
            >
              Timeline
            </Link>
            <span style={{ fontSize: "0.85rem" }}>{expanded ? "−" : "+"}</span>
          </div>
        </div>
        {delta.change_type === "modified" && (
          <div
            className="muted"
            style={{ fontSize: "0.82rem", marginTop: 4 }}
          >
            +{delta.paragraphs_added} added, −{delta.paragraphs_removed}{" "}
            removed, ~{delta.paragraphs_modified} modified,{" "}
            {delta.paragraphs_unchanged} unchanged
          </div>
        )}
      </button>
      {expanded && changedParas.length > 0 && (
        <div className="obs-paras">
          {changedParas.map((p, i) => (
            <ParagraphDiff key={i} delta={p} />
          ))}
        </div>
      )}
    </div>
  );
}

export function DiffViewer({
  diff,
  ticker,
}: {
  diff: DiffResult;
  ticker: string;
}) {
  const [filter, setFilter] = useState<"all" | "changed">("changed");

  const sections =
    filter === "changed"
      ? diff.section_deltas.filter((d) => d.change_type !== "unchanged")
      : diff.section_deltas;

  const sorted = [...sections].sort(
    (a, b) => b.change_intensity - a.change_intensity,
  );

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: 14 }}>
        <div className="row between">
          <div>
            <h2 style={{ fontSize: "1.05rem" }}>
              {diff.company}: {diff.before_date} vs {diff.after_date}
            </h2>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              {diff.form_type} &middot; Overall change:{" "}
              {pct(diff.overall_change_intensity)}
            </span>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <div className="obs-stat-row">
              <span className="obs-stat">
                <strong>{diff.sections_unchanged}</strong> unchanged
              </span>
              <span className="obs-stat obs-stat-modified">
                <strong>{diff.sections_modified}</strong> modified
              </span>
              <span className="obs-stat obs-stat-added">
                <strong>{diff.sections_added}</strong> added
              </span>
              <span className="obs-stat obs-stat-removed">
                <strong>{diff.sections_removed}</strong> removed
              </span>
            </div>
          </div>
        </div>
        <div className="filter-controls">
          <span className="control-label">Show:</span>
          <button
            className={`mode-btn ${filter === "changed" ? "active" : ""}`}
            onClick={() => setFilter("changed")}
          >
            Changed only
          </button>
          <button
            className={`mode-btn ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
          >
            All sections
          </button>
        </div>
      </div>

      {sorted.map((d) => (
        <SectionDetail key={d.section_id} delta={d} ticker={ticker} />
      ))}

      {sorted.length === 0 && (
        <div className="panel" style={{ padding: 24, textAlign: "center" }}>
          <span className="muted">No changed sections</span>
        </div>
      )}
    </div>
  );
}
