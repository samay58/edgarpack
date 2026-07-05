"""Shared exception types used across resolver and CLI layers.

Kept in a leaf module so both ``edgarpack.identity`` and
``edgarpack.sec.tickers`` can raise them without creating an import cycle
through ``edgarpack.harvest``.
"""

from __future__ import annotations


class UnknownCompany(ValueError):  # noqa: N818
    """No company matches the given ticker/CIK/name."""


class AmbiguousCompany(ValueError):  # noqa: N818
    """A company name matches multiple rows; caller must disambiguate."""


class VenueNotAvailable(ValueError):  # noqa: N818
    """The requested --venue has no identifier on this universe entry."""
