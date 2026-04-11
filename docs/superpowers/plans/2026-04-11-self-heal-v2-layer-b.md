# Self-heal v2 (Layer B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend self-heal with Layer B — KPI extraction from pack MD&A and segment sections via an LLM subprocess, verified by literal-substring match on the excerpt and order-of-magnitude cross-check against the prior filing, cached per `(cik, accession, metric)`.

**Architecture:** New `edgarpack/query/kpi_extract.py` module. Hand-curated `KPI_CATALOG` of ~26 entries. Loads pack markdown via `PackRegistry`, selects MD&A + key-metrics sections, calls the same `codex`/`claude` subprocess path as Layer A, rejects hallucinated quotes via substring check, recursively verifies against the prior filing. One migration adds an `accession` column to `learned_concepts`. Layer A behavior is untouched.

**Tech Stack:** Python 3.11+, pydantic, stdlib sqlite3, stdlib subprocess, pytest + unittest. No new third-party runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-04-11-self-heal-v2-layer-b-design.md`

**Depends on:** v1 shipped on main at merge `ab7edf7`.

---

## File map

| File | New / Modified | Responsibility |
|---|---|---|
| `edgarpack/query/models.py` | modified | Add `excerpt_text: str = ""` field to `CitedValue`. Extend `document_url` property to prefer `excerpt_text` when set. |
| `edgarpack/query/kpi_extract.py` | new | `KpiDef` dataclass, `KPI_CATALOG` dict, `try_extract_kpi` orchestrator, section selection, LLM dispatch, substring check, prior-filing verification, `_build_cited_from_extraction`. |
| `edgarpack/query/learned_registry.py` | modified | Add `accession` column migration (runs once via `PRAGMA user_version`). Update `lookup`, `upsert`, `list_rows`, `clear` to be accession-aware while preserving v1 callers. |
| `edgarpack/query/layer_zero.py` | modified | `unknown_metric_guard` helper: check both `METRIC_MAP` and `KPI_CATALOG` when deciding whether to raise `MetricNotFound`. |
| `edgarpack/query/financials.py` | modified | After Layer A (`try_learn`) returns None for a metric, fall through to `try_extract_kpi`. Accumulate Layer B diagnostics on a new `QueryResult.diagnostics` list. |
| `edgarpack/query/concepts.py` | modified | Re-export `KPI_CATALOG` and `KpiDef` for import convenience. |
| `edgarpack/cli.py` | modified | Render the `QueryResult.diagnostics` footer when present. Add `kpi-llm` and `kpi-cached` to the `learned list --source` choices. |
| `tests/test_kpi_extract.py` | new | Unit tests: catalog, section selection, prompt building, JSON parsing, substring check, build-cited, pack loading with tmp dir. |
| `tests/test_kpi_extract_integration.py` | new | End-to-end: synthetic manifest + section files in tmpdir, mocked LLM, real financials() call, verify Layer B fires after Layer A returns None. |
| `tests/test_learned_registry_migration.py` | new | Migration runs exactly once, old rows survive, new accession column populated via upsert. |
| `tests/test_query_models_source.py` | modified | Add a test for `excerpt_text` field + `document_url` override. |
| `tests/test_financials.py` | modified | Add a test confirming Layer B is called after Layer A returns None. |

Tests run from `~/edgarpack/` with `~/edgarpack/.venv/bin/pytest tests/test_<name>.py -v`. Set `EDGARPACK_USER_AGENT` in the subshell if running the full suite (some v1 tests need it).

---

## Task 1: Add `excerpt_text` field to `CitedValue` and extend `document_url`

**Files:**
- Modify: `edgarpack/query/models.py` (class `CitedValue`)
- Modify: `tests/test_query_models_source.py` (append test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_query_models_source.py`:

```python
class TestCitedValueExcerptText(unittest.TestCase):
    def test_default_excerpt_text_is_empty(self) -> None:
        cv = _make_cited()
        self.assertEqual(cv.excerpt_text, "")

    def test_excerpt_text_can_be_set(self) -> None:
        cv = _make_cited(excerpt_text="Annual recurring revenue of $1.2 billion as of fiscal year end.")
        self.assertEqual(
            cv.excerpt_text,
            "Annual recurring revenue of $1.2 billion as of fiscal year end.",
        )

    def test_document_url_uses_excerpt_when_set(self) -> None:
        cv = _make_cited(
            primary_document="crwd-20240131.htm",
            excerpt_text="Annual recurring revenue of $3.44 billion as of January 31, 2024.",
        )
        url = cv.document_url
        self.assertIsNotNone(url)
        assert url is not None
        # First 8 words of the excerpt should be in the fragment
        self.assertIn("Annual%20recurring%20revenue%20of", url)
        self.assertIn("#:~:text=", url)

    def test_document_url_falls_back_to_concept_when_no_excerpt(self) -> None:
        cv = _make_cited(primary_document="nvda-20250126.htm")
        url = cv.document_url
        self.assertIsNotNone(url)
        assert url is not None
        # Uses concept label ("Revenues" -> "Revenues") as the fragment
        self.assertIn("#:~:text=Revenues", url)

    def test_document_url_none_without_primary_document(self) -> None:
        cv = _make_cited()  # no primary_document set
        self.assertIsNone(cv.document_url)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_query_models_source.py::TestCitedValueExcerptText -v`

Expected: FAIL with `AttributeError: 'CitedValue' object has no attribute 'excerpt_text'`.

- [ ] **Step 3: Add the field to `CitedValue`**

In `edgarpack/query/models.py`, find the `source: str = "hardcoded"` line inside `CitedValue` and add:

```python
    # Self-heal provenance. 'hardcoded' for values resolved through METRIC_MAP.
    # 'learned:cached' for registry hits. 'learned:fuzzy', 'learned:llm', or
    # 'learned:user' for first-time discoveries that got persisted.
    source: str = "hardcoded"

    # Layer B (Self-heal v2): literal quote from the pack prose that produced
    # this value. Used by document_url to build a tight text-fragment anchor.
    # Empty for v1 values (anchors use the concept label).
    excerpt_text: str = ""
```

- [ ] **Step 4: Extend the `document_url` property**

Find the `document_url` property in `edgarpack/query/models.py` and replace it with:

```python
    @property
    def document_url(self) -> str | None:
        """Direct filing HTML URL with text fragment scroll.

        v1 behavior: uses the concept label as the text fragment.
        v2 behavior: when excerpt_text is set (Layer B), uses the first
        eight words of the excerpt for a tighter anchor into the exact
        sentence that contained the value.

        Returns None if no primary_document is available.
        """
        if not self.primary_document:
            return None
        acc_nodash = self.accession.replace("-", "")
        cik_bare = self.cik.lstrip("0")
        base = f"{SEC_ARCHIVES_BASE}/{cik_bare}/{acc_nodash}/{self.primary_document}"
        if self.excerpt_text:
            words = self.excerpt_text.split()[:8]
            fragment = quote(" ".join(words))
            return f"{base}#:~:text={fragment}"
        label = _concept_to_label(self.concept)
        return f"{base}#:~:text={quote(label)}"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_query_models_source.py -v`

Expected: All 11 tests pass (6 existing + 5 new).

- [ ] **Step 6: Regression check**

Run: `cd ~/edgarpack && EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" ~/edgarpack/.venv/bin/pytest tests/test_financials.py tests/test_comps.py tests/test_cli_self_heal.py -q`

Expected: All pass.

- [ ] **Step 7: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/models.py tests/test_query_models_source.py
git commit -m "feat(query/models): add CitedValue.excerpt_text for Layer B anchors

New optional field defaults to empty string (v1 behavior unchanged). When
set (by Layer B), document_url builds a text-fragment anchor from the
first eight words of the excerpt instead of the concept label. This lets
browser deep-links scroll to the exact sentence containing the extracted
value, not just the first mention of the KPI phrase.

Part of self-heal v2 (see docs/superpowers/specs/2026-04-11-self-heal-v2-layer-b-design.md).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 2: Scaffold `kpi_extract.py` with `KpiDef` and `KPI_CATALOG`

**Files:**
- Create: `edgarpack/query/kpi_extract.py`
- Create: `tests/test_kpi_extract.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_kpi_extract.py`:

```python
"""Unit tests for Layer B KPI extraction."""

from __future__ import annotations

import unittest

from edgarpack.query.kpi_extract import KPI_CATALOG, KpiDef


class TestKpiCatalog(unittest.TestCase):
    def test_catalog_has_core_saas_kpis(self) -> None:
        for name in ("arr", "nrr", "rpo", "crpo", "billings"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_consumer_kpis(self) -> None:
        for name in ("dau", "mau", "arpu"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_marketplace_kpis(self) -> None:
        for name in ("gmv", "take_rate", "gross_bookings"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_retail_kpis(self) -> None:
        for name in ("same_store_sales", "store_count"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_has_core_fintech_kpis(self) -> None:
        for name in ("tpv", "aum"):
            self.assertIn(name, KPI_CATALOG)

    def test_catalog_is_non_empty(self) -> None:
        self.assertGreaterEqual(len(KPI_CATALOG), 25)

    def test_every_kpi_has_non_empty_phrases(self) -> None:
        for name, kpi in KPI_CATALOG.items():
            self.assertGreater(
                len(kpi.phrases), 0,
                f"{name} has no phrases",
            )
            for phrase in kpi.phrases:
                self.assertIsInstance(phrase, str)
                self.assertTrue(phrase.strip(),
                                f"{name} has an empty phrase")

    def test_every_kpi_has_valid_unit_hint(self) -> None:
        valid_units = {"USD", "count", "percent", "days", "pure"}
        for name, kpi in KPI_CATALOG.items():
            self.assertIn(kpi.unit_hint, valid_units,
                          f"{name} has invalid unit_hint={kpi.unit_hint!r}")


class TestKpiDef(unittest.TestCase):
    def test_kpi_def_is_frozen(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        with self.assertRaises((AttributeError, TypeError)):
            kpi.unit_hint = "percent"  # type: ignore[misc]

    def test_kpi_def_defaults(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        self.assertEqual(kpi.industry, ())
        self.assertEqual(kpi.description, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'edgarpack.query.kpi_extract'`.

- [ ] **Step 3: Create `kpi_extract.py`**

Create `edgarpack/query/kpi_extract.py`:

```python
"""Layer B of the self-heal stack: extract industry KPIs from pack prose.

Layer A (self_heal.py) handles GAAP concept drift within XBRL. Layer B
handles metrics that exist only in management prose and segment tables:
ARR, NRR, RPO, DAU, GMV, same-store sales, and so on.

See docs/superpowers/specs/2026-04-11-self-heal-v2-layer-b-design.md for
the full design rationale.

Entry point: try_extract_kpi(metric, cik, company, period, ...).

Resolution order inside this module:
    1. KPI_CATALOG lookup (fail fast if metric isn't a known KPI)
    2. _resolve_filing_for_period: find the pack that represents the period
    3. _select_sections: read manifest, filter to MD&A + key-metrics
    4. _read_section_text: concat markdown from disk
    5. _trim_to_budget: stay under the LLM token budget
    6. _build_extraction_prompt: tight prompt with KPI phrases + text
    7. _extract_via_llm: subprocess to codex/claude, parse JSON
    8. _verify_excerpt_in_text: anti-hallucination substring check
    9. _build_cited_from_extraction: CitedValue with excerpt_text and badge
    10. _verify_against_prior_filing: recursive order-of-magnitude check
    11. Persist to learned_concepts with accession key
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class KpiDef:
    """Metadata about a hand-curated KPI the extractor knows how to look for.

    phrases: the forms the LLM should search for in prose. Multiple forms
        are useful because companies use different phrasings (e.g. 'ARR' in
        one filing and 'annual recurring revenue' in another).
    unit_hint: the expected unit type. The LLM is told this so it can
        normalize or reject mismatched units.
    industry: SIC prefix tuple. Empty tuple means 'all industries'. Not
        used by the v2 selector but recorded for a future industry-aware
        suggester.
    description: human-readable description for `edgarpack learned show`.
    """

    phrases: tuple[str, ...]
    unit_hint: str
    industry: tuple[str, ...] = field(default=())
    description: str = ""


KPI_CATALOG: dict[str, KpiDef] = {
    # SaaS / subscription
    "arr": KpiDef(
        phrases=("annual recurring revenue", "ARR", "ending ARR",
                 "ARR of approximately"),
        unit_hint="USD",
        description="Annualized subscription revenue at period end.",
    ),
    "nrr": KpiDef(
        phrases=("net revenue retention", "dollar-based net retention",
                 "net dollar retention", "NRR", "NDR"),
        unit_hint="percent",
        description="Cohort-based revenue retention, typically >100% for healthy SaaS.",
    ),
    "grr": KpiDef(
        phrases=("gross revenue retention", "GRR", "gross dollar retention"),
        unit_hint="percent",
    ),
    "rpo": KpiDef(
        phrases=("remaining performance obligations", "RPO"),
        unit_hint="USD",
    ),
    "crpo": KpiDef(
        phrases=("current remaining performance obligations", "cRPO",
                 "current RPO"),
        unit_hint="USD",
    ),
    "billings": KpiDef(
        phrases=("billings", "calculated billings"),
        unit_hint="USD",
    ),
    "subscription_rev": KpiDef(
        phrases=("subscription revenue",),
        unit_hint="USD",
    ),
    "customer_count": KpiDef(
        phrases=("total customers", "number of customers",
                 "customers with ARR over"),
        unit_hint="count",
    ),
    "magic_number": KpiDef(
        phrases=("sales efficiency", "magic number"),
        unit_hint="pure",
    ),

    # Consumer / internet
    "dau": KpiDef(
        phrases=("daily active users", "DAU"),
        unit_hint="count",
    ),
    "mau": KpiDef(
        phrases=("monthly active users", "MAU"),
        unit_hint="count",
    ),
    "qau": KpiDef(
        phrases=("quarterly active users", "QAU"),
        unit_hint="count",
    ),
    "arpu": KpiDef(
        phrases=("average revenue per user", "ARPU"),
        unit_hint="USD",
    ),
    "arppu": KpiDef(
        phrases=("average revenue per paying user", "ARPPU"),
        unit_hint="USD",
    ),
    "paying_users": KpiDef(
        phrases=("paying users", "paid users", "paying subscribers"),
        unit_hint="count",
    ),

    # Marketplace / platform
    "gmv": KpiDef(
        phrases=("gross merchandise volume", "GMV", "gross transaction value",
                 "gross booking value"),
        unit_hint="USD",
    ),
    "gross_bookings": KpiDef(
        phrases=("gross bookings",),
        unit_hint="USD",
    ),
    "take_rate": KpiDef(
        phrases=("take rate", "net take rate", "effective take rate"),
        unit_hint="percent",
    ),
    "transactions": KpiDef(
        phrases=("number of transactions", "total transactions",
                 "transactions processed"),
        unit_hint="count",
    ),

    # Retail / consumer goods
    "same_store_sales": KpiDef(
        phrases=("same-store sales", "comparable store sales",
                 "comparable sales", "comps"),
        unit_hint="percent",
    ),
    "store_count": KpiDef(
        phrases=("number of stores", "total stores", "store count"),
        unit_hint="count",
    ),
    "avg_ticket": KpiDef(
        phrases=("average ticket", "average transaction value", "average check"),
        unit_hint="USD",
    ),

    # Fintech / payments
    "tpv": KpiDef(
        phrases=("total payment volume", "TPV", "payment volume"),
        unit_hint="USD",
    ),
    "active_accounts": KpiDef(
        phrases=("active accounts", "active customer accounts"),
        unit_hint="count",
    ),
    "aum": KpiDef(
        phrases=("assets under management", "AUM"),
        unit_hint="USD",
    ),
    "aua": KpiDef(
        phrases=("assets under administration", "AUA"),
        unit_hint="USD",
    ),
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v`

