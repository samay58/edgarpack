"use client";

import { useState } from "react";
import Link from "next/link";
import type {
  DiffResult,
  ParagraphDelta,
  SectionDelta,
  SectionType,
} from "@/types/observatory";

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function sectionTypeLabel(sectionType: SectionType): string {
  return sectionType.replace(/_/g, " ");
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
      {delta.is_boilerplate && <span className="obs-subtle-tag">boilerplate</span>}
    </div>
  );
}

function SectionDetail({
  delta,
  ticker,
  hideBoilerplate,
}: {
  delta: SectionDelta;
  ticker: string;
  hideBoilerplate: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const changedParas = delta.paragraph_deltas.filter(
    (p) => p.change_type !== "unchanged" && (!hideBoilerplate || !p.is_boilerplate),
  );

  return (
    <div
      className={`panel obs-section-detail ${delta.section_type !== "prose" ? "obs-section-detail-muted" : ""}`}
    >
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
            {delta.section_type !== "prose" && (
              <span className="obs-subtle-tag" style={{ marginLeft: 8 }}>
                {sectionTypeLabel(delta.section_type)}
              </span>
            )}
          </div>
          <div className="row" style={{ gap: 12 }}>
            <span className="muted" style={{ fontSize: "0.78rem" }}>
              score {delta.interest_score.toFixed(1)}
            </span>
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
  const [sectionType, setSectionType] = useState<"all" | SectionType>("all");
  const [hideBoilerplate, setHideBoilerplate] = useState(true);

  let sections =
    filter === "changed"
      ? diff.section_deltas.filter((d) => d.change_type !== "unchanged")
      : diff.section_deltas;

  if (sectionType !== "all") {
    sections = sections.filter((d) => d.section_type === sectionType);
  }

  const sorted = [...sections].sort((a, b) => {
    if (b.interest_score !== a.interest_score) {
      return b.interest_score - a.interest_score;
    }
    return b.change_intensity - a.change_intensity;
  });

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
            aria-pressed={filter === "changed"}
          >
            Changed only
          </button>
          <button
            className={`mode-btn ${filter === "all" ? "active" : ""}`}
            onClick={() => setFilter("all")}
            aria-pressed={filter === "all"}
          >
            All sections
          </button>
          <span className="control-label" style={{ marginLeft: 8 }}>
            Type:
          </span>
          <button
            className={`mode-btn ${sectionType === "all" ? "active" : ""}`}
            onClick={() => setSectionType("all")}
            aria-pressed={sectionType === "all"}
          >
            All
          </button>
          <button
            className={`mode-btn ${sectionType === "prose" ? "active" : ""}`}
            onClick={() => setSectionType("prose")}
            aria-pressed={sectionType === "prose"}
          >
            Prose
          </button>
          <button
            className={`mode-btn ${sectionType === "financial_statement" ? "active" : ""}`}
            onClick={() => setSectionType("financial_statement")}
            aria-pressed={sectionType === "financial_statement"}
          >
            Financials
          </button>
          <button
            className={`mode-btn ${sectionType === "signature" ? "active" : ""}`}
            onClick={() => setSectionType("signature")}
            aria-pressed={sectionType === "signature"}
          >
            Signatures
          </button>
          <button
            className={`mode-btn ${sectionType === "exhibit_index" ? "active" : ""}`}
            onClick={() => setSectionType("exhibit_index")}
            aria-pressed={sectionType === "exhibit_index"}
          >
            Exhibits
          </button>
          <button
            className={`mode-btn ${hideBoilerplate ? "active" : ""}`}
            onClick={() => setHideBoilerplate((prev) => !prev)}
            aria-pressed={hideBoilerplate}
          >
            {hideBoilerplate ? "Hide boilerplate" : "Show boilerplate"}
          </button>
        </div>
      </div>

      {sorted.map((d) => (
        <SectionDetail
          key={d.section_id}
          delta={d}
          ticker={ticker}
          hideBoilerplate={hideBoilerplate}
        />
      ))}

      {sorted.length === 0 && (
        <div className="panel" style={{ padding: 24, textAlign: "center" }}>
          <span className="muted">No changed sections</span>
        </div>
      )}
    </div>
  );
}
