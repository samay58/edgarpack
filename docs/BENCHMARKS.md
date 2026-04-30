# Benchmarks

How much does EdgarPack actually compress a filing for downstream LLM use? This doc runs the numbers end-to-end against three real 10-Ks, reports the median, and calls out where the win is smaller than the headline.

Every figure in this doc maps to a row in `[benchmarks/efficiency-2026-04-20.json](../benchmarks/efficiency-2026-04-20.json)`. The script that produced the numbers is `[scripts/benchmark_efficiency.py](../scripts/benchmark_efficiency.py)`. Raw HTML, stripped HTML, the clean pack markdown, the Item 1A section file, and a per-filing `metrics.json` for each 10-K are committed under `[benchmarks/artifacts/](../benchmarks/artifacts/)` so a reviewer can re-count bytes or tokens without rerunning anything.

## Methodology

- Sample: the latest 10-K for NVDA, AAPL, TSLA as of 2026-04-20.
- Tokenizer: OpenAI `cl100k_base` via `tiktoken`. Claude's tokenizer produces numbers a few percent different; the shape of the claim does not change.
- Stages measured, per filing:
  1. Raw HTML as fetched from SEC EDGAR. We record both the primary filing document and the concatenation of every HTML file in the filing index (exhibits, audit letters, etc.). This dated benchmark used the combined number as the headline denominator; current builds fetch the primary document by default, so the primary-to-clean reduction is the operational comparison.
  2. iXBRL tag strip applied to the combined HTML (`[edgarpack/parse/ixbrl_strip.py](../edgarpack/parse/ixbrl_strip.py)`). Isolates how much of the historical combined-payload bloat is pure XBRL tagging.
  3. Clean `filing.full.md` produced by `[edgarpack/pack/build.py](../edgarpack/pack/build.py)`. This is what you actually hand to an LLM.
  4. Single section: `sections/10k_parti_item1a_risk_factors.md` when present.
- Wall-clock: `time.monotonic()` around each stage. Host: Apple Silicon laptop, Python 3.14, SEC disk cache warm for the fetches (typical dev loop). Reported times are indicative, not guarantees.
- Every ticker pins to its exact accession number at run time so reruns are deterministic.

## Payload reduction

Raw combined HTML (everything in the filing index) -> clean `filing.full.md`:


| Filing             | Raw bytes | Raw tokens  | Clean bytes | Clean tokens | Reduction |
| ------------------ | --------- | ----------- | ----------- | ------------ | --------- |
| NVDA 10-K (FY2026) | 2,047,880 | 595,255     | 462,187     | 102,007      | 82.9%     |
| AAPL 10-K (FY2025) | 1,707,594 | 492,156     | 301,547     | 70,835       | 85.6%     |
| TSLA 10-K (FY2025) | 2,797,342 | 812,958     | 519,395     | 113,333      | 86.1%     |
| **Median**         |           | **595,255** |             | **102,007**  | **85.6%** |


The three filings agree within three percentage points. A typical 10-K is a touch under 600k tokens of raw HTML; EdgarPack turns it into a touch over 100k tokens of clean markdown.

## Stage attribution: where does the win come from?

Raw -> iXBRL-stripped -> clean. Same three filings:


| Filing | Raw tokens | Stripped tokens   | Stripped -> clean | Clean tokens |
| ------ | ---------- | ----------------- | ----------------- | ------------ |
| NVDA   | 595,255    | 480,365 (19% cut) | 78.8% cut         | 102,007      |
| AAPL   | 492,156    | 400,089 (19% cut) | 82.3% cut         | 70,835       |
| TSLA   | 812,958    | 650,614 (20% cut) | 82.6% cut         | 113,333      |


About a fifth of the total reduction comes from iXBRL tag removal. The remaining two-thirds comes from the downstream HTML cleaning, semantic reduction, markdown rendering, and polish passes described in `[ARCHITECTURE.md](../ARCHITECTURE.md)`. If you only strip iXBRL, you are leaving most of the compression on the table.

## Context-window fit

Using cl100k tokens as the yardstick. Model windows shown are the current published maxima as of 2026-04-20; numbers shift if a provider raises them.


| Filing | Raw fits in 128k (GPT-4 Turbo)? | Raw fits in 200k (Claude 3.5 Sonnet)? | Clean fits in 128k? | Clean fits in 200k? |
| ------ | ------------------------------- | ------------------------------------- | ------------------- | ------------------- |
| NVDA   | No (595k)                       | No (595k)                             | Yes (102k)          | Yes (102k)          |
| AAPL   | No (492k)                       | No (492k)                             | Yes (71k)           | Yes (71k)           |
| TSLA   | No (813k)                       | No (813k)                             | Yes (113k)          | Yes (113k)          |


Every raw 10-K is too big for every mainstream frontier model's input window. Every clean pack fits in both, with room left over for instructions, few-shot examples, and cited responses.

## Cost illustration

Input-only cost to hand the whole filing to the model, rounded to the cent. Pricing snapshot: 2026-04-20, from each provider's public pricing page.