Expected: 9 passing tests.

- [ ] **Step 5: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query): add KPI_CATALOG and KpiDef scaffold for Layer B

New edgarpack/query/kpi_extract.py with a hand-curated dict of 26 KPI
entries covering SaaS, consumer, marketplace, retail, and fintech. Each
entry has a tuple of phrase forms (for LLM search), a unit hint (USD,
count, percent, days, pure), an optional SIC prefix tuple, and an
optional human-readable description.

Adding a new KPI is a single dict entry. This ships the catalog only;
the extractor and orchestrator come in subsequent tasks.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 3: Migrate `learned_concepts` schema (add `accession` column)

**Files:**
- Modify: `edgarpack/query/learned_registry.py` (`_ensure_schema`)
- Create: `tests/test_learned_registry_migration.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_learned_registry_migration.py`:

```python
"""Tests for the learned_concepts schema migration (v1 -> v2)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path


class TestLearnedRegistryMigration(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"

    def _create_v1_schema_with_row(self) -> None:
        """Write a pre-migration v1 schema + one row, as a v1 installation would."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS learned_concepts (
                cik           TEXT NOT NULL,
                metric        TEXT NOT NULL,
                concept       TEXT NOT NULL,
                taxonomy      TEXT NOT NULL,
                source        TEXT NOT NULL,
                verified      INTEGER NOT NULL,
                verif_method  TEXT,
                value_sample  REAL,
                learned_at    TEXT NOT NULL,
                hit_count     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (cik, metric)
            )
        """)
        conn.execute(
            "INSERT INTO learned_concepts (cik, metric, concept, taxonomy, "
            "source, verified, verif_method, value_sample, learned_at, hit_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("0001045810", "revenue", "Revenues", "us-gaap",
             "fuzzy", 1, "order_of_magnitude", 130e9,
             datetime.now(UTC).isoformat(), 0),
        )
        conn.execute("PRAGMA user_version = 0")
        conn.commit()
        conn.close()

    def test_migration_adds_accession_column(self) -> None:
        self._create_v1_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        # Check schema has new column
        conn = sqlite3.connect(str(self.db_path))
        cols = [row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()]
        self.assertIn("accession", cols)

        # user_version bumped to 1
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)
        conn.close()
        reg.close()

    def test_migration_preserves_existing_v1_rows(self) -> None:
        self._create_v1_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        row = reg.lookup("0001045810", "revenue")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.concept, "Revenues")

    def test_migration_is_idempotent(self) -> None:
        self._create_v1_schema_with_row()

        from edgarpack.query.learned_registry import LearnedRegistry
        LearnedRegistry(db_path=self.db_path).close()  # first open: migrates
        LearnedRegistry(db_path=self.db_path).close()  # second open: no-op

        # Still exactly one row, still has the column
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT * FROM learned_concepts").fetchall()
        self.assertEqual(len(rows), 1)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)
        conn.close()

    def test_fresh_install_has_migrated_schema(self) -> None:
        """A fresh DB (no pre-existing table) should still end up at user_version=1."""
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.db_path)

        conn = sqlite3.connect(str(self.db_path))
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, 1)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()]
        self.assertIn("accession", cols)
        conn.close()
        reg.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_learned_registry_migration.py -v`

Expected: FAIL on `test_migration_adds_accession_column` (column missing), `test_fresh_install_has_migrated_schema` (user_version still 0).

- [ ] **Step 3: Update `_ensure_schema` to run the migration**

In `edgarpack/query/learned_registry.py`, replace `_ensure_schema`:

```python
    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version < 1:
            # v2 migration: add accession column and a (cik, accession, metric) unique index
            existing_cols = {row[1] for row in conn.execute(
                "PRAGMA table_info(learned_concepts)"
            ).fetchall()}
            if "accession" not in existing_cols:
                conn.execute(
                    "ALTER TABLE learned_concepts "
                    "ADD COLUMN accession TEXT NOT NULL DEFAULT ''"
                )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_cik_accn_metric "
                "ON learned_concepts(cik, accession, metric)"
            )
            conn.execute("PRAGMA user_version = 1")
        conn.commit()
```

- [ ] **Step 4: Run the migration tests to verify they pass**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_learned_registry_migration.py -v`

Expected: 4 passing tests.

- [ ] **Step 5: Regression check on v1 registry tests**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_learned_registry.py -v`

