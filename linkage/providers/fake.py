"""A provider that does exactly what the test tells it to.

Every engine test runs against this rather than a live feed. Market data is the
worst possible test fixture -- it changes, it is slow, it is unavailable at
weekends, and it cannot be made to produce the edge case you need to cover. The
interesting cases here are all edge cases: a leg that has gone stale, a price
that moved four sigma, a provider that has stopped answering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from linkage.providers.base import Bar, ProviderError, Quote


class FakeProvider:
    name = "fake"

    def __init__(self, cadence_floor_seconds: int = 1) -> None:
        self._prices: dict[str, Quote] = {}
        self._bars: dict[str, list[Bar]] = {}
        self._unreachable: set[str] = set()
        self._cadence_floor = cadence_floor_seconds
        self.quote_calls: list[str] = []

    @property
    def cadence_floor_seconds(self) -> int:
        return self._cadence_floor

    # -- test controls ---------------------------------------------------

    def set_price(
        self,
        symbol: str,
        price: str | Decimal,
        *,
        age_seconds: float = 0,
        stale: bool = False,
    ) -> None:
        self._prices[symbol] = Quote(
            symbol=symbol,
            price=Decimal(str(price)),
            ts=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
            stale=stale,
        )

    def set_bars(self, symbol: str, bars: list[Bar]) -> None:
        self._bars[symbol] = bars

    def make_unreachable(self, symbol: str) -> None:
        self._unreachable.add(symbol)

    # -- provider interface ----------------------------------------------

    def quote(self, symbol: str) -> Quote:
        self.quote_calls.append(symbol)
        if symbol in self._unreachable:
            raise ProviderError(f"fake: {symbol} is unreachable")
        try:
            return self._prices[symbol]
        except KeyError:
            raise ProviderError(f"fake: no price set for {symbol}") from None

    def bars(self, symbol: str, timeframe: str, count: int) -> list[Bar]:
        return self._bars.get(symbol, [])[-count:]
