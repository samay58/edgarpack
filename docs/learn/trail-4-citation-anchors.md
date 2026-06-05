# Trail 4: Link a number back to the filing

Time: about 10 minutes.

Trail 0 showed the query path. This trail follows the source link that rides along with a result.

A companyfacts value already knows its accession and form. That is enough for a filing-level citation. EdgarPack tries to go one step tighter. When the source filing has inline XBRL, it can often build a link to the exact tagged fact in the filing HTML.

## Try it

Run a query with primary links:

```bash
edgarpack query NVDA revenue --period ltm --show-links primary --audit
```

Look for links beside the result or component citations. A strong link points to the primary filing HTML, often with a `#fact-id` anchor at the end.

Now ask for all links:

```bash
edgarpack query NVDA revenue --period ltm --show-links all --audit
```

Compare the filing link, viewer link, and primary-document link. They are not the same thing. The primary-document anchor is the one EdgarPack works hardest to tighten.

## Why there is a second pass

Companyfacts gives EdgarPack the number and the accession. It does not give a browser anchor into the original HTML.

Inline XBRL filings can contain tags like this:

```html
<ix:nonFraction name="us-gaap:Revenues" id="f-47">60,922</ix:nonFraction>
```

If EdgarPack can match the query value to that inline fact, it can link to:

```text
.../primary-document.htm#f-47
```

That is why `financials()` enriches fact ids after it has already built the query result. Doing it earlier would fetch filing HTML value by value. The current path fetches once per unique accession in the result.

For an LTM result, that usually means three filing fetches: the recent cumulative quarter, the latest full fiscal year, and the prior-year matching quarter.

## Collect the accessions

The enrichment pass first walks the `QueryResult` and collects accession numbers. It handles both scalar values and series results. For derived values, it walks into the components, because each component can come from a different filing.

The output is a set, so duplicate accessions are removed before any HTTP calls happen.

## Parse inline XBRL facts

For each accession, EdgarPack fetches the primary filing HTML through the normal cached filing path. It then scans `<ix:nonFraction>` tags and stores a map:

```text
(concept_without_taxonomy_prefix, scaled_numeric_value) -> fact_id
```

The parser reads optional `scale` and `sign` attributes. It strips commas, handles parentheses, applies scale, and treats the XBRL `sign` attribute as authoritative when present.

The `(concept, value)` pair is a practical lookup key inside one filing. EdgarPack does not run a full XBRL context engine here. If the same concept and value appear twice, EdgarPack keeps the first occurrence, which normally favors the financial statement row over a repeated note disclosure.

## Write fact ids back onto cited values

After parsing, EdgarPack walks the result again. For each `CitedValue`, it strips the taxonomy prefix from the concept and looks up `(concept, value)` in the fact-id map for that accession.

When the lookup succeeds, `cited.fact_id` is filled. When it fails, the value stays cited, but the URL falls back to a less precise link.

## URL fallback order

`CitedValue` exposes several useful URLs:

- `filing_url`: the SEC filing index page.
- `concept_url`: the SEC companyconcept API URL for the concept history, when the concept is a normal taxonomy tag.
- `viewer_url`: the SEC Inline XBRL Viewer URL, when a primary document is available.
- `document_url`: the primary HTML document with a text-fragment fallback.
- `anchor_url`: the primary HTML document with `#fact_id`, when the fact id exists.

`anchor_url` is the tightest link. If there is no fact id, it falls back to `document_url`. If there is no primary document, the renderer can still show filing-level context.

That distinction matters when you review output. A filing-level URL is still a citation, but it is not the same quality as a fact anchor.

## In the code

- `edgarpack/query/financials.py:1102` through `edgarpack/query/financials.py:1107` run the enrichment pass after the `QueryResult` is built.
- `edgarpack/query/financials.py:244` collects accessions from scalar, series, and derived values.
- `edgarpack/query/financials.py:208` fetches filing HTML and parses fact ids for each accession.
- `edgarpack/query/financials.py:261` writes fact ids back into cited values.
- `edgarpack/query/periods.py:73` parses inline XBRL facts into `(concept, value) -> fact_id`.
- `edgarpack/query/periods.py:39` parses displayed numbers, including scale and sign handling.
- `edgarpack/query/periods.py:116` looks up a fact id for one cited value.
- `edgarpack/query/models.py:24` defines the citation fields on `CitedValue`.
- `edgarpack/query/models.py:82` through `edgarpack/query/models.py:169` define filing, concept, viewer, document, and anchor URLs.
- `edgarpack/query/render.py:140` chooses how those links appear in the single-period query table.