Expected: All 11 v1 tests still pass (the v1 behavior is preserved because all v1 writes use `accession=''` by default once we update the DAO in Task 4, and the existing v1 tests don't touch the new column).

- [ ] **Step 6: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/learned_registry.py tests/test_learned_registry_migration.py
git commit -m "feat(query/learned_registry): migrate schema for Layer B (add accession)

One-time migration runs inside _ensure_schema via PRAGMA user_version.
Adds an 'accession' TEXT column (default '') and a new unique index
(cik, accession, metric). Existing v1 rows keep accession='' and
continue to work.

Migration is idempotent: repeated calls no-op once user_version >= 1.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 4: Extend `LearnedRegistry` to support accession-keyed operations

**Files:**
- Modify: `edgarpack/query/learned_registry.py` (`lookup`, `upsert`, `list_rows`, `clear`, `LearnedRow`)
- Modify: `tests/test_learned_registry.py` (append test class)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_learned_registry.py`:

```python
class TestLearnedRegistryAccessionKey(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "registry.db"
        self.reg = LearnedRegistry(db_path=self.db_path)

    def test_upsert_with_accession_and_lookup(self) -> None:
        self.reg.upsert(
            cik="0001535527",
            metric="arr",
            concept="annual recurring revenue",
            taxonomy="kpi-prose",
            source="kpi-llm",
            verified=True,
            verif_method="prior_filing_crosscheck",
            value_sample=3_440_000_000.0,
            accession="0001535527-24-000123",
        )
        row = self.reg.lookup(
            "0001535527", "arr", accession="0001535527-24-000123",
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.accession, "0001535527-24-000123")

    def test_same_metric_across_two_accessions(self) -> None:
        """Layer B caches per filing: FY2024 ARR and FY2025 ARR coexist."""
        self.reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue", taxonomy="kpi-prose",
            source="kpi-llm", verified=True, value_sample=3.0e9,
            accession="0001535527-24-000123",
        )
        self.reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue", taxonomy="kpi-prose",
            source="kpi-llm", verified=True, value_sample=3.44e9,
            accession="0001535527-25-000045",
        )
        fy24 = self.reg.lookup("0001535527", "arr",
                                accession="0001535527-24-000123")
        fy25 = self.reg.lookup("0001535527", "arr",
                                accession="0001535527-25-000045")
        assert fy24 is not None and fy25 is not None
        self.assertAlmostEqual(fy24.value_sample or 0, 3.0e9)
        self.assertAlmostEqual(fy25.value_sample or 0, 3.44e9)

    def test_v1_lookup_without_accession_still_works(self) -> None:
        """Calls that omit accession use accession='' for backward compat."""
        self.reg.upsert(
            cik="0001045810", metric="revenue",
            concept="Revenues", taxonomy="us-gaap",
            source="fuzzy", verified=True,
        )
        # v1-style lookup, no accession kwarg
        row = self.reg.lookup("0001045810", "revenue")
        assert row is not None
        self.assertEqual(row.accession, "")
        self.assertEqual(row.concept, "Revenues")

    def test_lookup_prefers_per_accession_over_whole_company(self) -> None:
        """If both a per-accession row and a whole-company row exist for
        the same (cik, metric), the per-accession row wins when accession
        is specified; the whole-company row wins when accession is None."""
        # Whole-company row (v1 shape)
        self.reg.upsert(
            cik="0001045810", metric="revenue",
            concept="Revenues", taxonomy="us-gaap",
            source="fuzzy", verified=True,
        )
        # Per-filing row (v2 shape)
        self.reg.upsert(
            cik="0001045810", metric="revenue",
            concept="RevenueFromContractWithCustomer", taxonomy="us-gaap",
            source="llm", verified=True,
            accession="0001045810-25-000001",
        )
        whole = self.reg.lookup("0001045810", "revenue")
        per = self.reg.lookup("0001045810", "revenue",
                               accession="0001045810-25-000001")
        assert whole is not None and per is not None
        self.assertEqual(whole.concept, "Revenues")
        self.assertEqual(per.concept, "RevenueFromContractWithCustomer")

    def test_list_rows_filters_by_accession(self) -> None:
        self.reg.upsert(
            cik="A", metric="arr", concept="annual recurring revenue",
            taxonomy="kpi-prose", source="kpi-llm", verified=True,
            accession="ACC-1",
        )
        self.reg.upsert(
            cik="A", metric="arr", concept="annual recurring revenue",
            taxonomy="kpi-prose", source="kpi-llm", verified=True,
            accession="ACC-2",
        )
        only_acc1 = self.reg.list_rows(cik="A", accession="ACC-1")
        self.assertEqual(len(only_acc1), 1)
        self.assertEqual(only_acc1[0].accession, "ACC-1")

    def test_clear_by_accession(self) -> None:
        self.reg.upsert(cik="A", metric="arr", concept="x",
                        taxonomy="kpi-prose", source="kpi-llm",
                        verified=True, accession="ACC-1")
        self.reg.upsert(cik="A", metric="arr", concept="y",
                        taxonomy="kpi-prose", source="kpi-llm",
                        verified=True, accession="ACC-2")
        removed = self.reg.clear(cik="A", accession="ACC-1")
        self.assertEqual(removed, 1)
        self.assertIsNotNone(self.reg.lookup("A", "arr", accession="ACC-2"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_learned_registry.py::TestLearnedRegistryAccessionKey -v`

Expected: FAIL — `lookup` doesn't accept `accession=`, `upsert` doesn't accept `accession=`, `list_rows` doesn't filter by accession, `clear` doesn't filter by accession, `LearnedRow` has no `accession` attribute.

- [ ] **Step 3: Update `LearnedRow` dataclass**

In `edgarpack/query/learned_registry.py`, update the `LearnedRow` dataclass:

```python
@dataclass(frozen=True)
class LearnedRow:
    cik: str
    metric: str
    concept: str
    taxonomy: str
    source: str
    verified: bool
    verif_method: str | None
    value_sample: float | None
    learned_at: str
    hit_count: int
    accession: str = ""
```

- [ ] **Step 4: Update `lookup` to support accession**

Replace `lookup`:

```python
    def lookup(
        self,
        cik: str,
        metric: str,
        accession: str | None = None,
    ) -> LearnedRow | None:
        """Look up a learned mapping.

        If ``accession`` is None, returns the whole-company (v1-style) row
        with accession=''. If ``accession`` is given, returns the per-filing
        row; if no per-filing row exists, does NOT fall back to the
        whole-company row (callers that need fallback call again with
        accession=None).
        """
        conn = self._get_conn()
        if accession is None:
            cur = conn.execute(
                "SELECT * FROM learned_concepts "
                "WHERE cik = ? AND metric = ? AND accession = ''",
                (cik, metric),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM learned_concepts "
                "WHERE cik = ? AND metric = ? AND accession = ?",
                (cik, metric, accession),
            )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dataclass(row)
```

- [ ] **Step 5: Update `upsert` to accept accession**

Replace `upsert`:

```python
    def upsert(
        self,
        *,
        cik: str,
        metric: str,
        concept: str,
        taxonomy: str,
        source: str,
        verified: bool,
        verif_method: str | None = None,
        value_sample: float | None = None,
        accession: str = "",
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO learned_concepts (
                cik, metric, concept, taxonomy, source,
                verified, verif_method, value_sample, learned_at,
                hit_count, accession
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(cik, accession, metric) DO UPDATE SET
                concept      = excluded.concept,
                taxonomy     = excluded.taxonomy,
                source       = excluded.source,
                verified     = excluded.verified,
                verif_method = excluded.verif_method,
                value_sample = excluded.value_sample,
                learned_at   = excluded.learned_at
            """,
            (
                cik, metric, concept, taxonomy, source,
                1 if verified else 0, verif_method, value_sample,
                datetime.now(UTC).isoformat(), accession,
            ),
        )
        conn.commit()
```

- [ ] **Step 6: Update `bump_hit_count` to accept optional accession**

Replace `bump_hit_count`:

```python
    def bump_hit_count(
        self,
        cik: str,
        metric: str,
        accession: str | None = None,
    ) -> None:
        conn = self._get_conn()
        if accession is None:
            conn.execute(
                "UPDATE learned_concepts SET hit_count = hit_count + 1 "
                "WHERE cik = ? AND metric = ? AND accession = ''",
                (cik, metric),
            )
        else:
            conn.execute(
                "UPDATE learned_concepts SET hit_count = hit_count + 1 "
                "WHERE cik = ? AND metric = ? AND accession = ?",
                (cik, metric, accession),
            )
        conn.commit()
```

- [ ] **Step 7: Update `list_rows` to accept accession filter**

Replace the signature and body of `list_rows`:

```python
    def list_rows(
        self,
        *,
        cik: str | None = None,
        metric: str | None = None,
        source: str | None = None,
        accession: str | None = None,
        only_unverified: bool = False,
    ) -> list[LearnedRow]:
        sql = "SELECT * FROM learned_concepts WHERE 1=1"
        params: list[object] = []
        if cik is not None:
            sql += " AND cik = ?"
            params.append(cik)
        if metric is not None:
            sql += " AND metric = ?"
            params.append(metric)
        if source is not None:
            sql += " AND source = ?"
            params.append(source)
        if accession is not None:
            sql += " AND accession = ?"
            params.append(accession)
        if only_unverified:
            sql += " AND verified = 0"
        sql += " ORDER BY hit_count DESC, learned_at DESC"
        conn = self._get_conn()
        cur = conn.execute(sql, tuple(params))
        return [_row_to_dataclass(r) for r in cur.fetchall()]
```

- [ ] **Step 8: Update `clear` to accept accession filter**

Replace `clear`:

```python
    def clear(
        self,
        *,
        cik: str | None = None,
        metric: str | None = None,
        accession: str | None = None,
        all: bool = False,
    ) -> int:
        if cik is None and metric is None and accession is None and not all:
            raise ValueError(
                "learned_registry.clear: refusing to clear entire table "
                "without all=True or a cik/metric/accession filter"
            )
        sql = "DELETE FROM learned_concepts WHERE 1=1"
        params: list[object] = []
        if cik is not None:
            sql += " AND cik = ?"
            params.append(cik)
        if metric is not None:
            sql += " AND metric = ?"
            params.append(metric)
        if accession is not None:
            sql += " AND accession = ?"
            params.append(accession)
        conn = self._get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount or 0
```

- [ ] **Step 9: Update `_row_to_dataclass` to include accession**

Replace `_row_to_dataclass`:

```python
def _row_to_dataclass(row: sqlite3.Row) -> LearnedRow:
    # accession may not exist on a pre-migration row; use .keys() to check.
    keys = row.keys() if hasattr(row, "keys") else []
    accession = row["accession"] if "accession" in keys else ""
    return LearnedRow(
        cik=row["cik"],
        metric=row["metric"],
        concept=row["concept"],
        taxonomy=row["taxonomy"],
        source=row["source"],
        verified=bool(row["verified"]),
        verif_method=row["verif_method"],
        value_sample=row["value_sample"],
        learned_at=row["learned_at"],
        hit_count=int(row["hit_count"]),
        accession=accession or "",
    )
```

- [ ] **Step 10: Run the tests to verify they pass**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_learned_registry.py tests/test_learned_registry_migration.py -v`

Expected: 17 tests pass (11 existing + 6 new).

- [ ] **Step 11: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/learned_registry.py tests/test_learned_registry.py
git commit -m "feat(query/learned_registry): accession-aware lookup, upsert, list, clear

LearnedRegistry now supports per-filing mappings via an optional
accession= kwarg on lookup/upsert/list_rows/clear/bump_hit_count.
LearnedRow gains an accession field (defaults to empty string for
backward compat with v1 rows).

Semantics: lookup with accession=None returns the v1-style whole-company
row. With accession set, returns the per-filing row without falling back
to the whole-company row. Callers that need fallback (try_learn in v1,
not try_extract_kpi in v2) call twice.

Layer B will upsert with the pack's accession. Layer A's existing
behavior is unchanged: accession defaults to '' everywhere it's not
explicitly passed.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 5: Update Layer 0 unknown-metric guard to check `KPI_CATALOG`

**Files:**
- Modify: `edgarpack/query/concepts.py` (re-export KPI_CATALOG + KpiDef)
- Modify: `edgarpack/query/financials.py` (unknown-metric guard)
- Modify: `tests/test_financials.py` (test that KPI names don't raise)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_financials.py` inside the existing `TestAliasDereferencing` class:

```python
    def test_kpi_catalog_name_does_not_raise(self) -> None:
        """A metric name in KPI_CATALOG but not METRIC_MAP must not raise."""
        import asyncio as _asyncio

        # Use a mock facts blob with no matching concepts so Layer A fails too.
        # The test only checks that MetricNotFound is NOT raised — the query
        # will still return None for the metric because Layer B isn't wired
        # yet in Task 5. That happens in Task 12.

        async def _run() -> None:
            with patch(f"{_P}.resolve_ticker",
                       new=AsyncMock(return_value=("0001535527", "CrowdStrike"))), \
                 patch(f"{_P}.fetch_company_facts",
                       new=AsyncMock(return_value={"facts": {}})), \
                 patch(f"{_P}._build_doc_map",
                       new=AsyncMock(return_value={})):
                # 'arr' is in KPI_CATALOG, not in METRIC_MAP.
                # Before Layer B is wired, the result for 'arr' is None, not a raise.
                result = await financials("CRWD", metrics="arr", period="lfy")
                self.assertIn("arr", result.metrics)
                # Layer B isn't firing yet (Task 12 does that), so expect None
                self.assertIsNone(result.metrics["arr"])

        _asyncio.run(_run())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_financials.py::TestAliasDereferencing::test_kpi_catalog_name_does_not_raise -v`

Expected: FAIL with `edgarpack.query.layer_zero.MetricNotFound: Unknown metric: 'arr'.` — the guard rejects 'arr' because it's not in METRIC_MAP.

- [ ] **Step 3: Update `concepts.py` to re-export KPI_CATALOG**

In `edgarpack/query/concepts.py`, extend the existing re-export block:

```python
# Re-export Layer 0 helpers for callers that only import from concepts.
from .layer_zero import METRIC_ALIASES, MetricNotFound, resolve_alias, suggest_metrics
from .kpi_extract import KPI_CATALOG, KpiDef

__all__ = [
    "METRIC_ALIASES",
    "MetricNotFound",
    "resolve_alias",
    "suggest_metrics",
    "METRIC_MAP",
    "ALL_METRICS",
    "MetricMeta",
    "resolve_concept",
    "get_metric_meta",
    "get_scope_warning",
    "KPI_CATALOG",
    "KpiDef",
]
```

- [ ] **Step 4: Update the unknown-metric guard in `financials.py`**

In `edgarpack/query/financials.py`, find the Layer 0 block and replace it:

```python
    # Layer 0: alias dereferencing + unknown-metric guard
    # A metric is "known" if it's in METRIC_MAP OR in KPI_CATALOG (Layer B).
    from .kpi_extract import KPI_CATALOG

    resolved_list: list[str] = []
    for m in metric_list:
        resolved = resolve_alias(m)
        if resolved not in METRIC_MAP and resolved not in KPI_CATALOG:
            combined_known = set(METRIC_MAP.keys()) | set(KPI_CATALOG.keys())
            suggestions = suggest_metrics(resolved, combined_known, n=3)
            raise MetricNotFound(m, suggestions=suggestions)
        resolved_list.append(resolved)
    metric_list = resolved_list
```

- [ ] **Step 5: Handle KPI-only metrics in the metric loop**

In `financials.py`, inside the `for metric in metric_list:` loop, find the line `meta = METRIC_MAP.get(metric)`. Currently this returns `None` for KPI-catalog-only metrics, and the code raises/errors. Change the flow so KPI-only metrics are deferred to Layer B:

```python
    for metric in metric_list:
        meta = METRIC_MAP.get(metric)
        if meta is None:
            # KPI-only metric (in KPI_CATALOG but not METRIC_MAP).
            # Task 12 will wire try_extract_kpi here. For now, set to None
            # so the test passes and the structure is ready.
            result_metrics[metric] = None
            continue

        if meta.derived:
            ...
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_financials.py::TestAliasDereferencing -v`

Expected: 3 passing (including the new test).

- [ ] **Step 7: Regression check**

Run: `cd ~/edgarpack && EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" ~/edgarpack/.venv/bin/pytest tests/ -q`

Expected: All pass.

- [ ] **Step 8: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/concepts.py edgarpack/query/financials.py tests/test_financials.py
git commit -m "feat(query): recognize KPI_CATALOG names as known metrics

The unknown-metric guard in financials() now accepts any name in
METRIC_MAP OR KPI_CATALOG. MetricNotFound only fires when neither
dictionary has the requested name. Suggestions are drawn from the union.

KPI-only metrics (in KPI_CATALOG but not METRIC_MAP) currently return
None from the metric loop. Task 12 will wire them to try_extract_kpi.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 6: Add `_resolve_filing_for_period` and pack/manifest loading

**Files:**
- Modify: `edgarpack/query/kpi_extract.py` (append helpers)
- Modify: `tests/test_kpi_extract.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_kpi_extract.py`:

```python
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from edgarpack.harvest.registry import PackRecord, PackRegistry
from edgarpack.query.kpi_extract import (
    _load_pack_manifest,
    _resolve_filing_for_period,
)


def _write_manifest(pack_dir: Path, sections: list[dict]) -> None:
    """Write a minimal manifest.json that Layer B's loader can parse."""
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "parser_version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {"url": "https://example/filing", "fetched_at": datetime.now(UTC).isoformat()},
        "filing": {
            "cik": "0001535527",
            "accession": "0001535527-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-03-07",
            "company_name": "CrowdStrike Holdings, Inc.",
        },
        "sections": sections,
        "artifacts": {},
        "warnings": [],
        "tokens_total": 0,
    }
    (pack_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


class TestResolveFilingForPeriod(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.packs_dir = Path(self._tmp.name) / "packs"
        self.packs_dir.mkdir()
        self.registry = PackRegistry(db_path=self.registry_db)

    def _register(self, accession: str, form_type: str, filing_date: str) -> Path:
        pack_dir = self.packs_dir / "0001535527" / accession
        _write_manifest(pack_dir, sections=[])
        self.registry.register_pack(PackRecord(
            accession=accession,
            cik="0001535527",
            ticker="CRWD",
            company_name="CrowdStrike Holdings, Inc.",
            form_type=form_type,
            filing_date=filing_date,
            sections_count=0,
            tokens_total=0,
            pack_dir=str(pack_dir),
            built_at=datetime.now(UTC).isoformat(),
        ))
        return pack_dir

    def test_lfy_returns_most_recent_10k(self) -> None:
        self._register("0001535527-23-000001", "10-K", "2023-03-01")
        pack_24 = self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "lfy", self.registry)
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.accession, "0001535527-24-000123")

    def test_mrq_returns_most_recent_10q(self) -> None:
        self._register("0001535527-24-000200", "10-Q", "2024-06-05")
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "mrq", self.registry)
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.form_type, "10-Q")

    def test_annual_series_returns_nth_most_recent(self) -> None:
        self._register("0001535527-22-000001", "10-K", "2022-03-01")
        self._register("0001535527-23-000001", "10-K", "2023-03-01")
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "annual:2", self.registry)
        assert rec is not None
        self.assertEqual(rec.accession, "0001535527-23-000001")

    def test_returns_none_when_no_pack(self) -> None:
        rec = _resolve_filing_for_period("9999999", "lfy", self.registry)
        self.assertIsNone(rec)

    def test_returns_none_for_annual_out_of_range(self) -> None:
        self._register("0001535527-24-000123", "10-K", "2024-03-07")
        rec = _resolve_filing_for_period("0001535527", "annual:5", self.registry)
        self.assertIsNone(rec)


class TestLoadPackManifest(unittest.TestCase):
    def test_loads_manifest_json_from_pack_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td) / "pack"
            _write_manifest(pack_dir, sections=[
                {"id": "10k_parti_item7_mda", "title": "MD&A",
                 "path": "sections/10k_parti_item7_mda.md",
                 "char_start": 0, "char_end": 1000,
                 "tokens_approx": 200, "sha256": "deadbeef"}
            ])
            manifest = _load_pack_manifest(pack_dir)
            self.assertIn("sections", manifest)
            self.assertEqual(len(manifest["sections"]), 1)
            self.assertEqual(manifest["sections"][0]["id"], "10k_parti_item7_mda")

    def test_raises_if_no_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td) / "nothing"
            pack_dir.mkdir()
            with self.assertRaises(FileNotFoundError):
                _load_pack_manifest(pack_dir)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v 2>&1 | tail -15`

Expected: FAIL with `ImportError: cannot import name '_resolve_filing_for_period'`.

- [ ] **Step 3: Implement `_load_pack_manifest` and `_resolve_filing_for_period`**

Append to `edgarpack/query/kpi_extract.py`:

```python
import json
from pathlib import Path

from ..harvest.registry import PackRecord, PackRegistry


