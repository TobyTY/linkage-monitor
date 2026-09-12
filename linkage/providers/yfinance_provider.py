"""Yahoo Finance provider.

The first provider that actually runs inside this process. TradingView's MCP
drives a desktop application over CDP and is an excellent research instrument,
but it is not something a Python service can call -- so the pipeline is built
against yfinance, which covers everything the starting universe needs: ADRs,
NSE listings, FX crosses, and commodity futures.

Two honesty constraints shape this file:

Delay. Yahoo's intraday data is delayed -- typically 15 minutes, more for some
venues, and the delay is not published per symbol. Rather than pretend
otherwise, every quote carries the timestamp of the bar it came from, and the
engine decides what is too old. A price is never dressed up as fresher than it
is.

Batching. One ``yf.download`` covering every symbol in the cycle is far cheaper
than one call per leg, and Yahoo rate-limits aggressively. ``prefetch`` pulls the
whole universe in one request; ``quote`` then reads from that snapshot.
"""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from linkage.providers.base import Bar, ProviderError, Quote

logger = logging.getLogger(__name__)

_CACHE_RELOCATED = False

_TIMEFRAME_TO_INTERVAL = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "60m",
    "1d": "1d",
}


class YFinanceProvider:
    """Free, delayed, batched. Good enough for a 48-72h horizon."""

    name = "yfinance"

    def __init__(self, interval: str = "1m", lookback: str = "2d") -> None:
        self._interval = interval
        self._lookback = lookback
        self._snapshot: dict[str, Quote] = {}

    @property
    def cadence_floor_seconds(self) -> int:
        """Sixty seconds, and not because of politeness.

        Yahoo's finest granularity is one-minute bars and the feed is delayed
        anyway, so polling faster returns the same bar repeatedly while burning
        through the rate limit. The honest floor is the bar interval.
        """
        return 60

    # -- provider interface ----------------------------------------------

    @staticmethod
    def _relocate_cache() -> None:
        """Move yfinance's sqlite cache off OneDrive.

        yfinance keeps a timezone cache in a platform data directory. When the
        project lives under a synced folder, OneDrive holds file locks on it and
        downloads fail intermittently with "database is locked" -- and because
        the failure is per-symbol, it looks like a bad ticker rather than an
        environment problem. Pinning the cache to a local path removes it.
        """
        global _CACHE_RELOCATED
        if _CACHE_RELOCATED:
            return
        try:
            import yfinance as yf

            cache_dir = Path(
                os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            ) / "linkage-monitor" / "yf-cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            yf.set_tz_cache_location(str(cache_dir))
        except Exception as exc:  # noqa: BLE001 - a cache location is best-effort
            logger.debug("could not relocate yfinance cache: %s", exc)
        _CACHE_RELOCATED = True

    def prefetch(self, symbols: Iterable[str]) -> None:
        symbols = sorted(set(symbols))
        if not symbols:
            return

        import yfinance as yf  # imported lazily; it is slow and noisy at import

        self._relocate_cache()

        frame = yf.download(
            tickers=symbols,
            period=self._lookback,
            interval=self._interval,
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
        if frame is None or frame.empty:
            raise ProviderError(
                f"yfinance returned nothing for {len(symbols)} symbol(s); "
                "market closed, symbols wrong, or rate limited"
            )

        snapshot: dict[str, Quote] = {}
        for symbol in symbols:
            try:
                series = frame[symbol]["Close"] if len(symbols) > 1 else frame["Close"]
            except (KeyError, TypeError):
                logger.warning("yfinance: no column for %s", symbol)
                continue

            series = series.dropna()
            if series.empty:
                logger.warning("yfinance: no non-null closes for %s", symbol)
                continue

            ts = series.index[-1].to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)

            snapshot[symbol] = Quote(
                symbol=symbol,
                price=Decimal(str(round(float(series.iloc[-1]), 6))),
                ts=ts.astimezone(timezone.utc),
                stale=False,  # age is the engine's judgement, from ts
            )

        self._snapshot = snapshot

    def quote(self, symbol: str) -> Quote:
        try:
            return self._snapshot[symbol]
        except KeyError:
            raise ProviderError(
                f"yfinance: {symbol} not in the current snapshot -- "
                "call prefetch() first, or the symbol is wrong"
            ) from None

    def bars(self, symbol: str, timeframe: str, count: int) -> list[Bar]:
        import yfinance as yf

        interval = _TIMEFRAME_TO_INTERVAL.get(timeframe, timeframe)
        frame = yf.Ticker(symbol).history(
            period="max" if interval == "1d" else "7d",
            interval=interval,
            auto_adjust=False,
        )
        if frame is None or frame.empty:
            raise ProviderError(f"yfinance: no bars for {symbol} at {interval}")

        frame = frame.dropna().tail(count)
        out: list[Bar] = []
        for ts, row in frame.iterrows():
            ts = ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            out.append(
                Bar(
                    symbol=symbol,
                    ts=ts.astimezone(timezone.utc),
                    open=Decimal(str(round(float(row["Open"]), 6))),
                    high=Decimal(str(round(float(row["High"]), 6))),
                    low=Decimal(str(round(float(row["Low"]), 6))),
                    close=Decimal(str(round(float(row["Close"]), 6))),
                    volume=Decimal(str(int(row["Volume"]))) if "Volume" in row else None,
                )
            )
        return out
