"use client";

import { useState } from "react";
import Link from "next/link";
import { ObservatoryApiError, searchCorpus } from "@/lib/observatory-api";
import type { SearchResult, SearchHit, TopicsResponse } from "@/types/observatory";

function Snippet({ text }: { text: string }) {
  // FTS5 uses >>> and <<< as highlight delimiters
  const parts = text.split(/(>>>|<<<)/);
  let inHighlight = false;
  return (
    <span>
      {parts.map((part, i) => {
        if (part === ">>>") {
          inHighlight = true;
          return null;
        }
        if (part === "<<<") {
          inHighlight = false;
          return null;
        }
        return inHighlight ? (
          <mark key={i} className="obs-highlight">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        );
      })}
    </span>
  );
}

function HitCard({ hit }: { hit: SearchHit }) {
  return (
    <article className="panel obs-hit">
      <div className="row between">
        <div className="row obs-hit-meta">
          <Link href={`/observatory/${hit.ticker ?? hit.cik}`} className="obs-hit-ticker">
            {hit.ticker ?? hit.cik}
          </Link>
          <span className="obs-badge">{hit.form_type}</span>
          <span className="muted obs-hit-date">{hit.filing_date}</span>
        </div>
        <span className="muted obs-hit-section">{hit.section_id}</span>
      </div>
      <div className="obs-hit-snippet">
        <Snippet text={hit.snippet} />
      </div>
      {hit.topics.length > 0 && (
        <div className="obs-tag-row" aria-label="Auto-extracted topics">
          {hit.topics.map((t) => (
            <span key={t} className="obs-topic-tag">
              {t}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

function formatSearchError(err: unknown): string {
  if (err instanceof ObservatoryApiError) return err.message;
  if (err instanceof Error) return err.message;
  return String(err);
}

export function SearchPage({ topics }: { topics: TopicsResponse | null }) {
  const [query, setQuery] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const doSearch = async (q: string, topic: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setError("");
    try {
      const data = await searchCorpus(q, { topic: topic || undefined, limit: 40 });
      setResults(data);
    } catch (e) {
      setError(formatSearchError(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-stack">
      <div className="panel obs-search-panel">
        <h2 className="obs-section-title">Cross-corpus search</h2>
        <form
          className="obs-search-form"
          onSubmit={(e) => {
            e.preventDefault();
            doSearch(query, topicFilter);
          }}
        >
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search filings (e.g. export controls, supply chain)"
            className="obs-search-input"
          />
          <button type="submit" className="primary-btn" disabled={loading}>
            {loading ? "Searching..." : "Search"}
          </button>
        </form>
        {topics && (
          <fieldset className="obs-topic-filters">
            <legend className="control-label">Topic</legend>
            <button
              type="button"
              className={`mode-btn ${!topicFilter ? "active" : ""}`}
              onClick={() => {
                setTopicFilter("");
                if (query) doSearch(query, "");
              }}
            >
              All
            </button>
            {topics.categories.map((cat) =>
              cat.topics
                .filter((t) => t.count > 0)
                .map((t) => (
                  <button
                    type="button"
                    key={t.tag}
                    className={`mode-btn ${topicFilter === t.tag ? "active" : ""}`}
                    onClick={() => {
                      setTopicFilter(t.tag);
                      if (query) doSearch(query, t.tag);
                    }}
                  >
                    {t.tag.split(":")[1]} ({t.count})
                  </button>
                )),
            )}
          </fieldset>
        )}
      </div>

      {error && (
        <div className="panel obs-error" role="alert">
          <span>{error}</span>
        </div>
      )}

      {results && (
        <>
          <div className="panel obs-results-bar">
            <div className="row between">
              <span>
                <strong>{results.total_hits}</strong> hits across{" "}
                <strong>{results.companies.length}</strong> companies
              </span>
              {results.topics_found.length > 0 && (
                <div className="obs-tag-row">
                  {results.topics_found.slice(0, 6).map((t) => (
                    <span key={t} className="obs-topic-tag">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
          {results.hits.map((hit) => (
            <HitCard key={hit.chunk_id} hit={hit} />
          ))}
        </>
      )}

      {!results && !loading && (
        <div className="panel obs-empty-state">
          <span className="muted">Search the indexed filing corpus.</span>
        </div>
      )}
    </div>
  );
}