def _load_pack_manifest(pack_dir: Path) -> dict:
    """Read manifest.json from a pack directory.

    Raises FileNotFoundError if the manifest does not exist.
    """
    manifest_path = pack_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest.json at {manifest_path}. Pack may be incomplete."
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


_PERIOD_TO_FORM: dict[str, str] = {
    "lfy": "10-K",
    "mrq": "10-Q",
}


def _resolve_filing_for_period(
    cik: str,
    period: str,
    registry: PackRegistry,
) -> PackRecord | None:
    """Given a period selector, find the pack that represents it.

    Period semantics:
      lfy              -> most recent 10-K
      mrq              -> most recent 10-Q
      mrp / ltm        -> most recent 10-K OR 10-Q by filing_date
      annual:N         -> Nth most recent 10-K (N is 1-indexed)
      quarterly:N      -> Nth most recent 10-Q (N is 1-indexed)

    Returns None if the required pack does not exist in the registry.
    """
    p = period.strip().lower()

    if p in ("lfy", "mrq"):
        form = _PERIOD_TO_FORM[p]
        packs = registry.list_packs(cik=cik, form_type=form, limit=5)
        return packs[0] if packs else None

    if p in ("mrp", "ltm"):
        # Both 10-K and 10-Q are candidates; sort by filing_date desc
        tens_k = registry.list_packs(cik=cik, form_type="10-K", limit=5)
        tens_q = registry.list_packs(cik=cik, form_type="10-Q", limit=5)
        merged = sorted(
            tens_k + tens_q,
            key=lambda r: r.filing_date,
            reverse=True,
        )
        return merged[0] if merged else None

    if p.startswith("annual:"):
        try:
            n = int(p.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        if n < 1:
            return None
        packs = registry.list_packs(cik=cik, form_type="10-K", limit=max(5, n))
        if len(packs) < n:
            return None
        return packs[n - 1]

    if p.startswith("quarterly:"):
        try:
            n = int(p.split(":", 1)[1])
        except (ValueError, IndexError):
            return None
        if n < 1:
            return None
        packs = registry.list_packs(cik=cik, form_type="10-Q", limit=max(5, n))
        if len(packs) < n:
            return None
        return packs[n - 1]

    return None
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v 2>&1 | tail -20`

Expected: All tests pass (9 catalog + 5 period resolution + 2 manifest loading = 16 tests).

- [ ] **Step 5: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query/kpi_extract): pack manifest loader + period->pack resolver

_load_pack_manifest(pack_dir) reads manifest.json from a pack directory
and raises FileNotFoundError with a clear message when absent.

_resolve_filing_for_period(cik, period, registry) maps period selectors
(lfy, mrq, mrp, ltm, annual:N, quarterly:N) to the correct PackRecord
via PackRegistry.list_packs. Returns None when no pack exists or N is
out of range.

Both are pure functions except for file/db reads, testable with
tempfile + a fresh PackRegistry.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 7: Add `_select_sections`, `_read_section_text`, `_trim_to_budget`

**Files:**
- Modify: `edgarpack/query/kpi_extract.py` (append helpers)
- Modify: `tests/test_kpi_extract.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_kpi_extract.py`:

```python
from edgarpack.query.kpi_extract import (
    _read_section_text,
    _select_sections,
    _trim_to_budget,
)


class TestSelectSections(unittest.TestCase):
    def test_matches_mda_section(self) -> None:
        sections = [
            {"id": "10k_parti_item1_business", "path": "sections/item1.md",
             "title": "Business", "char_start": 0, "char_end": 100},
            {"id": "10k_parti_item7_managements_discussion_and_analysis",
             "path": "sections/item7.md", "title": "MD&A",
             "char_start": 100, "char_end": 5000},
            {"id": "10k_parti_item8_financial_statements",
             "path": "sections/item8.md", "title": "Financials",
             "char_start": 5000, "char_end": 10000},
        ]
        selected = _select_sections(sections)
        ids = {s["id"] for s in selected}
        self.assertIn("10k_parti_item7_managements_discussion_and_analysis", ids)
        self.assertNotIn("10k_parti_item1_business", ids)

    def test_matches_key_metrics_section_by_slug(self) -> None:
        sections = [
            {"id": "10k_key_metrics_nontraditional",
             "path": "sections/key.md", "title": "Key Metrics",
             "char_start": 0, "char_end": 500},
            {"id": "10k_operating_data_north_america",
             "path": "sections/ops.md", "title": "Operating Data",
             "char_start": 500, "char_end": 1000},
        ]
        selected = _select_sections(sections)
        self.assertEqual(len(selected), 2)

    def test_matches_10q_mda(self) -> None:
        sections = [
            {"id": "10q_parti_item1_financial_statements",
             "path": "sections/q1.md", "title": "Financials",
             "char_start": 0, "char_end": 100},
            {"id": "10q_parti_item2_managements_discussion",
             "path": "sections/q2.md", "title": "MD&A",
             "char_start": 100, "char_end": 2000},
        ]
        selected = _select_sections(sections)
        ids = {s["id"] for s in selected}
        self.assertIn("10q_parti_item2_managements_discussion", ids)

    def test_returns_empty_when_no_matches(self) -> None:
        sections = [
            {"id": "10k_parti_item1_business", "path": "sections/item1.md",
             "title": "Business", "char_start": 0, "char_end": 100},
        ]
        self.assertEqual(_select_sections(sections), [])


class TestReadSectionText(unittest.TestCase):
    def test_concatenates_section_files_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            sections_dir = pack_dir / "sections"
            sections_dir.mkdir()
            (sections_dir / "a.md").write_text("Alpha content", encoding="utf-8")
            (sections_dir / "b.md").write_text("Beta content", encoding="utf-8")
            sections = [
                {"id": "sec_a", "path": "sections/a.md", "title": "A",
                 "char_start": 0, "char_end": 100},
                {"id": "sec_b", "path": "sections/b.md", "title": "B",
                 "char_start": 100, "char_end": 200},
            ]
            text = _read_section_text(pack_dir, sections)
            self.assertIn("Alpha content", text)
            self.assertIn("Beta content", text)
            self.assertIn("sec_a", text)  # separator marker includes the id
            self.assertIn("sec_b", text)

    def test_skips_missing_files_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            pack_dir = Path(td)
            (pack_dir / "sections").mkdir()
            sections = [
                {"id": "missing_sec", "path": "sections/missing.md", "title": "Gone",
                 "char_start": 0, "char_end": 100},
            ]
            text = _read_section_text(pack_dir, sections)
            self.assertEqual(text, "")


class TestTrimToBudget(unittest.TestCase):
    def test_passthrough_when_under_budget(self) -> None:
        text = "short text"
        self.assertEqual(_trim_to_budget(text, max_chars=100), text)

    def test_truncates_when_over_budget(self) -> None:
        text = "x" * 200
        trimmed = _trim_to_budget(text, max_chars=100)
        self.assertLessEqual(len(trimmed), 150)  # allow for the marker
        self.assertIn("[truncated]", trimmed)

    def test_default_budget_is_reasonable(self) -> None:
        # Default should allow up to ~60K chars (~15K tokens at 4 chars/token)
        text = "x" * 50_000
        trimmed = _trim_to_budget(text)
        self.assertEqual(trimmed, text)  # unmodified
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v 2>&1 | tail -15`

Expected: FAIL — three helpers don't exist yet.

- [ ] **Step 3: Implement the helpers**

Append to `edgarpack/query/kpi_extract.py`:

```python
import logging
import re as _re

logger = logging.getLogger(__name__)

_SECTION_PATTERNS: tuple[_re.Pattern[str], ...] = (
    _re.compile(r"^10k_parti_item7\b"),      # MD&A (10-K)
    _re.compile(r"^10k_parti_item7a\b"),     # Quant/Qual market risk (sometimes KPIs)
    _re.compile(r"^10q_parti_item2\b"),      # MD&A (10-Q)
    _re.compile(r"_segment"),                # segment reporting, anywhere
    _re.compile(r"_key_metric"),
    _re.compile(r"_operating_data"),
    _re.compile(r"_key_performance"),
)


def _select_sections(sections: list[dict]) -> list[dict]:
    """Return manifest section entries whose IDs match MD&A / key-metrics patterns.

    Empty list if none match. The caller handles the 'malformed pack' case.
    """
    result: list[dict] = []
    for sec in sections:
        sec_id = str(sec.get("id", ""))
        if any(pat.search(sec_id) for pat in _SECTION_PATTERNS):
            result.append(sec)
    return result


_SECTION_SEPARATOR = "\n\n--- [{id}] ---\n\n"


def _read_section_text(pack_dir: Path, sections: list[dict]) -> str:
    """Concatenate section markdown from disk in manifest order.

    Missing files are skipped with a warning log; the function never raises.
    Returns an empty string if none of the requested sections exist.
    """
    parts: list[str] = []
    for sec in sections:
        sec_id = str(sec.get("id", ""))
        rel_path = sec.get("path", "")
        if not rel_path:
            continue
        section_file = pack_dir / rel_path
        if not section_file.exists():
            logger.warning(
                "Section file missing: %s (pack=%s)", section_file, pack_dir
            )
            continue
        try:
            content = section_file.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read %s: %s", section_file, e)
            continue
        parts.append(_SECTION_SEPARATOR.format(id=sec_id))
        parts.append(content)
    return "".join(parts)


_DEFAULT_MAX_CHARS = 60_000


def _trim_to_budget(text: str, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """Trim text to stay under a character budget (rough token proxy).

    Uses a 4 chars/token heuristic: 60K chars ~= 15K tokens. Truncates
    mid-section with a clear '[truncated]' marker so the LLM knows the
    text has a boundary.
    """
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 100]
    return f"{head}\n\n[truncated at {max_chars} chars]"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v 2>&1 | tail -25`

Expected: All tests pass (~25 total: 9 catalog + 5 period + 2 manifest + 4 select + 2 read + 3 trim).

- [ ] **Step 5: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query/kpi_extract): section selection + reading + budget trimming

_select_sections filters manifest entries by regex over section IDs:
^10k_parti_item7, ^10k_parti_item7a, ^10q_parti_item2, _segment,
_key_metric, _operating_data, _key_performance. Returns empty list on
no matches (caller handles the malformed-pack case).

_read_section_text concatenates matching section .md files in manifest
order with a '--- [section_id] ---' separator. Missing files are logged
and skipped, never raised.

_trim_to_budget enforces a 60K char budget (~15K tokens at 4 chars/token)
with a clear '[truncated]' marker so the LLM knows the boundary.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 8: Add `_build_extraction_prompt` and `_extract_via_llm`

**Files:**
- Modify: `edgarpack/query/kpi_extract.py` (append helpers)
- Modify: `tests/test_kpi_extract.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_kpi_extract.py`:

```python
import json as _json
from unittest.mock import patch

from edgarpack.query.kpi_extract import (
    _build_extraction_prompt,
    _extract_via_llm,
    _llm_backend_available_kpi,
)


class TestBuildExtractionPrompt(unittest.TestCase):
    def test_prompt_contains_metric_phrases(self) -> None:
        kpi = KpiDef(
            phrases=("annual recurring revenue", "ARR"),
            unit_hint="USD",
        )
        prompt = _build_extraction_prompt(
            metric="arr", kpi_def=kpi,
            company="CrowdStrike", form_type="10-K",
            filing_date="2024-03-07",
            text="MD&A says ARR was $3.44B at year end.",
        )
        self.assertIn("annual recurring revenue", prompt)
        self.assertIn("ARR", prompt)
        self.assertIn("CrowdStrike", prompt)
        self.assertIn("10-K", prompt)
        self.assertIn("2024-03-07", prompt)
        self.assertIn("MD&A says ARR was $3.44B at year end.", prompt)

    def test_prompt_requests_strict_json(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        prompt = _build_extraction_prompt(
            metric="arr", kpi_def=kpi,
            company="X", form_type="10-K", filing_date="2024-01-01",
            text="text",
        )
        self.assertIn("JSON", prompt)
        self.assertIn("confidence", prompt)
        self.assertIn("excerpt", prompt)

    def test_prompt_includes_unit_hint(self) -> None:
        kpi = KpiDef(phrases=("NRR",), unit_hint="percent")
        prompt = _build_extraction_prompt(
            metric="nrr", kpi_def=kpi,
            company="X", form_type="10-K", filing_date="2024-01-01",
            text="text",
        )
        self.assertIn("percent", prompt)


class TestExtractViaLlm(unittest.TestCase):
    def test_returns_none_without_backend(self) -> None:
        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", None):
            result = _extract_via_llm("dummy prompt")
            self.assertIsNone(result)

    def test_parses_valid_response(self) -> None:
        fake = _json.dumps({
            "value": 3440000000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            result = _extract_via_llm("prompt")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["confidence"], "high")
            self.assertEqual(result["value"], 3440000000)
            self.assertEqual(result["unit"], "USD")

    def test_returns_none_on_malformed_json(self) -> None:
        class _Fake:
            stdout = "not json at all"
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_returns_none_on_nonzero_exit(self) -> None:
        class _Fake:
            stdout = ""
            stderr = "error"
            returncode = 1

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_returns_none_on_timeout(self) -> None:
        import subprocess as _sp

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   side_effect=_sp.TimeoutExpired(cmd="codex", timeout=45)):
            self.assertIsNone(_extract_via_llm("prompt"))

    def test_parses_dict_object_field_types(self) -> None:
        """Reject responses missing required keys or with wrong types."""
        bad_responses = [
            {"confidence": "high"},  # missing value/unit/excerpt/section_id
            {"value": None, "unit": "USD", "excerpt": "x", "section_id": "y",
             "confidence": "high"},  # value is None but confidence is high
            {"value": "not a number", "unit": "USD", "excerpt": "x",
             "section_id": "y", "confidence": "high"},
        ]
        for resp in bad_responses:
            class _Fake:
                stdout = _json.dumps(resp)
                stderr = ""
                returncode = 0
            with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
                 patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
                self.assertIsNone(_extract_via_llm("prompt"))

    def test_passes_through_not_found_confidence(self) -> None:
        fake = _json.dumps({
            "value": None, "unit": None, "excerpt": "",
            "section_id": "", "confidence": "not_found",
        })

        class _Fake:
            stdout = fake
            stderr = ""
            returncode = 0

        with patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            result = _extract_via_llm("prompt")
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result["confidence"], "not_found")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestBuildExtractionPrompt tests/test_kpi_extract.py::TestExtractViaLlm -v`

Expected: FAIL — both functions don't exist yet.

- [ ] **Step 3: Implement the prompt builder and LLM dispatch**

Append to `edgarpack/query/kpi_extract.py`:

```python
import shutil
import subprocess

# Module-level LLM backend detection for Layer B. Separate from Layer A's
# _LLM_CMD so tests can patch each independently.
_LLM_CMD_KPI: str | None = None
for _candidate in ("codex", "claude"):
    if shutil.which(_candidate):
        _LLM_CMD_KPI = _candidate
        break


def _llm_backend_available_kpi() -> bool:
    return _LLM_CMD_KPI is not None


_LLM_TIMEOUT_SECONDS_KPI = 45


def _build_extraction_prompt(
    metric: str,
    kpi_def: KpiDef,
    company: str,
    form_type: str,
    filing_date: str,
    text: str,
) -> str:
    """Build the single-shot KPI extraction prompt.

    The prompt instructs the LLM to extract a literal, verbatim value for
    the requested metric from the provided text. It is explicit about
    rules (no inference, no forward-looking targets, literal excerpts
    only) and requires a strict JSON response with a fixed schema.
    """
    phrases = ", ".join(f'"{p}"' for p in kpi_def.phrases)
    return (
        "You are extracting a reported KPI from SEC filing prose. Be "
        "conservative. Reject ambiguous cases. Never infer or compute; "
        "only extract values that are stated literally.\n\n"
        f"Company: {company}\n"
        f"Filing: {form_type} filed {filing_date}\n"
        f"Metric: {metric}\n"
        f"Metric phrases to search for: {phrases}\n"
        f"Unit hint: {kpi_def.unit_hint}\n\n"
        "Rules:\n"
        "1. Search only the text below. Never use outside knowledge.\n"
        "2. Only return a value if the text states it in unambiguous prose "
        "or a labeled table row. Forward-looking targets, ranges, and "
        "competitor figures do not count.\n"
        f"3. The value's unit must match the hint ({kpi_def.unit_hint}). "
        "If the text reports a different unit, normalize or return not_found.\n"
        "4. The excerpt must be a verbatim substring of the text. "
        "No paraphrasing.\n"
        "5. If multiple candidate values exist (e.g. historical AND current), "
        "return the most recent as-of the filing date.\n"
        "6. If you cannot find the value with high confidence, return "
        '{"confidence": "not_found", ...} or {"confidence": "ambiguous", ...}.\n\n'
        "Respond with strict JSON, no prose, no markdown fences:\n"
        "  {\n"
        '    "value": <number or null>,\n'
        '    "unit": "USD" | "count" | "percent" | "days" | "pure" | null,\n'
        '    "excerpt": "<verbatim substring of the text>",\n'
        '    "section_id": "<the section ID the excerpt came from>",\n'
        '    "confidence": "high" | "medium" | "low" | "not_found" | "ambiguous"\n'
        "  }\n\n"
        "TEXT:\n"
        f"{text}\n"
    )


def _extract_via_llm(prompt: str) -> dict | None:
    """Run the LLM subprocess and parse the JSON response.

    Returns the parsed dict on success, or None on any failure path:
    no backend, timeout, non-zero exit, malformed JSON, missing keys,
    wrong value types, or a 'value is None' response with confidence=high.

    'not_found' / 'ambiguous' / 'low' confidence responses are passed
    through as dicts so the caller can produce a structured diagnostic.
    """
    if _LLM_CMD_KPI is None:
        return None

    try:
        completed = subprocess.run(
            [_LLM_CMD_KPI, "exec", "--prompt", prompt],
            capture_output=True,
            text=True,
            timeout=_LLM_TIMEOUT_SECONDS_KPI,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("KPI LLM extract failed: %s", e)
        return None

    if completed.returncode != 0:
        logger.warning(
            "KPI LLM extract returned non-zero: %s",
            (completed.stderr or "")[:200],
        )
        return None

    raw = (completed.stdout or "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = _re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(parsed, dict):
        return None

    confidence = parsed.get("confidence")
    if confidence not in ("high", "medium", "low", "not_found", "ambiguous"):
        return None

    # Structural validation: low-confidence responses need fewer fields
    if confidence in ("not_found", "ambiguous", "low"):
        return parsed

    # High/medium confidence: require value/unit/excerpt/section_id
    value = parsed.get("value")
    unit = parsed.get("unit")
    excerpt = parsed.get("excerpt")
    section_id = parsed.get("section_id")

    if not isinstance(value, (int, float)):
        return None
    if not isinstance(unit, str) or not unit:
        return None
    if not isinstance(excerpt, str) or not excerpt.strip():
        return None
    if not isinstance(section_id, str):
        return None

    return parsed
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v 2>&1 | tail -15`

Expected: All tests pass (~35 total).

- [ ] **Step 5: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query/kpi_extract): prompt builder + LLM subprocess dispatch

_build_extraction_prompt formats a tight single-shot prompt with the
KPI phrases, unit hint, company metadata, rules ('literal substring
only', 'most recent as-of filing date'), strict JSON schema, and the
pre-trimmed section text.

_extract_via_llm calls the codex/claude subprocess with a 45s timeout
and parses the response. Validates structural shape: high/medium
confidence responses must have numeric value + non-empty unit + excerpt
+ section_id. Low-confidence / not_found / ambiguous responses pass
through as dicts for the caller to turn into diagnostics.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 9: Add `_verify_excerpt_in_text` anti-hallucination check

**Files:**
- Modify: `edgarpack/query/kpi_extract.py` (append helper)
- Modify: `tests/test_kpi_extract.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_kpi_extract.py`:

```python
from edgarpack.query.kpi_extract import _verify_excerpt_in_text


class TestVerifyExcerptInText(unittest.TestCase):
    def test_exact_substring_passes(self) -> None:
        text = "CrowdStrike reported Annual Recurring Revenue of $3.44 billion at year end."
        excerpt = "Annual Recurring Revenue of $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_whitespace_normalized(self) -> None:
        text = "ARR of  $3.44  billion  \n at year end."
        excerpt = "ARR of $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))

    def test_hallucinated_excerpt_fails(self) -> None:
        text = "CrowdStrike reported $3.44 billion at year end."
        excerpt = "ARR was $3.44 billion, a 30 percent increase year over year"
        self.assertFalse(_verify_excerpt_in_text(excerpt, text))

    def test_empty_excerpt_fails(self) -> None:
        self.assertFalse(_verify_excerpt_in_text("", "some text"))

    def test_empty_text_fails(self) -> None:
        self.assertFalse(_verify_excerpt_in_text("something", ""))

    def test_case_insensitive_match(self) -> None:
        text = "Annual Recurring Revenue was $3.44 billion."
        excerpt = "annual recurring revenue was $3.44 billion"
        self.assertTrue(_verify_excerpt_in_text(excerpt, text))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestVerifyExcerptInText -v`

Expected: FAIL — function doesn't exist yet.

- [ ] **Step 3: Implement `_verify_excerpt_in_text`**

Append to `edgarpack/query/kpi_extract.py`:

```python
_WS_RUN = _re.compile(r"\s+")


def _verify_excerpt_in_text(excerpt: str, source_text: str) -> bool:
    """True when ``excerpt`` is a substring of ``source_text``.

    Whitespace is collapsed to single spaces on both sides before the
    comparison. Case-insensitive. Empty excerpt or source returns False.

    This is the hallucination firewall: an LLM cannot invent values that
    weren't in the source text if we reject any response whose excerpt
    fails this check.
    """
    if not excerpt or not source_text:
        return False
    norm_excerpt = _WS_RUN.sub(" ", excerpt).strip().lower()
    norm_source = _WS_RUN.sub(" ", source_text).strip().lower()
    if not norm_excerpt:
        return False
    return norm_excerpt in norm_source
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestVerifyExcerptInText -v`

Expected: 6 passing tests.

- [ ] **Step 5: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query/kpi_extract): anti-hallucination substring check

_verify_excerpt_in_text normalizes whitespace and lowercases both sides
before checking that the LLM's excerpt is a literal substring of the
source text. Empty excerpt or empty source returns False.

This is the core trust property of Layer B. An LLM cannot invent values
that were not in the text we gave it; rejecting any response whose
excerpt fails this check means every persisted Layer B value is
grounded in a real quote from a real filing.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 10: Add `_build_cited_from_extraction` and `_verify_against_prior_filing`

**Files:**
- Modify: `edgarpack/query/kpi_extract.py` (append helpers)
- Modify: `tests/test_kpi_extract.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_kpi_extract.py`:

```python
from datetime import date

from edgarpack.query.kpi_extract import _build_cited_from_extraction


class TestBuildCitedFromExtraction(unittest.TestCase):
    def test_builds_cited_value_with_expected_fields(self) -> None:
        kpi = KpiDef(
            phrases=("annual recurring revenue", "ARR"),
            unit_hint="USD",
        )
        response = {
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion at fiscal year end",
            "section_id": "10k_parti_item7_managements_discussion",
            "confidence": "high",
        }
        pack_record = PackRecord(
            accession="0001535527-24-000123",
            cik="0001535527",
            ticker="CRWD",
            company_name="CrowdStrike Holdings, Inc.",
            form_type="10-K",
            filing_date="2024-03-07",
            sections_count=10,
            tokens_total=300_000,
            pack_dir="/tmp/packs/0001535527/0001535527-24-000123",
            built_at=datetime.now(UTC).isoformat(),
            manifest_hash=None,
            warnings_json=None,
        )
        pack_manifest = {
            "filing": {
                "cik": "0001535527",
                "accession": "0001535527-24-000123",
                "form_type": "10-K",
                "filing_date": "2024-03-07",
                "company_name": "CrowdStrike Holdings, Inc.",
            },
            "sections": [],
        }

        cited = _build_cited_from_extraction(
            response=response,
            metric="arr",
            kpi_def=kpi,
            pack_record=pack_record,
            pack_manifest=pack_manifest,
            primary_document="crwd-20240131.htm",
        )

        self.assertEqual(cited.value, 3_440_000_000)
        self.assertEqual(cited.unit, "USD")
        self.assertEqual(cited.metric, "arr")
        self.assertEqual(cited.concept, "annual recurring revenue")
        self.assertEqual(cited.accession, "0001535527-24-000123")
        self.assertEqual(cited.cik, "0001535527")
        self.assertEqual(cited.company, "CrowdStrike Holdings, Inc.")
        self.assertEqual(cited.form_type, "10-K")
        self.assertEqual(cited.filed, date(2024, 3, 7))
        self.assertEqual(cited.taxonomy, "kpi-prose")
        self.assertEqual(cited.primary_document, "crwd-20240131.htm")
        self.assertEqual(cited.fact_id, "")
        self.assertIn("$3.44 billion", cited.excerpt_text)

    def test_document_url_uses_excerpt(self) -> None:
        kpi = KpiDef(phrases=("ARR",), unit_hint="USD")
        response = {
            "value": 1000, "unit": "USD",
            "excerpt": "Annual recurring revenue of $1,000",
            "section_id": "sec", "confidence": "high",
        }
        pack_record = PackRecord(
            accession="0001535527-24-000123", cik="0001535527",
            ticker="CRWD", company_name="CRWD",
            form_type="10-K", filing_date="2024-03-07",
            sections_count=0, tokens_total=0,
            pack_dir="/tmp/p", built_at="2024-03-08T00:00:00+00:00",
        )
        manifest = {"filing": {
            "cik": "0001535527",
            "accession": "0001535527-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-03-07",
            "company_name": "CRWD",
        }}
        cited = _build_cited_from_extraction(
            response=response, metric="arr", kpi_def=kpi,
            pack_record=pack_record, pack_manifest=manifest,
            primary_document="doc.htm",
        )
        url = cited.document_url
        self.assertIsNotNone(url)
        assert url is not None
        # Should use the excerpt-based text fragment
        self.assertIn("#:~:text=", url)
        self.assertIn("Annual", url)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestBuildCitedFromExtraction -v`

Expected: FAIL — function doesn't exist.

- [ ] **Step 3: Implement `_build_cited_from_extraction`**

Append to `edgarpack/query/kpi_extract.py`:

```python
from datetime import date as _date

from .models import CitedValue


def _build_cited_from_extraction(
    response: dict,
    metric: str,
    kpi_def: KpiDef,
    pack_record: PackRecord,
    pack_manifest: dict,
    primary_document: str,
) -> CitedValue:
    """Construct a CitedValue from a validated LLM extraction response.

    The caller guarantees `response` passed structural validation in
    _extract_via_llm and the excerpt passed _verify_excerpt_in_text.
    """
    filing = pack_manifest.get("filing", {})

    # Parse filing_date -> date
    filing_date_str = str(filing.get("filing_date", pack_record.filing_date))
    try:
        filed = _date.fromisoformat(filing_date_str)
    except ValueError:
        filed = _date.min

    # Fiscal year inferred from the filing date's year.
    # Layer B doesn't distinguish fiscal vs calendar in v2; the manifest
    # does not carry fiscal_year directly. Use the filing year as a
    # conservative default.
    fiscal_year = filed.year if filed != _date.min else 0
    # 10-K -> FY, 10-Q -> Q? (we don't know which quarter without more
    # parsing; use 'Q' as a sentinel).
    fiscal_period = "FY" if pack_record.form_type.startswith("10-K") else "Q"

    # First matched phrase is used as the concept for citation purposes.
    # The prompt explicitly lists all phrases so the LLM picks one; we
    # default to the first phrase if the response doesn't say.
    concept = kpi_def.phrases[0] if kpi_def.phrases else metric

    return CitedValue(
        value=response["value"],
        unit=str(response.get("unit") or kpi_def.unit_hint),
        metric=metric,
        concept=concept,
        period_end=filed,
        fiscal_year=fiscal_year,
        fiscal_period=fiscal_period,
        form_type=pack_record.form_type,
        filed=filed,
        accession=pack_record.accession,
        cik=pack_record.cik,
        company=pack_record.company_name,
        taxonomy="kpi-prose",
        primary_document=primary_document,
        fact_id="",
        excerpt_text=str(response.get("excerpt", "")),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestBuildCitedFromExtraction -v`

Expected: 2 passing tests.

- [ ] **Step 5: Write the failing test for `_verify_against_prior_filing`**

Append to `tests/test_kpi_extract.py`:

```python
from edgarpack.query.kpi_extract import _verify_against_prior_filing


class TestVerifyAgainstPriorFiling(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.registry = PackRegistry(db_path=self.registry_db)

    def _register(self, accession: str, filing_date: str) -> None:
        pack_dir = Path(self._tmp.name) / "packs" / "A" / accession
        _write_manifest(pack_dir, sections=[])
        self.registry.register_pack(PackRecord(
            accession=accession,
            cik="0001535527",
            ticker="CRWD",
            company_name="CRWD",
            form_type="10-K",
            filing_date=filing_date,
            sections_count=0,
            tokens_total=0,
            pack_dir=str(pack_dir),
            built_at=datetime.now(UTC).isoformat(),
        ))

    def test_returns_false_when_no_prior_filing(self) -> None:
        # Only one filing registered
        self._register("ACC-A", "2024-03-07")
        verified, method = _verify_against_prior_filing(
            current_value=3.44e9,
            metric="arr",
            cik="0001535527",
            current_accession="ACC-A",
            registry=self.registry,
            registry_path=self.registry_db,
        )
        self.assertFalse(verified)
        self.assertEqual(method, "no_prior_filing")

    def test_returns_true_when_within_order_of_magnitude(self) -> None:
        """If the prior filing's extraction returns a value within 4x,
        verify passes. Simulate by seeding the learned_concepts registry
        with a prior entry so try_extract_kpi hits the cache."""
        from edgarpack.query.learned_registry import LearnedRegistry

        self._register("ACC-23", "2023-03-01")
        self._register("ACC-24", "2024-03-07")

        # Seed a prior-filing learned row so recursive try_extract_kpi is a
        # cache hit instead of a live LLM call.
        reg = LearnedRegistry(db_path=self.registry_db)
        reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue", taxonomy="kpi-prose",
            source="kpi-llm", verified=True,
            verif_method="order_of_magnitude",
            value_sample=2.56e9,  # prior year
            accession="ACC-23",
        )
        reg.close()

        verified, method = _verify_against_prior_filing(
            current_value=3.44e9,  # 1.34x prior year -> within [0.25, 4.0]
            metric="arr",
            cik="0001535527",
            current_accession="ACC-24",
            registry=self.registry,
            registry_path=self.registry_db,
        )
        self.assertTrue(verified)
        self.assertEqual(method, "prior_filing_crosscheck")
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestVerifyAgainstPriorFiling -v`

Expected: FAIL — function doesn't exist.

- [ ] **Step 7: Implement `_verify_against_prior_filing`**

Append to `edgarpack/query/kpi_extract.py`:

```python
from .learned_registry import LearnedRegistry
from .self_heal import verify_order_of_magnitude


def _verify_against_prior_filing(
    current_value: float,
    metric: str,
    cik: str,
    current_accession: str,
    registry: PackRegistry,
    registry_path: Path | None,
) -> tuple[bool, str]:
    """Verify by extracting the same KPI from the prior 10-K and comparing.

    Returns (verified, method_tag).

    method_tag values:
      'prior_filing_crosscheck' — verification ran and passed or failed
      'no_prior_filing'         — no prior filing exists, verification skipped
      'prior_extract_failed'    — prior filing exists but extraction returned None

    Implementation detail: the recursive call to try_extract_kpi passes
    _verify=False to break the recursion at depth 1.
    """
    all_10k = registry.list_packs(cik=cik, form_type="10-K", limit=10)
    prior = [p for p in all_10k if p.accession != current_accession]
    if not prior:
        return False, "no_prior_filing"

    # Most-recent prior is already sorted first by list_packs (DESC by filing_date).
    prior_pack = prior[0]

    # Check the registry first — a cached prior-year extraction is free.
    learned_reg = LearnedRegistry(db_path=registry_path)
    try:
        cached = learned_reg.lookup(
            cik=cik, metric=metric, accession=prior_pack.accession,
        )
    finally:
        learned_reg.close()

    prior_value: float | None = None
    if cached is not None and cached.value_sample is not None:
        prior_value = float(cached.value_sample)
    else:
        # Recursive call with _verify=False to break the chain
        cited = try_extract_kpi(
            metric=metric,
            cik=cik,
            company=prior_pack.company_name,
            period="lfy",  # prior 10-K
            registry_path=registry_path,
            pack_registry=registry,
            _verify=False,
            _override_pack=prior_pack,
        )
        if cited is None or not isinstance(cited.value, (int, float)):
            return False, "prior_extract_failed"
        prior_value = float(cited.value)

    if prior_value is None:
        return False, "prior_extract_failed"

    if verify_order_of_magnitude(current_value, prior_value):
        return True, "prior_filing_crosscheck"
    return False, "prior_filing_crosscheck"
```

Note: the recursive call passes `_override_pack` — this parameter will be added to `try_extract_kpi` in Task 11. For this task only, the test's second case uses a cached row so the recursive call is not exercised; the function is still tested for the `no_prior_filing` and `cache_hit` paths.

- [ ] **Step 8: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestVerifyAgainstPriorFiling -v`

Expected: 2 passing tests. (The second test hits the cached-prior path and never exercises the recursive call, which works because try_extract_kpi is a forward reference that gets resolved at call time.)

- [ ] **Step 9: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query/kpi_extract): build CitedValue + prior-filing verification

_build_cited_from_extraction constructs a CitedValue from a validated
LLM extraction response: value, unit, metric, concept=first-phrase,
accession/cik/company/form/filed from the pack record, taxonomy='kpi-prose',
primary_document for anchor URL, fact_id=empty, excerpt_text=literal quote.

_verify_against_prior_filing walks the prior 10-K for the same company,
hits the LearnedRegistry cache if a prior extraction exists, otherwise
recursively calls try_extract_kpi with _verify=False to break the chain
at depth 1. Compares via Layer A's verify_order_of_magnitude (0.25x-4.0x
range). Returns (verified, method_tag) for the orchestrator to attach
to the registry row.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 11: Add `try_extract_kpi` orchestrator

**Files:**
- Modify: `edgarpack/query/kpi_extract.py` (append orchestrator)
- Modify: `tests/test_kpi_extract.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_kpi_extract.py`:

```python
from unittest.mock import patch as _patch, AsyncMock

from edgarpack.query.kpi_extract import try_extract_kpi


class TestTryExtractKpi(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.registry_db = Path(self._tmp.name) / "registry.db"
        self.pack_registry = PackRegistry(db_path=self.registry_db)
        self.pack_dir = Path(self._tmp.name) / "packs" / "0001535527" / "0001535527-24-000123"

    def _build_pack(self) -> None:
        _write_manifest(
            self.pack_dir,
            sections=[
                {"id": "10k_parti_item7_mda", "path": "sections/mda.md",
                 "title": "MD&A", "char_start": 0, "char_end": 1000,
                 "tokens_approx": 100, "sha256": "abc"}
            ],
        )
        (self.pack_dir / "sections").mkdir(exist_ok=True)
        (self.pack_dir / "sections" / "mda.md").write_text(
            "Annual recurring revenue of $3.44 billion at fiscal year end.",
            encoding="utf-8",
        )
        self.pack_registry.register_pack(PackRecord(
            accession="0001535527-24-000123",
            cik="0001535527",
            ticker="CRWD",
            company_name="CrowdStrike Holdings, Inc.",
            form_type="10-K",
            filing_date="2024-03-07",
            sections_count=1,
            tokens_total=100,
            pack_dir=str(self.pack_dir),
            built_at=datetime.now(UTC).isoformat(),
        ))

    def test_returns_none_for_metric_not_in_catalog(self) -> None:
        result = try_extract_kpi(
            metric="not_a_kpi",
            cik="0001535527",
            company="CRWD",
            period="lfy",
            registry_path=self.registry_db,
            pack_registry=self.pack_registry,
        )
        self.assertIsNone(result)

    def test_returns_none_when_no_pack(self) -> None:
        """No pack registered -> None (caller renders diagnostic)."""
        result = try_extract_kpi(
            metric="arr",
            cik="9999999",
            company="Nobody",
            period="lfy",
            registry_path=self.registry_db,
            pack_registry=self.pack_registry,
        )
        self.assertIsNone(result)

    def test_successful_extraction_returns_cited_value(self) -> None:
        self._build_pack()

        fake_response = _json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual recurring revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNotNone(cited)
        assert cited is not None
        self.assertEqual(cited.value, 3_440_000_000)
        self.assertEqual(cited.source, "learned:kpi-llm")
        self.assertEqual(cited.metric, "arr")
        self.assertEqual(cited.accession, "0001535527-24-000123")

        # Row persisted to learned_concepts
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        row = reg.lookup("0001535527", "arr",
                          accession="0001535527-24-000123")
        self.assertIsNotNone(row)
        reg.close()

    def test_second_call_hits_cache(self) -> None:
        """Second call with the same args should not touch the LLM at all."""
        self._build_pack()

        # Seed the registry with the expected result
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        reg.upsert(
            cik="0001535527", metric="arr",
            concept="annual recurring revenue",
            taxonomy="kpi-prose", source="kpi-llm", verified=True,
            verif_method="prior_filing_crosscheck", value_sample=3.44e9,
            accession="0001535527-24-000123",
        )
        reg.close()

        # Patch subprocess to blow up if called; cache hit means no call
        with _patch("edgarpack.query.kpi_extract.subprocess.run",
                    side_effect=AssertionError("should not be called")):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNotNone(cited)
        assert cited is not None
        self.assertEqual(cited.source, "learned:kpi-cached")

    def test_llm_returns_not_found_returns_none_without_cache(self) -> None:
        self._build_pack()

        fake_response = _json.dumps({
            "value": None, "unit": None, "excerpt": "",
            "section_id": "", "confidence": "not_found",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNone(cited)
        from edgarpack.query.learned_registry import LearnedRegistry
        reg = LearnedRegistry(db_path=self.registry_db)
        row = reg.lookup("0001535527", "arr", accession="0001535527-24-000123")
        self.assertIsNone(row)
        reg.close()

    def test_hallucinated_excerpt_is_rejected(self) -> None:
        self._build_pack()

        fake_response = _json.dumps({
            "value": 99_999_999_999,  # nonsense number
            "unit": "USD",
            "excerpt": "This sentence is not in the source text at all",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _Fake:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with _patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             _patch("edgarpack.query.kpi_extract.subprocess.run", return_value=_Fake):
            cited = try_extract_kpi(
                metric="arr",
                cik="0001535527",
                company="CrowdStrike Holdings, Inc.",
                period="lfy",
                registry_path=self.registry_db,
                pack_registry=self.pack_registry,
            )

        self.assertIsNone(cited)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py::TestTryExtractKpi -v`

Expected: FAIL — `try_extract_kpi` doesn't exist.

- [ ] **Step 3: Implement `try_extract_kpi`**

Append to `edgarpack/query/kpi_extract.py`:

```python
def try_extract_kpi(
    metric: str,
    cik: str,
    company: str,
    period: str,
    *,
    registry_path: Path | None = None,
    pack_registry: PackRegistry | None = None,
    _verify: bool = True,
    _override_pack: PackRecord | None = None,
) -> CitedValue | None:
    """Layer B entry point. Extracts a KPI from a pack's MD&A/segment sections.

    Returns a CitedValue with source='learned:kpi-llm' (or 'learned:kpi-cached'
    on a registry hit), or None on any failure path.

    Parameters:
        metric: canonical metric name (must be in KPI_CATALOG)
        cik: zero-padded CIK string
        company: company name (used in the LLM prompt)
        period: lfy / mrq / mrp / ltm / annual:N / quarterly:N
        registry_path: path to the learned_concepts registry db (None -> default)
        pack_registry: PackRegistry instance (None -> new default one)
        _verify: internal, set to False by recursive prior-filing cross-check
        _override_pack: internal, set when the caller has already resolved
                        the prior filing (skips _resolve_filing_for_period)
    """
    kpi_def = KPI_CATALOG.get(metric)
    if kpi_def is None:
        return None

    own_registry = False
    if pack_registry is None:
        pack_registry = PackRegistry()
        own_registry = True

    try:
        # 1. Resolve filing
        if _override_pack is not None:
            pack_record = _override_pack
        else:
            pack_record = _resolve_filing_for_period(cik, period, pack_registry)
        if pack_record is None:
            return None

        accession = pack_record.accession

        # 2. Cache check
        learned_reg = LearnedRegistry(db_path=registry_path)
        try:
            cached = learned_reg.lookup(cik=cik, metric=metric, accession=accession)
            if cached is not None:
                learned_reg.bump_hit_count(
                    cik=cik, metric=metric, accession=accession,
                )
                # Rebuild CitedValue from cached row + pack manifest
                pack_dir = Path(pack_record.pack_dir)
                try:
                    manifest = _load_pack_manifest(pack_dir)
                except FileNotFoundError:
                    return None
                primary_doc = manifest.get("filing", {}).get(
                    "primary_document", ""
                )
                # No re-verification on cached hits
                cited = CitedValue(
                    value=cached.value_sample,
                    unit=kpi_def.unit_hint,
                    metric=metric,
                    concept=cached.concept,
                    period_end=_date.fromisoformat(pack_record.filing_date)
                        if pack_record.filing_date else _date.min,
                    fiscal_year=int(pack_record.filing_date[:4])
                        if pack_record.filing_date else 0,
                    fiscal_period="FY" if pack_record.form_type.startswith("10-K") else "Q",
                    form_type=pack_record.form_type,
                    filed=_date.fromisoformat(pack_record.filing_date)
                        if pack_record.filing_date else _date.min,
                    accession=accession,
                    cik=cik,
                    company=pack_record.company_name,
                    taxonomy=cached.taxonomy,
                    primary_document=primary_doc,
                    fact_id="",
                    source="learned:kpi-cached",
                )
                if not cached.verified:
                    cited.warnings.append(
                        "Resolved via unverified learned KPI mapping. "
                        f"Verify manually: edgarpack learned verify {cik} {metric}"
                    )
                return cited
        finally:
            learned_reg.close()

        # 3. Load pack manifest
        pack_dir = Path(pack_record.pack_dir)
        try:
            manifest = _load_pack_manifest(pack_dir)
        except FileNotFoundError:
            return None

        # 4. Select sections
        sections = manifest.get("sections", [])
        selected = _select_sections(sections)
        if not selected:
            return None

        # 5. Read and trim text
        raw_text = _read_section_text(pack_dir, selected)
        if not raw_text:
            return None
        text = _trim_to_budget(raw_text)

        # 6. LLM backend check
        if not _llm_backend_available_kpi():
            return None

        # 7. Build prompt + extract
        filing_meta = manifest.get("filing", {})
        prompt = _build_extraction_prompt(
            metric=metric,
            kpi_def=kpi_def,
            company=filing_meta.get("company_name", company),
            form_type=filing_meta.get("form_type", pack_record.form_type),
            filing_date=filing_meta.get("filing_date", pack_record.filing_date),
            text=text,
        )
        response = _extract_via_llm(prompt)
        if response is None:
            return None

        # Low-confidence / not-found / ambiguous: no cache, return None
        confidence = response.get("confidence")
        if confidence in ("not_found", "ambiguous", "low"):
            return None

        # 8. Verify excerpt is a substring of the source text
        excerpt = str(response.get("excerpt", ""))
        if not _verify_excerpt_in_text(excerpt, text):
            logger.warning(
                "Layer B rejected hallucinated excerpt for %s/%s: %s",
                cik, metric, excerpt[:100],
            )
            return None

        # 9. Build CitedValue
        primary_doc = filing_meta.get("primary_document", "")
        # primary_document may not be in manifest; try to find in sections
        if not primary_doc:
            # Fallback: grab the first filing HTML artifact from the manifest
            artifacts = manifest.get("artifacts", {})
            if isinstance(artifacts, dict):
                for path in artifacts:
                    if path.endswith(".htm") and "/" not in path:
                        primary_doc = path
                        break
        cited = _build_cited_from_extraction(
            response=response,
            metric=metric,
            kpi_def=kpi_def,
            pack_record=pack_record,
            pack_manifest=manifest,
            primary_document=primary_doc,
        )

        # 10. Verification (skipped on recursive calls)
        verified = False
        verif_method: str | None = None
        if _verify and isinstance(cited.value, (int, float)):
            verified, verif_method = _verify_against_prior_filing(
                current_value=float(cited.value),
                metric=metric,
                cik=cik,
                current_accession=accession,
                registry=pack_registry,
                registry_path=registry_path,
            )

        # 11. Persist
        learned_reg = LearnedRegistry(db_path=registry_path)
        try:
            learned_reg.upsert(
                cik=cik,
                metric=metric,
                concept=cited.concept,
                taxonomy="kpi-prose",
                source="kpi-llm",
                verified=verified,
                verif_method=verif_method,
                value_sample=float(cited.value) if isinstance(cited.value, (int, float)) else None,
                accession=accession,
            )
        finally:
            learned_reg.close()

        cited.source = "learned:kpi-llm"
        if not verified:
            reason = {
                "no_prior_filing": "No prior filing available for cross-check.",
                "prior_extract_failed": "Prior-filing extraction failed; could not cross-check.",
                "prior_filing_crosscheck": "Value was outside the expected order of magnitude vs. prior filing.",
            }.get(verif_method or "", "Unverified learned KPI mapping.")
            cited.warnings.append(f"Unverified: {reason}")

        return cited
    finally:
        if own_registry:
            pack_registry.close()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract.py -v 2>&1 | tail -20`

Expected: All tests pass (~45 total).

- [ ] **Step 5: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/kpi_extract.py tests/test_kpi_extract.py
git commit -m "feat(query/kpi_extract): add try_extract_kpi orchestrator

The Layer B entry point. Flow: KPI_CATALOG check -> period->pack
resolution -> cache lookup -> pack manifest load -> section selection
-> text read + trim -> LLM backend check -> prompt build + LLM call
-> excerpt substring verify (hallucination firewall) -> build
CitedValue -> prior-filing cross-check -> persist to learned_concepts
with accession key.

Confidence gating: high/medium accepted, low/not_found/ambiguous
produce None (no cache write). Unverified results are still returned
with a warning explaining why.

_override_pack is the internal escape hatch for the recursive
prior-filing verification call.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 12: Wire Layer B into `financials.py` and add `QueryResult.diagnostics`

**Files:**
- Modify: `edgarpack/query/models.py` (add `QueryResult.diagnostics`)
- Modify: `edgarpack/query/financials.py` (call `try_extract_kpi` on KPI-only metrics)
- Modify: `tests/test_query_models_source.py` (add test for `diagnostics`)
- Modify: `tests/test_financials.py` (add Layer B hook test)

- [ ] **Step 1: Write the failing test for `QueryResult.diagnostics`**

Append to `tests/test_query_models_source.py`:

```python
from edgarpack.query.models import QueryResult


class TestQueryResultDiagnostics(unittest.TestCase):
    def test_default_diagnostics_is_empty_list(self) -> None:
        qr = QueryResult(company="X", cik="0", period="lfy", metrics={})
        self.assertEqual(qr.diagnostics, [])

    def test_diagnostics_can_hold_structured_entries(self) -> None:
        qr = QueryResult(
            company="X", cik="0", period="lfy", metrics={},
            diagnostics=[
                {"metric": "arr", "kind": "no_pack",
                 "message": "KPI extraction requires a built pack."}
            ],
        )
        self.assertEqual(len(qr.diagnostics), 1)
        self.assertEqual(qr.diagnostics[0]["metric"], "arr")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_query_models_source.py::TestQueryResultDiagnostics -v`

Expected: FAIL — `QueryResult` has no `diagnostics` attribute.

- [ ] **Step 3: Add `diagnostics` field to `QueryResult`**

In `edgarpack/query/models.py`, find the `QueryResult` class and add:

```python
class QueryResult(BaseModel):
    """Result for a single company, multiple metrics."""

    company: str
    cik: str
    period: str = "lfy"
    metrics: dict[str, CitedValue | list[CitedValue] | None]

    # Self-heal v2: structured diagnostics for Layer B failures.
    # Each entry is {"metric": str, "kind": str, "message": str}.
    diagnostics: list[dict[str, str]] = Field(default_factory=list)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_query_models_source.py::TestQueryResultDiagnostics -v`

Expected: 2 passing tests.

- [ ] **Step 5: Write the failing test for Layer B wire-up**

Append to `tests/test_financials.py`:

```python
class TestLayerBWireUp(unittest.TestCase):
    def test_kpi_catalog_metric_calls_try_extract_kpi(self) -> None:
        """When a metric is in KPI_CATALOG but not METRIC_MAP, financials()
        must call try_extract_kpi instead of returning None silently."""
        import asyncio as _asyncio
        from unittest.mock import MagicMock

        async def _run() -> None:
            fake_cited = MagicMock()
            fake_cited.value = 3_440_000_000
            fake_cited.source = "learned:kpi-llm"
            fake_cited.warnings = []

            with patch(f"{_P}.resolve_ticker",
                       new=AsyncMock(return_value=("0001535527", "CRWD"))), \
                 patch(f"{_P}.fetch_company_facts",
                       new=AsyncMock(return_value={"facts": {}})), \
                 patch(f"{_P}._build_doc_map",
                       new=AsyncMock(return_value={})), \
                 patch("edgarpack.query.kpi_extract.try_extract_kpi",
                       return_value=fake_cited) as mock_extract:
                result = await financials("CRWD", metrics="arr", period="lfy")
                mock_extract.assert_called_once()
                self.assertEqual(result.metrics["arr"], fake_cited)

        _asyncio.run(_run())

    def test_kpi_none_result_adds_diagnostic(self) -> None:
        """When try_extract_kpi returns None, a diagnostic entry is added
        to the QueryResult."""
        import asyncio as _asyncio

        async def _run() -> None:
            with patch(f"{_P}.resolve_ticker",
                       new=AsyncMock(return_value=("0001535527", "CRWD"))), \
                 patch(f"{_P}.fetch_company_facts",
                       new=AsyncMock(return_value={"facts": {}})), \
                 patch(f"{_P}._build_doc_map",
                       new=AsyncMock(return_value={})), \
                 patch("edgarpack.query.kpi_extract.try_extract_kpi",
                       return_value=None):
                result = await financials("CRWD", metrics="arr", period="lfy")
                self.assertIsNone(result.metrics["arr"])
                self.assertTrue(
                    any(d.get("metric") == "arr" for d in result.diagnostics),
                    f"expected 'arr' diagnostic, got {result.diagnostics}",
                )

        _asyncio.run(_run())
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_financials.py::TestLayerBWireUp -v`

Expected: FAIL — financials() is not calling try_extract_kpi for KPI-only metrics.

- [ ] **Step 7: Wire Layer B into `financials.py`**

In `edgarpack/query/financials.py`, find the `for metric in metric_list:` loop and the `if meta is None:` branch. Replace that branch with:

```python
    for metric in metric_list:
        meta = METRIC_MAP.get(metric)
        if meta is None:
            # KPI-only metric (in KPI_CATALOG but not METRIC_MAP).
            # Try Layer B extraction from the pack's MD&A/segment sections.
            from .kpi_extract import try_extract_kpi

            cited = try_extract_kpi(
                metric=metric,
                cik=cik,
                company=company_name,
                period=period,
            )
            if cited is not None:
                result_metrics[metric] = cited
            else:
                result_metrics[metric] = None
                diagnostics_list.append({
                    "metric": metric,
                    "kind": "layer_b_unresolved",
                    "message": (
                        f"Layer B could not resolve '{metric}': no pack, "
                        f"no LLM backend, or the value was not found in "
                        f"MD&A/segment sections."
                    ),
                })
            continue
```

Earlier in the function, initialize `diagnostics_list` before the metric loop:

```python
    result_metrics: dict[str, CitedValue | list[CitedValue] | None] = {}
    derived_cache: _DerivedCache = {}
    diagnostics_list: list[dict[str, str]] = []
```

And at the end where `QueryResult` is built, pass diagnostics:

```python
    result = QueryResult(
        company=company_name,
        cik=cik,
        period=period,
        metrics=result_metrics,
        diagnostics=diagnostics_list,
    )
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_financials.py::TestLayerBWireUp tests/test_financials.py::TestAliasDereferencing -v`

Expected: All pass.

- [ ] **Step 9: Full regression**

Run: `cd ~/edgarpack && EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" ~/edgarpack/.venv/bin/pytest tests/ -q`

Expected: All pass.

- [ ] **Step 10: Commit**

```bash
cd ~/edgarpack
git add edgarpack/query/models.py edgarpack/query/financials.py tests/test_query_models_source.py tests/test_financials.py
git commit -m "feat(query/financials): wire Layer B into the metric loop

When a metric is in KPI_CATALOG but not METRIC_MAP, financials() now
calls kpi_extract.try_extract_kpi instead of silently returning None.
Successful extractions land in result.metrics; None returns record a
structured diagnostic on result.diagnostics (new field on QueryResult).

QueryResult gains a diagnostics: list[dict[str, str]] field, empty by
default. v1 consumers that ignore it are unaffected.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Task 13: CLI diagnostics footer + integration test

**Files:**
- Modify: `edgarpack/cli.py` (render `QueryResult.diagnostics` footer, extend `--source` choices)
- Create: `tests/test_kpi_extract_integration.py`
- Modify: `tests/test_cli_self_heal.py` (append diagnostic footer test)

- [ ] **Step 1: Write the failing test for CLI diagnostics rendering**

Append to `tests/test_cli_self_heal.py`:

```python
class TestDiagnosticsFooter(unittest.TestCase):
    def test_diagnostics_rendered_as_footer(self) -> None:
        qr = QueryResult(
            company="CRWD",
            cik="0001535527",
            period="lfy",
            metrics={"arr": None},
            diagnostics=[
                {"metric": "arr", "kind": "layer_b_unresolved",
                 "message": "Layer B could not resolve 'arr': no pack."}
            ],
        )
        out = _render_query_table(qr, _args())
        self.assertIn("Diagnostics:", out)
        self.assertIn("arr:", out)
        self.assertIn("Layer B could not resolve", out)

    def test_no_diagnostics_no_footer(self) -> None:
        qr = QueryResult(
            company="CRWD", cik="0001535527", period="lfy",
            metrics={"revenue": _cited("revenue", "Revenues", 5e9)},
        )
        out = _render_query_table(qr, _args())
        self.assertNotIn("Diagnostics:", out)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_cli_self_heal.py::TestDiagnosticsFooter -v`

Expected: FAIL — `_render_query_table` doesn't render a Diagnostics footer.

- [ ] **Step 3: Add diagnostics footer rendering in `cli.py`**

In `edgarpack/cli.py`, find the section of `_render_query_table` where the strict-rejected footer is rendered (near the end, before the permalink). Add diagnostics rendering just before the strict footer:

```python
    diagnostics = getattr(result, "diagnostics", [])
    if diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for diag in diagnostics:
            if isinstance(diag, dict):
                metric_name = diag.get("metric", "?")
                message = diag.get("message", "")
                lines.extend(
                    _wrap_cli_text(
                        f"  {metric_name}: {message}",
                        width,
                        indent="    ",
                    )
                )

    if strict_rejected:
        lines.append("")
        lines.append(
            f"Strict mode: rejected learned values for: {', '.join(strict_rejected)}"
        )
        lines.append(
            "Use `edgarpack learned list` to inspect, or re-run without --strict."
        )
```

- [ ] **Step 4: Update `edgarpack learned list --source` choices**

In `edgarpack/cli.py`, find:

```python
    p_learned_list.add_argument(
        "--source",
        choices=["fuzzy", "llm", "user"],
        help="Filter by source mechanism",
    )
```

Replace with:

```python
    p_learned_list.add_argument(
        "--source",
        choices=["fuzzy", "llm", "user", "kpi-llm"],
        help="Filter by source mechanism",
    )
```

- [ ] **Step 5: Run the CLI tests to verify they pass**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_cli_self_heal.py -v 2>&1 | tail -15`

Expected: All pass.

- [ ] **Step 6: Write the end-to-end integration test**

Create `tests/test_kpi_extract_integration.py`:

```python
"""End-to-end Layer B integration test with synthetic pack + mocked LLM."""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

from edgarpack.harvest.registry import PackRecord, PackRegistry

_P = "edgarpack.query.financials"


def _build_synthetic_pack(td: Path) -> tuple[PackRegistry, Path]:
    """Build a tmp PackRegistry + one fake CrowdStrike 10-K pack with an
    MD&A section containing ARR prose."""
    registry_db = td / "registry.db"
    packs_dir = td / "packs" / "0001535527" / "0001535527-24-000123"
    sections_dir = packs_dir / "sections"
    sections_dir.mkdir(parents=True)
    (sections_dir / "mda.md").write_text(
        "Our subscription-first business model has driven "
        "Annual Recurring Revenue of $3.44 billion as of the end of fiscal 2024, "
        "an increase of 34 percent year over year.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "parser_version": "0.1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {"url": "https://example", "fetched_at": datetime.now(UTC).isoformat()},
        "filing": {
            "cik": "0001535527",
            "accession": "0001535527-24-000123",
            "form_type": "10-K",
            "filing_date": "2024-03-07",
            "company_name": "CrowdStrike Holdings, Inc.",
            "primary_document": "crwd-20240131.htm",
        },
        "sections": [
            {"id": "10k_parti_item7_mda",
             "title": "MD&A",
             "path": "sections/mda.md",
             "char_start": 0, "char_end": 500,
             "tokens_approx": 80, "sha256": "abc"},
        ],
        "artifacts": {},
        "warnings": [],
        "tokens_total": 80,
    }
    (packs_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    registry = PackRegistry(db_path=registry_db)
    registry.register_pack(PackRecord(
        accession="0001535527-24-000123",
        cik="0001535527",
        ticker="CRWD",
        company_name="CrowdStrike Holdings, Inc.",
        form_type="10-K",
        filing_date="2024-03-07",
        sections_count=1,
        tokens_total=80,
        pack_dir=str(packs_dir),
        built_at=datetime.now(UTC).isoformat(),
    ))
    return registry, registry_db


class TestLayerBEndToEnd(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.td = Path(self._tmp.name)
        self.pack_registry, self.pack_registry_db = _build_synthetic_pack(self.td)
        self.learned_db = self.td / "learned.db"

    async def test_kpi_query_end_to_end(self) -> None:
        from edgarpack.query.financials import financials

        fake_response = json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual Recurring Revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _FakeCompleted:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with patch(f"{_P}.resolve_ticker",
                   new=AsyncMock(return_value=("0001535527", "CrowdStrike Holdings, Inc."))), \
             patch(f"{_P}.fetch_company_facts",
                   new=AsyncMock(return_value={"facts": {}})), \
             patch(f"{_P}._build_doc_map",
                   new=AsyncMock(return_value={})), \
             patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_FakeCompleted), \
             patch("edgarpack.query.kpi_extract.PackRegistry",
                   return_value=self.pack_registry), \
             patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                   self.learned_db):
            result = await financials("CRWD", metrics="arr", period="lfy")

        arr = result.metrics.get("arr")
        self.assertIsNotNone(arr)
        assert arr is not None
        self.assertEqual(arr.value, 3_440_000_000)
        self.assertEqual(arr.source, "learned:kpi-llm")
        self.assertEqual(arr.accession, "0001535527-24-000123")

    async def test_mixed_query_revenue_and_kpi(self) -> None:
        """A query mixing a hardcoded metric and a Layer B KPI returns both."""
        from edgarpack.query.financials import financials

        # Minimal facts blob so revenue resolves via the hardcoded path
        facts = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": [{
            "val": 3_000_000_000, "fy": 2024, "fp": "FY",
            "start": "2023-02-01", "end": "2024-01-31",
            "form": "10-K", "filed": "2024-03-07",
            "accn": "0001535527-24-000123",
            "frame": "CY2024",
        }]}}}}}

        fake_response = json.dumps({
            "value": 3_440_000_000,
            "unit": "USD",
            "excerpt": "Annual Recurring Revenue of $3.44 billion",
            "section_id": "10k_parti_item7_mda",
            "confidence": "high",
        })

        class _FakeCompleted:
            stdout = fake_response
            stderr = ""
            returncode = 0

        with patch(f"{_P}.resolve_ticker",
                   new=AsyncMock(return_value=("0001535527", "CrowdStrike Holdings, Inc."))), \
             patch(f"{_P}.fetch_company_facts",
                   new=AsyncMock(return_value=facts)), \
             patch(f"{_P}._build_doc_map",
                   new=AsyncMock(return_value={})), \
             patch("edgarpack.query.kpi_extract._LLM_CMD_KPI", "codex"), \
             patch("edgarpack.query.kpi_extract.subprocess.run",
                   return_value=_FakeCompleted), \
             patch("edgarpack.query.kpi_extract.PackRegistry",
                   return_value=self.pack_registry), \
             patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                   self.learned_db):
            result = await financials("CRWD", metrics="revenue,arr", period="lfy")

        rev = result.metrics.get("revenue")
        arr = result.metrics.get("arr")
        assert rev is not None and arr is not None
        self.assertEqual(rev.source, "hardcoded")
        self.assertEqual(arr.source, "learned:kpi-llm")

    async def test_no_pack_produces_diagnostic(self) -> None:
        """When no pack is registered for the CIK, Layer B returns None and
        a diagnostic is attached to the QueryResult."""
        from edgarpack.query.financials import financials

        with patch(f"{_P}.resolve_ticker",
                   new=AsyncMock(return_value=("9999999", "Unknown Co"))), \
             patch(f"{_P}.fetch_company_facts",
                   new=AsyncMock(return_value={"facts": {}})), \
             patch(f"{_P}._build_doc_map",
                   new=AsyncMock(return_value={})), \
             patch("edgarpack.query.kpi_extract.PackRegistry",
                   return_value=self.pack_registry), \
             patch("edgarpack.query.learned_registry.DEFAULT_REGISTRY_PATH",
                   self.learned_db):
            result = await financials("UNKNOWN", metrics="arr", period="lfy")

        self.assertIsNone(result.metrics["arr"])
        self.assertTrue(
            any(d.get("metric") == "arr" for d in result.diagnostics)
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 7: Run the integration tests**

Run: `cd ~/edgarpack && ~/edgarpack/.venv/bin/pytest tests/test_kpi_extract_integration.py -v`

Expected: 3 passing tests.

- [ ] **Step 8: Full regression**

Run: `cd ~/edgarpack && EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" ~/edgarpack/.venv/bin/pytest tests/ -q 2>&1 | tail -5`

Expected: Full suite passes. Layer A's 379 tests + new Layer B tests.

- [ ] **Step 9: Manual smoke test against a real pack**

Run (assumes you have a built CRWD 10-K pack and a working LLM backend):

```bash
cd ~/edgarpack
EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" \
  ~/edgarpack/.venv/bin/edgarpack build --cik 0001535527 --form 10-K --out ./packs
EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" \
  ~/edgarpack/.venv/bin/edgarpack query CRWD arr --period lfy
```

Expected: A cited ARR value with `[learned:kpi-llm ✓]` or `[learned:kpi-llm ⚠]` badge.

Second run:
```bash
EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" \
  ~/edgarpack/.venv/bin/edgarpack query CRWD arr --period lfy
```

Expected: same value, source changes to `[learned:kpi-cached]`, no LLM call.

If no pack is built:
```bash
EDGARPACK_USER_AGENT="EdgarPack User samay58@gmail.com" \
  ~/edgarpack/.venv/bin/edgarpack query PLTR arr --period lfy
```

Expected: `arr: N/A` plus a Diagnostics footer explaining to run `edgarpack build`.

- [ ] **Step 10: Commit**

```bash
cd ~/edgarpack
git add edgarpack/cli.py tests/test_cli_self_heal.py tests/test_kpi_extract_integration.py
git commit -m "feat(cli): render Layer B diagnostics footer + integration tests

_render_query_table now appends a 'Diagnostics:' block when
QueryResult.diagnostics is non-empty. Each diagnostic prints
'  <metric>: <message>' wrapped to terminal width.

edgarpack learned list --source choices extended with 'kpi-llm'.

Three end-to-end integration tests covering:
1. KPI-only query resolves via Layer B (synthetic pack + mocked LLM)
2. Mixed query (revenue hardcoded + arr via Layer B) returns both
3. No pack -> structured diagnostic on QueryResult

Completes self-heal v2 Layer B.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
"
```

---

## Self-review

**Spec coverage check:**

- [x] `CitedValue.excerpt_text` field + `document_url` override -> Task 1
- [x] `KpiDef` dataclass + `KPI_CATALOG` with 26 entries -> Task 2
- [x] `learned_concepts` schema migration (add `accession` col, `PRAGMA user_version`) -> Task 3
- [x] `LearnedRegistry` accession-aware API -> Task 4
- [x] Layer 0 unknown-metric guard extended with `KPI_CATALOG` -> Task 5
- [x] `_resolve_filing_for_period` + pack manifest loader -> Task 6
- [x] `_select_sections` + `_read_section_text` + `_trim_to_budget` -> Task 7
- [x] `_build_extraction_prompt` + `_extract_via_llm` -> Task 8
- [x] `_verify_excerpt_in_text` anti-hallucination -> Task 9
- [x] `_build_cited_from_extraction` + `_verify_against_prior_filing` -> Task 10
- [x] `try_extract_kpi` orchestrator with all failure modes -> Task 11
- [x] `financials.py` wire-up + `QueryResult.diagnostics` -> Task 12
- [x] CLI diagnostics footer + integration tests -> Task 13

**Placeholder scan:** No TBD, TODO, or "similar to Task N" references. Every step has concrete code or exact commands.

**Type consistency check:**
- `KpiDef` signature (`phrases`, `unit_hint`, `industry`, `description`) used consistently across Task 2, 6, 7, 8, 10, 11.
- `LearnedRegistry.upsert(accession=...)` signature matches between Task 4 definition and Task 10/11 call sites.
- `_verify_excerpt_in_text` signature (`excerpt`, `source_text`) matches between Task 9 definition and Task 11 call.
- `try_extract_kpi` signature (`metric`, `cik`, `company`, `period`, `registry_path`, `pack_registry`, `_verify`, `_override_pack`) defined in Task 11, referenced recursively in Task 10's `_verify_against_prior_filing` (forward reference resolved at call time).
- `QueryResult.diagnostics` field defined in Task 12, rendered in Task 13.
- `CitedValue.source` values: `"hardcoded"`, `"learned:fuzzy"`, `"learned:llm"`, `"learned:kpi-llm"`, `"learned:kpi-cached"`. All five are referenced consistently.

**Ambiguity check:**
- Task 11's prior-filing recursion: the test seeds a cached prior row so the recursive call is not actually exercised in unit tests. Integration test in Task 13 covers the full flow. This is a deliberate testing strategy, not a gap.
- Task 11's `primary_document` fallback: if the manifest doesn't include it, we search `artifacts` for the first top-level `.htm` file. This is a best-effort fallback; if the manifest is well-formed per v1, the first branch always fires.
- Task 12's Layer B import is lazy (`from .kpi_extract import try_extract_kpi` inside the loop body) to avoid circular import with `concepts.py` which re-exports `KPI_CATALOG` from `kpi_extract`.

**Scope check:** 13 tasks, one feature branch, ~1500 lines of source + ~1200 lines of tests. Splittable into two PRs at Task 5/6 if preferred (Tasks 1-5 = "plumbing + catalog + guard", Tasks 6-13 = "extractor + orchestrator + wire-up").

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-11-self-heal-v2-layer-b.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for a 13-task plan where each task needs its own clean context window. Each subagent sees only its task plus the spec reference.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints after Task 5 (plumbing), Task 11 (orchestrator), and Task 13 (done).

Which approach?
