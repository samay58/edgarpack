"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { FilingText } from "@/components/observatory/filing-text";
import type {
  DiffResult,
  ParagraphDelta,
  SectionDelta,
  SectionType,
} from "@/types/observatory";

const WORD_SPLIT_PATTERN = /([A-Za-z0-9]+|[^A-Za-z0-9]+)/g;
const WORD_MATCH_PATTERN = /[a-z0-9]+/g;
const TERM_STOPWORDS = new Set([
  "the",
  "and",
  "for",
  "that",
  "this",
  "with",
  "from",
  "were",
  "have",
  "has",
  "had",
  "our",
  "their",
  "they",
  "them",
  "there",
  "into",
  "about",
  "your",
  "you",
  "which",
  "will",
  "would",
  "could",
  "should",
  "also",
  "such",
  "than",
  "then",
  "been",
  "being",
  "through",
  "under",
  "over",
  "between",
  "during",
  "each",
  "within",
  "without",
  "these",
  "those",
  "may",
  "might",
  "item",
  "report",
  "form",
  "fiscal",
  "year",
  "ended",
  "annual",
  "quarterly",
]);

function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function sectionTypeLabel(sectionType: SectionType): string {
  return sectionType.replace(/_/g, " ");
}

function normalizeWord(word: string): string {
  return word.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function wordsFromText(text: string): string[] {
  return text.toLowerCase().match(WORD_MATCH_PATTERN) ?? [];
}

function changedWordSets(
  oldText: string,
  newText: string,
): { oldOnly: Set<string>; newOnly: Set<string> } {
  const oldWords = new Set(wordsFromText(oldText));
  const newWords = new Set(wordsFromText(newText));
  const oldOnly = new Set<string>();
  const newOnly = new Set<string>();

  for (const w of oldWords) {
    if (!newWords.has(w)) oldOnly.add(w);
  }
  for (const w of newWords) {
    if (!oldWords.has(w)) newOnly.add(w);
  }
  return { oldOnly, newOnly };
}

function paragraphSignalScore(delta: ParagraphDelta): number {
  const words = Math.max(delta.old_word_count, delta.new_word_count);
  if (words <= 0 || delta.is_boilerplate) return 0;
  if (delta.change_type === "modified") {
    return words * Math.max(0, 1 - delta.similarity);
  }
  return words;
}

function renderHighlightedText(
  text: string,
  changedWords: Set<string>,
  variant: "old" | "new",
): ReactNode {
  const parts = text.match(WORD_SPLIT_PATTERN) ?? [text];
  return parts.map((part, i) => {
    const normalized = normalizeWord(part);
    if (!normalized || !changedWords.has(normalized)) {
      return (
        <span key={`${variant}-${i}`} className="obs-token-context">
          {part}
        </span>
      );
    }
    return (
      <mark
        key={`${variant}-${i}`}
        className={variant === "old" ? "obs-token-removed" : "obs-token-added"}
      >
        {part}
      </mark>
    );
  });
}

function buildSectionInsights(delta: SectionDelta): string[] {
  const signalParas = delta.paragraph_deltas.filter(
    (p) => p.change_type !== "unchanged" && !p.is_boilerplate,
  );
  if (!signalParas.length) {
    return ["No substantive edit signal (boilerplate or cosmetic changes only)."];
  }

  let wordsAdded = 0;
  let wordsRemoved = 0;
  let wordsMateriallyChanged = 0;
  let substantiveRewrites = 0;
  const addedTerms = new Map<string, number>();
  const removedTerms = new Map<string, number>();

  const accumulate = (text: string | null, bucket: Map<string, number>): void => {
    if (!text) return;
    for (const word of wordsFromText(text)) {
      if (word.length < 4 || TERM_STOPWORDS.has(word)) continue;
      bucket.set(word, (bucket.get(word) ?? 0) + 1);
    }
  };

  for (const p of signalParas) {
    if (p.change_type === "added") {
      wordsAdded += p.new_word_count;
      wordsMateriallyChanged += p.new_word_count;
      accumulate(p.new_text, addedTerms);
      continue;
    }
    if (p.change_type === "removed") {
      wordsRemoved += p.old_word_count;
      wordsMateriallyChanged += p.old_word_count;
      accumulate(p.old_text, removedTerms);
      continue;
    }
    if (p.change_type === "modified") {
      wordsAdded += p.new_word_count;
      wordsRemoved += p.old_word_count;
      wordsMateriallyChanged += Math.round(
        Math.max(p.old_word_count, p.new_word_count) * (1 - p.similarity),
      );
      if (p.similarity < 0.75) substantiveRewrites += 1;
      accumulate(p.new_text, addedTerms);
      accumulate(p.old_text, removedTerms);
    }
  }

  const insights: string[] = [];
  const netWords = wordsAdded - wordsRemoved;
  if (netWords > 80) {
    insights.push(`Disclosure expanded by ~${netWords} net words.`);
  } else if (netWords < -80) {
    insights.push(`Disclosure contracted by ~${Math.abs(netWords)} net words.`);
  }

  if (substantiveRewrites > 0) {
    const suffix = substantiveRewrites === 1 ? "" : "s";
    insights.push(`${substantiveRewrites} substantive rewrite${suffix} (similarity < 75%).`);
  } else if (wordsMateriallyChanged > 0) {
    insights.push(`~${wordsMateriallyChanged} words materially changed.`);
  }

  const emergentTerms = [...addedTerms.entries()]
    .map(([word, count]) => [word, count - (removedTerms.get(word) ?? 0)] as const)
    .filter(([, deltaCount]) => deltaCount > 1)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([word]) => word);
  if (emergentTerms.length > 0) {
    insights.push(`New emphasis: ${emergentTerms.join(", ")}.`);
  }

  return insights.slice(0, 3);
}

