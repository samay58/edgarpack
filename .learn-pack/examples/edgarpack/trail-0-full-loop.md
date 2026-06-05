# Trail 0: Query one cited number

Time: about 12 minutes.

Start here if you are new to EdgarPack. You will run a query a few ways, then read what happened.

```bash
edgarpack query NVDA revenue --period ltm
```

That command asks for NVIDIA revenue over the trailing twelve months. The answer should be a number plus a citation marker. The marker tells you which filing data supports the number.

If `edgarpack` is not installed globally, use `uv run edgarpack` in the examples.

## Read the command first

The command has four parts:

```text
edgarpack query   NVDA   revenue   --period ltm
tool + action     who    what      when
```

`NVDA` is the company. You can also type the company name:

```bash
edgarpack query "NVIDIA" revenue --period ltm
```

Both forms should resolve to the same SEC filer. The ticker is shorter. The name is often easier when you are thinking in company names instead of symbols.

A few other examples:

```bash
edgarpack query "Apple Inc" revenue --period lfy
edgarpack query "Microsoft" revenue --period lfy
edgarpack query "Alphabet" revenue --period lfy
edgarpack query "Tesla" revenue --period lfy
```

Company-name lookup is forgiving, but it is not guesswork. If a name is ambiguous, EdgarPack should stop and ask you to be more specific. If the company is not in the SEC ticker list or the local universe, it should fail instead of choosing the nearest public company.

## Try it

Run the basic query:

```bash
edgarpack query NVDA revenue --period ltm
```

Then run the same query with the company name:

```bash
edgarpack query "NVIDIA" revenue --period ltm
```

The company line in the output should point to the same filer. That is the first thing this trail is teaching: EdgarPack resolves who you mean before it tries to answer the financial question.

Look for three things in the output:

- the revenue value;
- the period label;
- a citation marker near the value.

Now ask for the same result with the audit view:

```bash
edgarpack query NVDA revenue --period ltm --audit --show-links primary
```

The audit view shows why LTM is a calculation. You should see the current year-to-date quarter, the latest full fiscal year, and the matching year-to-date quarter from the prior year.

Then ask for the machine-readable version:

```bash
edgarpack query NVDA revenue --period ltm --format json-full
```

Search the JSON for `citation_ids`, `calculation_id`, `accession`, and `primary_document`. Those fields are the difference between "the number printed" and "the number can be checked."

Try one failure case too:

```bash
edgarpack query NVDA made_up_metric --period ltm
```

The command should stop with suggestions. It should not print a blank table and make you guess whether NVIDIA failed to report the metric.

## What happened

```text
read the command
  -> decide which company NVDA means
  -> fetch the company's reported SEC facts
  -> translate revenue into the right accounting concept
  -> turn ltm into a filing window
  -> build a cited result
  -> print the result
```

The code has more branches than this, because real filings have more branches. Start with this path.

## First, EdgarPack decides which company you meant

`NVDA` is simple, but users do not always type simple input. EdgarPack accepts tickers, CIKs, company names, and aliases from `universe.toml`.

The CLI checks the local universe before it falls back to the SEC. That matters for HKEX, SSE, and private companies. A China company should not be sent through the SEC companyfacts path by accident, and a private company should not produce a confident empty table.

For NVIDIA, identity resolves to an SEC filer. The query path then fetches companyfacts and builds a primary-document map for later citation links.

## Then it translates `revenue`

Companies use different accounting tags for revenue. One company may report `Revenues`; another may report `RevenueFromContractWithCustomerExcludingAssessedTax`. A bank will often use a different concept again.

So `revenue` is the user's word, not necessarily the filing's exact field name. EdgarPack resolves aliases, checks known metrics, checks catalog KPIs, checks company-specific KPIs found by `edgarpack which`, and accepts S-1 snapshot metric slugs for registration filers.

If the metric does not fit any of those sources, the command stops with suggestions. A missing metric is not the same as a company reporting zero.

## Then it turns `ltm` into real periods

`ltm` is not usually a single reported SEC companyfacts value. For a duration metric like revenue, EdgarPack builds it from three cited components:

```text
LTM = most recent cumulative quarter
    + latest full fiscal year
    - matching cumulative quarter from the prior year
```

Example: if the newest quarter is Q3, the current Q3 year-to-date number covers nine months. Add the last full fiscal year, then subtract the prior year's Q3 year-to-date number. The remaining window is the trailing twelve months.

This only works if the selector finds the right kind of quarter. A standalone three-month Q3 value is not the same as a year-to-date Q3 value. [Trail 3](trail-3-period-selection.md) spends a full pass on that distinction.

When EdgarPack computes LTM, the output is a derived value with component citations. If one component is missing, the result records a diagnostic instead of filling the cell with an unsupported calculation.

## The citation travels with the value

The result carries more than a number:

- company and CIK;
- form type, filing date, accession, and primary document;
- period start and period end;
- fiscal year and fiscal period;
- accounting concept and taxonomy;
- reporting currency;
- source marker and warnings;
- source URL, document URL, viewer URL, or fact anchor when available.

For SEC inline XBRL filings, EdgarPack makes one later pass to tighten links. Companyfacts tells EdgarPack which filing supplied the number. The filing HTML can also contain an inline XBRL fact id. When EdgarPack can match the fact id, the link can point to the exact tagged number in the HTML instead of only the filing page. [Trail 4](trail-4-citation-anchors.md) covers that pass.

## Printing comes last

By the time the table prints, the query result already exists. Rendering decides whether you see a table, lean JSON, full JSON, or an audit-style view. It should not decide what the number means.

That split is useful when you edit the code. If a value is wrong, start in the query layer. If the value is right but the table is awkward, start in the renderer.

## In the code

- `edgarpack/cli.py:339` builds the top-level parser. The `query` subparser starts at `edgarpack/cli.py:579`.
- `edgarpack/cli.py:2225` handles `query`. It resolves local identity, parses periods, expands presets, calls `financials()`, and chooses table or JSON output.
- `edgarpack/query/financials.py:664` is the one-company, one-period query entrypoint.
- `edgarpack/query/financials.py:696` through `edgarpack/query/financials.py:741` route HKEX and SSE identities before the SEC fallback.
- `edgarpack/query/financials.py:743` through `edgarpack/query/financials.py:759` resolve an SEC filer, fetch companyfacts, and build the primary-document map.
- `edgarpack/query/financials.py:761` through `edgarpack/query/financials.py:803` normalize and validate requested metrics.
- `edgarpack/query/periods.py:976` sends `ltm` into `_select_ltm_like()` at `edgarpack/query/periods.py:535`.
- `edgarpack/query/models.py:24` defines `CitedValue`; `edgarpack/query/models.py:155` builds the fact-anchor URL when a fact id exists.
- `edgarpack/query/render.py:140` renders the single-period query table.

For query changes, run:

```bash
scripts/symphony_quality_gate.sh
uv run --extra dev --extra china --extra sse mypy edgarpack
```

For period math, add the focused tests named in [docs/TESTING.md](../TESTING.md).
