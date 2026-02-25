"use client";

import { useState, useCallback } from "react";
import Link from "next/link";
import type {
  SearchResult,
  SearchHit,
  TopicsResponse,
} from "@/types/observatory";

const API_BASE =
  process.env.NEXT_PUBLIC_OBSERVATORY_API_BASE ??
  "http://127.0.0.1:8000/api/v1/observatory";

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
    <div className="panel obs-hit">
      <div className="row between">
        <div className="row" style={{ gap: 6 }}>
          <Link
            href={`/observatory/${hit.ticker ?? hit.cik}`}
            className="obs-hit-ticker"
          >
            {hit.ticker ?? hit.cik}
          </Link>
          <span className="obs-badge">{hit.form_type}</span>
          <span className="muted" style={{ fontSize: "0.82rem" }}>
            {hit.filing_date}
          </span>
        </div>
        <span className="muted" style={{ fontSize: "0.78rem" }}>
          {hit.section_id}
        </span>
      </div>
      <div className="obs-hit-snippet">
        <Snippet text={hit.snippet} />
      </div>
      {hit.topics.length > 0 && (
        <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
          {hit.topics.map((t) => (
            <span key={t} className="obs-topic-tag">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function SearchPage({
  topics,
}: {
  topics: TopicsResponse | null;
}) {
  const [query, setQuery] = useState("");
  const [topicFilter, setTopicFilter] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const doSearch = useCallback(
    async (q: string, topic: string) => {
      if (!q.trim()) return;
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({ q });
        if (topic) params.set("topic", topic);
        params.set("limit", "40");
        const res = await fetch(`${API_BASE}/search?${params}`);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const data = (await res.json()) as SearchResult;
        setResults(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: 14 }}>
        <h2 style={{ fontSize: "1.05rem", marginBottom: 8 }}>
          Cross-corpus search
        </h2>
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
            placeholder="Search filings... (e.g., export controls, supply chain)"
            style={{ flex: 1 }}
          />
          <button type="submit" className="primary-btn" disabled={loading}>
            {loading ? "Searching..." : "Search"}
          </button>
        </form>
        {topics && (
          <div className="filter-controls" style={{ marginTop: 8 }}>
            <span className="control-label">Topic:</span>
            <button
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
          </div>
        )}
      </div>

      {error && (
        <div className="panel" style={{ padding: 14 }}>
          <span style={{ color: "var(--warning)" }}>{error}</span>
        </div>
      )}

      {results && (
        <>
          <div className="panel" style={{ padding: 10 }}>
            <div className="row between">
              <span style={{ fontSize: "0.9rem" }}>
                <strong>{results.total_hits}</strong> hits across{" "}
                <strong>{results.companies.length}</strong> companies
              </span>
              {results.topics_found.length > 0 && (
                <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
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
        <div
          className="panel"
          style={{ padding: 40, textAlign: "center" }}
        >
          <span className="muted">
            Search across all indexed filings. Try &quot;export controls&quot;, &quot;cybersecurity&quot;, or &quot;supply chain&quot;.
          </span>
        </div>
      )}
    </div>
  );
}
