"""SQLite DAO for the learned_concepts table.

Shares ~/.edgarpack/registry.db with harvest/registry.py but owns a separate
table. Thin wrapper over raw SQL; no ORM, no migrations framework.

Schema:
    learned_concepts (
        cik, metric, concept, taxonomy,
        source ('fuzzy' | 'llm' | 'user'),
        verified (0/1), verif_method, value_sample,
        learned_at, hit_count, accession
    )
    PRIMARY KEY (cik, accession, metric)

PRAGMA user_version ownership: this module claims PRAGMA user_version as
its migration counter. harvest/registry.py uses a try/except _MIGRATIONS
list and does NOT touch user_version. If harvest ever adopts user_version-
based migrations, the two owners must coordinate (e.g. move to per-table
metadata rows) or one will silently skip migrations on existing databases.

Migration history:
    v0 -> v1: add accession column (Task 3)
    v1 -> v2: rebuild table to replace PRIMARY KEY (cik, metric) with
              PRIMARY KEY (cik, accession, metric) so that per-filing
              rows with the same (cik, metric) but different accessions
              can coexist (Task 4).
    v2 -> v3: add company_kpis table (per-company discovered KPIs for
              `edgarpack which`, keyed by (cik, accession, slug)).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import CACHE_DIR

DEFAULT_REGISTRY_PATH = CACHE_DIR.parent / "registry.db"

_SCHEMA = """
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
    accession     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (cik, accession, metric)
);

CREATE INDEX IF NOT EXISTS idx_learned_source
    ON learned_concepts(source);
CREATE INDEX IF NOT EXISTS idx_learned_hit_count
    ON learned_concepts(hit_count DESC);
"""

_COMPANY_KPIS_SCHEMA = """
CREATE TABLE IF NOT EXISTS company_kpis (
    cik              TEXT NOT NULL,
    accession        TEXT NOT NULL,
    slug             TEXT NOT NULL,
    display_name     TEXT NOT NULL,
    aliases          TEXT,
    unit             TEXT,
    magnitude        TEXT,
    value            REAL,
    period_end       TEXT NOT NULL,
    fiscal_year      INTEGER NOT NULL DEFAULT 0,
    fiscal_period    TEXT NOT NULL DEFAULT '',
    form_type        TEXT NOT NULL DEFAULT '',
    definition       TEXT,
    section_id       TEXT,
    chunk_id         TEXT,
    source_substring TEXT,
    confidence       REAL,
    extracted_at     TEXT NOT NULL,
    PRIMARY KEY (cik, accession, slug)
);

CREATE INDEX IF NOT EXISTS idx_company_kpis_cik_slug
    ON company_kpis(cik, slug);
CREATE INDEX IF NOT EXISTS idx_company_kpis_cik_period
    ON company_kpis(cik, period_end);
"""

_REBUILD_TABLE_SQL = """
BEGIN;

CREATE TABLE learned_concepts_new (
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
    accession     TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (cik, accession, metric)
);

INSERT INTO learned_concepts_new
    SELECT cik, metric, concept, taxonomy, source,
           verified, verif_method, value_sample, learned_at, hit_count,
           COALESCE(accession, '') AS accession
    FROM learned_concepts;

DROP TABLE learned_concepts;

ALTER TABLE learned_concepts_new RENAME TO learned_concepts;

CREATE INDEX IF NOT EXISTS idx_learned_source
    ON learned_concepts(source);
