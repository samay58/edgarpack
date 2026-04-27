# XGIMI China Annual Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make XGIMI / 688696 behave like a first-class China Lens filer for simple CLI build, query, and which flows without falling into SEC CIK resolution.

**Architecture:** Keep the first slice deterministic and citation-backed. Treat SSE annual reports as a second SSE document type, extract a small CAS fact set from primary annual-report tables, and reuse the existing HKEX pack-query path after generalizing it to non-SEC China packs.

**Tech Stack:** Python, argparse CLI, pydantic models, existing SSE pack builder, existing `financials()` query models, pytest fixtures.

---

### Task 1: Identity Routing

**Files:**
- Modify: `edgarpack/harvest/universe.py`
- Modify: `edgarpack/identity.py`
- Modify: `edgarpack/cli.py`
- Modify: `universe.toml`
- Test: `tests/test_china_identity.py`

- [ ] Add `stock_code` to `CompanySpec` and `ResolvedCompany`.
- [ ] Route `listing = "SSE"` and six-digit A-share codes to source `SSE`.
- [ ] Add XGIMI aliases: `688696`, `XGIMI`, `Chengdu XGIMI Technology Co., Ltd.`, Chinese name.
- [ ] Update CLI identity pre-pass so SSE entries return before SEC fallback.
- [ ] Test that `688696`, `XGIMI`, and the legal name resolve to source `SSE` with stock code `688696`.

### Task 2: SSE Annual Pack Shape

**Files:**
- Modify: `edgarpack/sse/sectionize_cn.py`
- Modify: `edgarpack/pack/build.py`
- Test: `tests/test_sectionize_cn.py`
- Test: `tests/test_sse_pack.py`

- [ ] Add annual-report section aliases, including `annual_s02_company_profile_key_financials`.
- [ ] Auto-detect `ANNUAL-REPORT` when the markdown contains annual-report markers.
- [ ] Pass document type into sectionization and manifest metadata.
- [ ] Keep prospectus behavior unchanged.
- [ ] Test that annual markdown gets annual section IDs and prospectus markdown still gets IPO IDs.

### Task 3: Citation-Backed CAS Fact Extraction

**Files:**
- Create: `edgarpack/sse/annual_facts.py`
- Modify: `edgarpack/pack/build.py`
- Test: `tests/test_sse_pack.py`

- [ ] Parse annual-report markdown tables for revenue, net income, operating cash flow, and R&D intensity.
- [ ] Emit `facts.json` in the existing China pack shape under taxonomy `cas`.
- [ ] Attach evidence metadata to every point: source URL, source document path, section ID, matched label, extraction method.
- [ ] Add `facts.json` to pack artifacts and keep extraction failure as a build warning rather than a crash.
- [ ] Test the generated fact values from a synthetic annual report fixture.

### Task 4: Query and CLI Surface

**Files:**
- Modify: `edgarpack/query/financials.py`
- Modify: `edgarpack/query/models.py`
- Modify: `edgarpack/cli.py`
- Test: `tests/test_china_query_sse.py`
- Test: `tests/test_cli_identity_fallthrough.py`

- [ ] Generalize `_query_hkex_pack` into a China pack query path that also discovers `packs/sse/<stock_code>/*/facts.json`.
- [ ] Preserve HKEX fixture behavior.
- [ ] Add CAS concept mapping for the extracted concepts.
- [ ] Make non-SEC citation links point at primary source URLs instead of synthesized SEC links.
- [ ] Make `edgarpack which 688696` give a China-pack metric inventory or an actionable build message, not a SEC CIK lookup.
- [ ] Test that XGIMI metrics return CAS/CNY values with source links.

### Task 5: Verification and Closeout

**Commands:**
- `uv run pytest tests/test_china_identity.py tests/test_sectionize_cn.py tests/test_sse_pack.py tests/test_china_query_sse.py tests/test_china_query_hk.py tests/test_cli_identity_fallthrough.py -q`
- `uv run ruff check edgarpack tests`
- XGIMI smoke with a real CNINFO PDF if the local PDF is available.

- [ ] Run focused tests.
- [ ] Run a real XGIMI CLI smoke if available.
- [ ] Close or update beads `edgarpack-49u` and `edgarpack-z8b`.
- [ ] Commit and push per `AGENTS.md`.
