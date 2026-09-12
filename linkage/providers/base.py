"""The boundary between where prices come from and what we do with them.

The engine is written against this Protocol and nothing else. Swapping
TradingView for a broker feed changes which class is constructed at startup and
nothing downstream -- that is the whole point of the abstraction, and it is what
lets the same code run in research mode today and live mode later.

The unusual member is ``cadence_floor_seconds``. Rather than a config file
asserting a poll rate the provider cannot actually meet, each provider declares
how fast it can honestly be driven and the scheduler respects it. TradingView
drives a desktop UI one symbol at a time and answers 60; a broker websocket
answers 1. Nothing else in the system changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol, runtime_checkable


class ProviderError(RuntimeError):
    """The provider could not answer. Distinct from "answered with stale data"."""


@dataclass(frozen=True)
class Quote:
    """A single price observation.

    ``stale`` is carried explicitly rather than inferred later. A provider that
    returns a cached or frozen value must say so, because a divergence computed
    from a stale leg is an artefact of the plumbing, not a market event -- and
    alerting on one is the most embarrassing failure this system could have.
    """

    symbol: str
    price: Decimal
    ts: datetime
    stale: bool = False

    def age_seconds(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        return (now - self.ts).total_seconds()


@dataclass(frozen=True)
class Bar:
    symbol: str
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None = None


@runtime_checkable
class MarketDataProvider(Protocol):
    """What the engine is allowed to assume about a price source."""

    name: str

    @property
    def cadence_floor_seconds(self) -> int:
        """The fastest this provider can honestly be polled, in seconds.

        Honesty matters more than the number. A provider that claims 1 and
        delivers 60 produces a system that silently alerts on stale data.
        """
        ...

    def quote(self, symbol: str) -> Quote:
        """Latest price for one symbol. Raises ProviderError if unreachable."""
        ...

    def bars(self, symbol: str, timeframe: str, count: int) -> list[Bar]:
        """Historical bars, oldest first."""
        ...
