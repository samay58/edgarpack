"""XBRL data via SEC companyfacts API."""

from typing import Any

from ..config import CACHE_DIR, SEC_DATA_BASE
from .cache import DiskCache
from .client import get_client
from .submissions import normalize_cik


class XBRLFetchError(Exception):
    """Raised by `fetch_company_facts` when the fetch itself failed.

    Distinct from the 'filer has no XBRL' case, which is surfaced by
    returning {} (the SEC returns 404 for such filers). Callers that care
    about the distinction should catch this exception and render an
    explicit diagnostic instead of silent N/A. Callers that don't care
    can ignore it; they'll still see the {} fallback via the wrapper
    that swallows the error (not exposed from this module to keep the
    truthfulness property at the API boundary).
    """

    def __init__(self, cik: str, cause: Exception):
        self.cik = cik
        self.cause = cause
        super().__init__(f"companyfacts fetch failed for CIK{cik}: {type(cause).__name__}: {cause}")


async def fetch_company_facts(cik: str, force: bool = False) -> dict[str, Any]:
    """Fetch company facts JSON from SEC XBRL API.

    Returns:
        Parsed companyfacts JSON on success. {} when the filer has no
        XBRL facts (SEC 404 response).

    Raises:
        XBRLFetchError: the underlying HTTP/network/parse call failed for
            a reason other than "no such filer." Callers that want to
            distinguish this from the no-data case should catch it and
            emit a structured diagnostic. Callers that don't care can
            swallow it via a try/except and fall back to {}.
    """
    cik = normalize_cik(cik)
    url = f"{SEC_DATA_BASE}/api/xbrl/companyfacts/CIK{cik}.json"

    cache = DiskCache(CACHE_DIR)

    if not force:
        # XBRL data changes less frequently, cache for 24 hours.
        cached = cache.get(url, max_age_seconds=86400)
        if cached is not None:
            import json

            try:
                return json.loads(cached)
            except json.JSONDecodeError as e:
                raise XBRLFetchError(cik, e) from e

    client = await get_client()
    try:
        data, headers = await client.fetch_json(url)
    except Exception as e:
        # Treat SEC 404 as "this filer has no XBRL facts" rather than a
        # fetch error. Everything else (timeouts, 5xx, TLS, parse errors)
        # propagates as XBRLFetchError so callers can surface it.
        from .client import HTTPError

        if isinstance(e, HTTPError) and getattr(e, "status_code", None) == 404:
            return {}
        raise XBRLFetchError(cik, e) from e

    import json

    cache.put(url, json.dumps(data).encode(), headers)

    return data


def filter_facts_by_accession(
    facts: dict[str, Any],
    accession: str,
) -> dict[str, Any]:
    """Filter companyfacts to only include facts from a specific filing.

    Args:
        facts: Full companyfacts JSON
        accession: Accession number to filter by

    Returns:
        Filtered facts dict
    """
    # Normalize accession format (remove dashes for comparison)
    accession_nodash = accession.replace("-", "")

    result: dict[str, Any] = {}

    facts_data = facts.get("facts", {})

    for taxonomy, concepts in facts_data.items():
        if not isinstance(concepts, dict):
            continue

        taxonomy_result: dict[str, list[dict[str, Any]]] = {}

        for concept_name, concept_data in concepts.items():
            if not isinstance(concept_data, dict):
                continue

            units = concept_data.get("units", {})

            for unit_type, values in units.items():
                if not isinstance(values, list):
                    continue

                matching_values = []
                for value in values:
                    if not isinstance(value, dict):
                        continue

                    # Check if this fact is from our target filing
                    value_accession = value.get("accn", "").replace("-", "")
                    if value_accession == accession_nodash:
                        # Include relevant fields
                        matching_values.append(
                            {
                                "period": _format_period(value),
                                "value": value.get("val"),
                                "unit": unit_type,
                                "form": value.get("form"),
                                "frame": value.get("frame"),
                            }
                        )

                if matching_values:
                    if concept_name not in taxonomy_result:
                        taxonomy_result[concept_name] = []
                    taxonomy_result[concept_name].extend(matching_values)

        if taxonomy_result:
            result[taxonomy] = taxonomy_result

    return result


def _format_period(value: dict[str, Any]) -> str:
    """Format period from XBRL fact.

    Args:
        value: Single fact value dict

    Returns:
        Period string like "2023-10-01/2023-12-31" or "2023-12-31" for instant
    """
    start = value.get("start")
    end = value.get("end")

    if start and end:
        return f"{start}/{end}"
    elif end:
        return end
    else:
        return "unknown"


async def fetch_xbrl_facts(
    cik: str,
    accession: str,
    force: bool = False,
) -> dict[str, Any]:
    """Fetch XBRL facts for a specific filing.

    Args:
        cik: CIK number
        accession: Accession number
        force: Bypass cache

    Returns:
        XBRL data dict ready for output, or empty dict if unavailable
    """
    facts = await fetch_company_facts(cik, force=force)

    if not facts:
        return {}

    cik = normalize_cik(cik)
    filtered = filter_facts_by_accession(facts, accession)

    if not filtered:
        return {}

    return {
        "source": "data.sec.gov/api/xbrl/companyfacts",
        "cik": cik,
        "accession": accession,
        "facts": filtered,
    }