At **Claude 3.5 Sonnet** input ($3.00 per 1M tokens):


| Filing     | Raw cost  | Clean cost | Saved per call | Input-cost multiple |
| ---------- | --------- | ---------- | -------------- | ------------------- |
| NVDA       | $1.79     | $0.31      | $1.48          | 5.8x cheaper        |
| AAPL       | $1.48     | $0.21      | $1.26          | 6.9x cheaper        |
| TSLA       | $2.44     | $0.34      | $2.10          | 7.2x cheaper        |
| **Median** | **$1.79** | **$0.31**  | **$1.48**      | **5.8x cheaper**    |


At **GPT-4o** input ($2.50 per 1M tokens):


| Filing     | Raw cost  | Clean cost | Saved per call |
| ---------- | --------- | ---------- | -------------- |
| NVDA       | $1.49     | $0.26      | $1.23          |
| AAPL       | $1.23     | $0.18      | $1.05          |
| TSLA       | $2.03     | $0.28      | $1.75          |
| **Median** | **$1.49** | **$0.26**  | **$1.23**      |


Output tokens are not modeled. The savings are meaningful at scale (one analysis per filing across a corpus of hundreds) and modest on a per-call basis. We are not going to pretend this is a 1000x cost cut. It is a 5.8x input-cost cut on the dominant cost line when you are analyzing whole filings.

## Single-section targeting

One of the stronger intuitions for EdgarPack is that you rarely need the whole filing. If the LLM task is "summarize risk factors," you want just Item 1A.


| Filing    | Item 1A tokens | Comment                                                                |
| --------- | -------------- | ---------------------------------------------------------------------- |
| NVDA 10-K | 20,503         | Full Risk Factors section extracted cleanly.                           |
| AAPL 10-K | 143            | Only the section preamble extracted; see limitation below.             |
| TSLA 10-K | 103            | Only a forward-looking-statement stub extracted; see limitation below. |


**Honest reading:** single-section targeting is a real win *when the sectionizer matches the full section*. NVDA's sectionizer output is exactly what you want. AAPL and TSLA landed stubs because those filings use incorporation-by-reference and the section boundary detector anchored on the header line of a short preamble paragraph rather than the full multi-page body that follows. This is a known sectionizer limitation for incorporation-by-reference filers, not an LLM-facing claim you can lean on today. Full-filing compression still works; section-level compression is filer-dependent until the sectionizer learns to walk through incorporation-by-reference structures.

## Build time

Cold (`force=True`) rebuild wall-clock per filing, measured after the SEC disk cache was populated once:


| Filing | Cold build | Warm (manifest cache) |
| ------ | ---------- | --------------------- |
| NVDA   | 0.94s      | 0.00s                 |
| AAPL   | 0.92s      | 0.00s                 |
| TSLA   | 1.26s      | 0.00s                 |


Cold build is under 1.3s per filing on an Apple Silicon laptop once HTML is cached. First-ever fetch from SEC dominates any single-filing end-to-end runtime; the stated cold-build number isolates parse + polish + sectionize.

## Where the win is smaller than you think

Read this section before you paste the headline number into a deck.

- iXBRL stripping alone only accounts for about a fifth of the total token reduction. A tool that *only* strips tags leaves most of the compression on the table, but conversely, someone measuring only the `strip_ixbrl` stage would understate what EdgarPack does.
- Token counts here are cl100k. Claude's tokenizer gives slightly different numbers (single-digit percent delta in our spot checks). If you need Claude-exact costs, rerun against `anthropic-tokenizer` outputs.
- Cost savings are modest on a per-call basis. The meaningful cost leverage shows up when you run the pipeline across hundreds of filings or many round-trips per filing (chat sessions, multi-hop analysis, comps across a corpus).
- Section-level extraction is filer-dependent. It works on NVDA; it doesn't work for AAPL or TSLA today because of incorporation-by-reference. Do not promise reliable per-section targeting in marketing copy until the sectionizer handles that pattern.
- Wall-clock numbers are laptop numbers. Your mileage depends on machine and network. If you are building from a cold SEC cache the first fetch round-trip dominates everything else.
- Sample size is three filings. Reductions could swing if you add filers with lighter XBRL footprints (smaller issuers, 20-F filers, 8-Ks), though the concrete numbers for 10-Ks from large US filers cluster tightly in this run.

## Reproduction

```bash
export EDGARPACK_USER_AGENT="Your Name your.email@example.com"
uv run python scripts/benchmark_efficiency.py
```

That regenerates both the JSON under `benchmarks/efficiency-YYYY-MM-DD.json` and the per-filing artifacts under `benchmarks/artifacts/`. Pin the sample with `--tickers NVDA AAPL TSLA` (that is also the default); add others with `--tickers NVDA AAPL TSLA JPM` if you want to widen the panel.

## Changelog

- **2026-04-20**: initial run against NVDA/AAPL/TSLA latest 10-Ks. Median reduction 85.6%. Section-level targeting limitation documented for incorporation-by-reference filers.