CREATE INDEX IF NOT EXISTS idx_learned_hit_count
    ON learned_concepts(hit_count DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_cik_accn_metric
    ON learned_concepts(cik, accession, metric);

COMMIT;
"""


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


@dataclass(frozen=True)
class CompanyKpiRow:
    """Per-filing discovered KPI row backing `edgarpack which`.

    Represents a single KPI disclosure found in one filing. The `which`
    aggregator merges rows across filings on (cik, slug) to produce the
    per-company period matrix surfaced to the user.

    aliases is a JSON-serialized list of prior display names the
    canonicalization pass has mapped to this slug. Empty list (or None when
    never set) means the slug is new or the raw display name is the only
    known spelling.
    """

    cik: str
    accession: str
    slug: str
    display_name: str
    aliases: list[str]
    unit: str | None
    magnitude: str | None
    value: float | None
    period_end: str
    fiscal_year: int
    fiscal_period: str
    form_type: str
    definition: str | None
    section_id: str | None
    chunk_id: str | None
    source_substring: str | None
    confidence: float | None
    extracted_at: str


class LearnedRegistry:
    """SQLite-backed registry of learned metric -> concept mappings."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_REGISTRY_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _ensure_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SCHEMA)
        current_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version < 1:
            # v0 -> v1: add accession column and (cik, accession, metric) unique index
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(learned_concepts)").fetchall()
            }
            if "accession" not in existing_cols:
                conn.execute(
                    "ALTER TABLE learned_concepts ADD COLUMN accession TEXT NOT NULL DEFAULT ''"
                )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_learned_cik_accn_metric "
                "ON learned_concepts(cik, accession, metric)"
            )
            conn.execute("PRAGMA user_version = 1")
            conn.commit()
            current_version = 1
        if current_version < 2:
            # v1 -> v2: rebuild table to drop PRIMARY KEY (cik, metric) and
            # replace it with PRIMARY KEY (cik, accession, metric) so that
            # per-filing rows with the same (cik, metric) can coexist.
            conn.executescript(_REBUILD_TABLE_SQL)
            conn.execute("PRAGMA user_version = 2")
            current_version = 2
        if current_version < 3:
            # v2 -> v3: add company_kpis table for per-company discovered
            # KPIs surfaced by `edgarpack which`. Idempotent create so
            # re-running on a v3 db is harmless.
            conn.executescript(_COMPANY_KPIS_SCHEMA)
            conn.execute("PRAGMA user_version = 3")
        conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

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
                "SELECT * FROM learned_concepts WHERE cik = ? AND metric = ? AND accession = ''",
                (cik, metric),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM learned_concepts WHERE cik = ? AND metric = ? AND accession = ?",
                (cik, metric, accession),
            )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dataclass(row)

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
                cik,
                metric,
                concept,
                taxonomy,
                source,
                1 if verified else 0,
                verif_method,
                value_sample,
                datetime.now(UTC).isoformat(),
                accession,
            ),
        )
        conn.commit()

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

    def verify_row(
        self,
        cik: str,
        metric: str,
        accession: str | None = None,
    ) -> None:
        """Mark a learned row as verified (verif_method='manual').

        Mirrors lookup/bump_hit_count semantics: accession=None targets the
        whole-company (v1) row with accession=''; a specific accession
        targets that per-filing row only.
        """
        conn = self._get_conn()
        if accession is None:
            conn.execute(
                "UPDATE learned_concepts "
                "SET verified = 1, verif_method = 'manual' "
                "WHERE cik = ? AND metric = ? AND accession = ''",
                (cik, metric),
            )
        else:
            conn.execute(
                "UPDATE learned_concepts "
                "SET verified = 1, verif_method = 'manual' "
                "WHERE cik = ? AND metric = ? AND accession = ?",
                (cik, metric, accession),
            )
        conn.commit()

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

    # ------------------------------------------------------------------
    # company_kpis DAO (`edgarpack which`)
    # ------------------------------------------------------------------

    def company_kpi_has_accession(self, cik: str, accession: str) -> bool:
        """True when any company_kpis row exists for this (cik, accession).

        Used as the cache-hit check for `discover_kpis`: one extraction pass
        persists multiple rows for a filing at once, so the presence of any
        row means the pass has already run. The special sentinel slug
        `__no_kpis_found__` records a negative result.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT 1 FROM company_kpis WHERE cik = ? AND accession = ? LIMIT 1",
            (cik, accession),
        ).fetchone()
        return row is not None

    def company_kpi_upsert(
        self,
        *,
        cik: str,
        accession: str,
        slug: str,
        display_name: str,
        aliases: list[str] | None = None,
        unit: str | None = None,
        magnitude: str | None = None,
        value: float | None = None,
        period_end: str,
        fiscal_year: int = 0,
        fiscal_period: str = "",
        form_type: str = "",
        definition: str | None = None,
        section_id: str | None = None,
        chunk_id: str | None = None,
        source_substring: str | None = None,
        confidence: float | None = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO company_kpis (
                cik, accession, slug, display_name, aliases,
                unit, magnitude, value, period_end,
                fiscal_year, fiscal_period, form_type,
                definition, section_id, chunk_id, source_substring,
                confidence, extracted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cik, accession, slug) DO UPDATE SET
                display_name     = excluded.display_name,
                aliases          = excluded.aliases,
                unit             = excluded.unit,
                magnitude        = excluded.magnitude,
                value            = excluded.value,
                period_end       = excluded.period_end,
                fiscal_year      = excluded.fiscal_year,
                fiscal_period    = excluded.fiscal_period,
                form_type        = excluded.form_type,
                definition       = excluded.definition,
                section_id       = excluded.section_id,
                chunk_id         = excluded.chunk_id,
                source_substring = excluded.source_substring,
                confidence       = excluded.confidence,
                extracted_at     = excluded.extracted_at
            """,
            (
                cik,
                accession,
                slug,
                display_name,
                json.dumps(aliases or []),
                unit,
                magnitude,
                value,
                period_end,
                int(fiscal_year or 0),
                fiscal_period or "",
                form_type or "",
                definition,
                section_id,
                chunk_id,
                source_substring,
                confidence,
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.commit()

    def company_kpi_mark_empty(
        self,
        *,
        cik: str,
        accession: str,
        form_type: str = "",
        period_end: str = "",
    ) -> None:
        """Persist a negative-result marker for a (cik, accession) pass.

        The marker is a sentinel row with slug='__no_kpis_found__'. It exists
        so a subsequent `company_kpi_has_accession` call returns True and
        skips re-running the LLM on a filing that genuinely has no KPIs.
        """
        self.company_kpi_upsert(
            cik=cik,
            accession=accession,
            slug="__no_kpis_found__",
            display_name="",
            aliases=[],
            unit=None,
            value=None,
            period_end=period_end or "",
            form_type=form_type,
        )

    def company_kpi_list(
        self,
        *,
        cik: str,
        slug: str | None = None,
        accession: str | None = None,
        include_sentinel: bool = False,
    ) -> list[CompanyKpiRow]:
        sql = "SELECT * FROM company_kpis WHERE cik = ?"
        params: list[object] = [cik]
        if slug is not None:
            sql += " AND slug = ?"
            params.append(slug)
        if accession is not None:
            sql += " AND accession = ?"
            params.append(accession)
        if not include_sentinel:
            sql += " AND slug != '__no_kpis_found__'"
        sql += " ORDER BY period_end DESC, slug ASC"
        conn = self._get_conn()
        cur = conn.execute(sql, tuple(params))
        return [_company_kpi_row_to_dataclass(r) for r in cur.fetchall()]

    def company_kpi_distinct_slugs(self, cik: str) -> list[str]:
        """Return all slugs known for this CIK across all cached filings.

        Fed into the canonicalization pass so a new filing can reuse slugs
        coined by earlier filings (drift dedupe: 'active designers' in 2023
        -> 'paid_seats' coined in 2024).
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT DISTINCT slug FROM company_kpis "
            "WHERE cik = ? AND slug != '__no_kpis_found__' "
            "ORDER BY slug",
            (cik,),
        ).fetchall()
        return [r["slug"] for r in rows]

    def company_kpi_clear(
        self,
        *,
        cik: str | None = None,
        accession: str | None = None,
    ) -> int:
        if cik is None and accession is None:
            raise ValueError(
                "company_kpi_clear: refusing to clear entire table without cik/accession"
            )
        sql = "DELETE FROM company_kpis WHERE 1=1"
        params: list[object] = []
        if cik is not None:
            sql += " AND cik = ?"
            params.append(cik)
        if accession is not None:
            sql += " AND accession = ?"
            params.append(accession)
        conn = self._get_conn()
        cur = conn.execute(sql, tuple(params))
        conn.commit()
        return cur.rowcount or 0


def _company_kpi_row_to_dataclass(row: sqlite3.Row) -> CompanyKpiRow:
    raw_aliases = row["aliases"] if row["aliases"] else "[]"
    try:
        aliases = json.loads(raw_aliases) if isinstance(raw_aliases, str) else []
    except json.JSONDecodeError:
        aliases = []
    if not isinstance(aliases, list):
        aliases = []
    return CompanyKpiRow(
        cik=row["cik"],
        accession=row["accession"],
        slug=row["slug"],
        display_name=row["display_name"] or "",
        aliases=[str(a) for a in aliases],
        unit=row["unit"],
        magnitude=row["magnitude"],
        value=row["value"],
        period_end=row["period_end"] or "",
        fiscal_year=int(row["fiscal_year"] or 0),
        fiscal_period=row["fiscal_period"] or "",
        form_type=row["form_type"] or "",
        definition=row["definition"],
        section_id=row["section_id"],
        chunk_id=row["chunk_id"],
        source_substring=row["source_substring"],
        confidence=row["confidence"],
        extracted_at=row["extracted_at"] or "",
    )


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