function ParagraphDiff({ delta }: { delta: ParagraphDelta }) {
  if (delta.change_type === "unchanged") return null;
  const oldText = delta.old_text ?? "";
  const newText = delta.new_text ?? "";
  const { oldOnly, newOnly } = changedWordSets(oldText, newText);
  const changedTerms = oldOnly.size + newOnly.size;

  return (
    <div className={`obs-para obs-para-${delta.change_type}`}>
      {delta.change_type === "removed" && delta.old_text && (
        <>
          <div className="obs-para-old">
            <FilingText text={delta.old_text}>{delta.old_text}</FilingText>
          </div>
          <div className="obs-para-meta muted">{delta.old_word_count} words removed</div>
        </>
      )}
      {delta.change_type === "added" && delta.new_text && (
        <>
          <div className="obs-para-new">
            <FilingText text={delta.new_text}>{delta.new_text}</FilingText>
          </div>
          <div className="obs-para-meta muted">{delta.new_word_count} words added</div>
        </>
      )}
      {delta.change_type === "modified" && (
        <>
          {delta.old_text && (
            <div className="obs-para-old">
              <FilingText text={delta.old_text}>
                {renderHighlightedText(delta.old_text, oldOnly, "old")}
              </FilingText>
            </div>
          )}
          {delta.new_text && (
            <div className="obs-para-new">
              <FilingText text={delta.new_text}>
                {renderHighlightedText(delta.new_text, newOnly, "new")}
              </FilingText>
            </div>
          )}
          <div className="obs-para-meta">
            <span className="muted obs-similarity">
              {(delta.similarity * 100).toFixed(0)}% similar
            </span>
            {changedTerms > 0 && (
              <span className="muted obs-similarity">{changedTerms} changed terms</span>
            )}
            {!delta.is_boilerplate && delta.similarity < 0.75 && (
              <span className="obs-subtle-tag obs-subtle-tag-inline">substantive edit</span>
            )}
          </div>
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
  focusMode,
}: {
  delta: SectionDelta;
  ticker: string;
  hideBoilerplate: boolean;
  focusMode: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const sectionContentId = `section-${delta.section_id.replace(/[^a-zA-Z0-9_-]/g, "_")}`;
  const sectionInsights = buildSectionInsights(delta);
  const changedParas = delta.paragraph_deltas.filter(
    (p) => p.change_type !== "unchanged" && (!hideBoilerplate || !p.is_boilerplate),
  );
  const focusedParas = changedParas.filter((p) => {
    if (!focusMode || p.change_type !== "modified") return true;
    return paragraphSignalScore(p) >= 10 || p.similarity < 0.9;
  });
  const hiddenLowSignalCount = changedParas.length - focusedParas.length;

  return (
    <div
      className={`panel obs-section-detail ${delta.section_type !== "prose" ? "obs-section-detail-muted" : ""}`}
    >
      <div className="obs-section-header-row">
        <button
          className="obs-section-header"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          aria-controls={sectionContentId}
        >
          <div className="obs-section-header-main">
            <div>
              <strong>{delta.title || delta.section_id}</strong>
              <span className={`obs-change-badge obs-change-${delta.change_type}`}>
                {delta.change_type}
              </span>
              {delta.section_type !== "prose" && (
                <span className="obs-subtle-tag obs-subtle-tag-inline">
                  {sectionTypeLabel(delta.section_type)}
                </span>
              )}
            </div>
            <div className="obs-section-metrics">
              <span className="muted obs-section-score">
                score {delta.interest_score.toFixed(1)}
              </span>
              <span className="obs-section-intensity">{pct(delta.change_intensity)}</span>
              <span className="obs-section-toggle">{expanded ? "−" : "+"}</span>
            </div>
          </div>
          {delta.change_type === "modified" && (
            <div className="muted obs-section-summary">
              +{delta.paragraphs_added} added, −{delta.paragraphs_removed} removed, ~
              {delta.paragraphs_modified} modified, {delta.paragraphs_unchanged} unchanged
            </div>
          )}
          <div className="obs-insight-row">
            {sectionInsights.map((insight) => (
              <span key={insight} className="obs-insight-pill">
                {insight}
              </span>
            ))}
          </div>
        </button>
        <Link
          href={`/observatory/${ticker}/timeline/${encodeURIComponent(delta.section_id)}`}
          className="secondary-btn obs-section-timeline-link"
        >
          Timeline
        </Link>
      </div>
      {expanded && changedParas.length > 0 && (
        <div id={sectionContentId} className="obs-paras">
          {focusMode && hiddenLowSignalCount > 0 && (
            <div className="obs-para">
              <div className="obs-para-meta muted">
                Focus mode hidden {hiddenLowSignalCount} low-signal paragraph
                {hiddenLowSignalCount === 1 ? "" : "s"}.
              </div>
            </div>
          )}
          {focusedParas.map((p, i) => (
            <ParagraphDiff key={i} delta={p} />
          ))}
        </div>
      )}
      {expanded && changedParas.length === 0 && (
        <div id={sectionContentId} className="obs-paras">
            <div className="obs-para">
              <div className="obs-para-meta muted">
                Only boilerplate edits in this section. Toggle Show boilerplate to inspect them.
              </div>
            </div>
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
  const [focusMode, setFocusMode] = useState(true);

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
      <div className="panel obs-panel-padded">
        <div className="row between">
          <div>
            <h2 className="obs-diff-title">
              {diff.company}: {diff.before_date} vs {diff.after_date}
            </h2>
            <span className="muted obs-meta-text">
              {diff.form_type} &middot; Overall change:{" "}
              {pct(diff.overall_change_intensity)}
            </span>
          </div>
          <div className="row obs-row-gap-sm">
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
          <span className="control-label obs-control-spacer">
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
          <button
            className={`mode-btn ${focusMode ? "active" : ""}`}
            onClick={() => setFocusMode((prev) => !prev)}
            aria-pressed={focusMode}
          >
            {focusMode ? "Focus signal" : "Show full context"}
          </button>
        </div>
      </div>

      {sorted.map((d) => (
        <SectionDetail
          key={d.section_id}
          delta={d}
          ticker={ticker}
          hideBoilerplate={hideBoilerplate}
          focusMode={focusMode}
        />
      ))}

      {sorted.length === 0 && (
        <div className="panel obs-empty-state">
          <span className="muted">No changed sections</span>
        </div>
      )}
    </div>
  );
}
