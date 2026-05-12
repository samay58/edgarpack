# EdgarPack Feedback Synthesis

This synthesizes repeated feedback from recent investor-style EdgarPack sessions: Cerebras, Meta, NVIDIA, Snap, Robinhood, SaaS cohort work, and Lime.

## What Is Working

EdgarPack's strongest use case is turning huge filings into clean evidence surfaces. It takes a raw EDGAR problem, which is mostly search, parsing, section drift, and token overload, and turns it into a reading problem.

That is not small. Across the recent runs, the best findings were buried in long filings:

- Lime's revenue per vehicle per day, vehicle payback, Uber dependency, going-concern warning, and city fleet-cap disclosures.
- Cerebras' OpenAI warrant, G42-to-OpenAI customer story, 20-vote Class B structure, and 81.9% S-1 rewrite.
- NVIDIA's 22% customer concentration, indirect OpenAI revenue language, H20 inventory charge, and shift to AI infrastructure wording.
- Meta's mission rewrite, Reality Labs operating drag, EU regulatory detail, and Zuckerberg key-person risk language.
- Snap's subscription pivot, unnamed AI platform partner, equity dilution risk, and unused tax asset stack.
- Robinhood's stablecoin balance-sheet disclosure, DTA valuation allowance release, Robinhood Chain, and product surface expansion.

The tool did not "think" those insights into existence. It made them findable. That is the right framing.

## The Big Product Read

EdgarPack should not become a generic finance chatbot. Its edge is primary-document work with citations.

The better product is a filing workbench for investors:

It should help a user find the right filings, build the right packs, extract financials and KPIs with period safety, normalize tables, create an evidence ledger, and draft only from cited claims.

The output should not be "here is an answer." It should be "here are the claims worth caring about, here is the evidence, here is what may be wrong, and here is where the filing itself is ambiguous."

## Repeated Frictions

Tables are still too weak. Financial tables often render as duplicated pipe text, with repeated row labels and poor column alignment. This is tolerable for narrative reading and bad for financial analysis.

Period semantics need to be stricter. A requested long-lookback period should never quietly return a recent or partial metric. Every output row should state requested period, returned fiscal year, whether it matched, and why any substitution happened.

Derived metrics need guardrails. Lime showed this clearly: computed free cash flow used the wrong capex value because annual and interim tables got crossed. If the filing has its own reconciliation, EdgarPack should prefer it or flag any disagreement loudly.

KPI discovery is useful but brittle. `which` can be slow, incomplete, or not locator-stable enough. It needs progress events, timeouts, resumability, skip reasons, and guaranteed evidence pointers.

JSON output needs to be machine-grade. If a command says `--format json`, stdout should be parseable JSON and progress logs should go to stderr.

Filing discovery needs investor logic. Users should not need to know that Shopify may require 40-F, Atlassian may require 20-F, or a company history may start in F-1 or S-1. "Give me annual evidence history" is the user intent.

S-1 support has improved, but still needs a dedicated workflow. Registration filings need interim periods, use of proceeds, debt maturity, offering blanks, related parties, cap table effects, lock-ups, and conversion terms. Those are not normal 10-K fields.

The shareable artifact path matters. Cerebras showed that exact accession pages are valuable for public threads. If packs and site output are gitignored locally, Pages deployment has to build the exact filings needed for public links.

Local runtime friction can pollute research. Sandbox or cache failures can look like EdgarPack failures unless command output is checked carefully. The tool should make healthy invocation paths obvious.

## What Would Make It Significantly Better

Investor research mode.

One command should create the skeleton of a credible research bundle: filing selections, source ledger, financial table, KPI table, key sections, red flags, and a memo outline. The bundle should be evidence-first, not prose-first.

Strict evidence mode.

No generated finding should survive without a citation. No derived metric should appear without component citations. If components come from mismatched periods or tables, the result should be blocked or marked unsafe.

Table normalizer.

Financial statements, KPI tables, debt tables, cap tables, and reconciliation tables need first-class structured extraction. This is probably the highest-leverage upgrade for investor users.

S-1 mode.

A dedicated registration workflow should surface:

- offering status and blanks
- use of proceeds
- debt maturity and going-concern language
- related-party transactions
- lock-ups
- principal stockholders
- conversion terms
- interim and annual financials
- filing-defined non-GAAP reconciliations
- changed terms across S-1 amendments

Resumable KPI discovery.

`which` should behave like a real batch job: progress, timeout, resume, per-filing status, locator guarantees, and clean JSON output.

Annual discovery mode.

`edgarpack annuals <company>` should walk annual-report history across 10-K, 20-F, 40-F, S-1, F-1, and issuer transitions. The user should not need to know the form family first.

Thread and memo export mode.

The tool should be able to create a publishable thread pack: claims, evidence links, exact accession URLs, short notes, and uncertainty flags. The writer still writes, but the evidence surface is already assembled.

Friction-to-issue loop.

When research exposes a real tool problem, EdgarPack should make it easy to capture the command, observed behavior, expected behavior, impact, and source files. The SaaS friction log is the manual version of this.

## Product North Star

EdgarPack should make primary-document research faster without making it less responsible.

The best version is not a black-box analyst. It is a source-backed research workbench that lets a user move from "I have a filing" to "I know the handful of claims that matter, every one tied to evidence, with warnings where extraction may be unsafe."

That is the wedge. Keep the tool close to the documents, make citations unavoidable, and make uncertainty visible.
