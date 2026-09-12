"""Data screening, because two bad rows can move a statistic by 120x.

This module exists because of a real failure. Yahoo returns SETFGOLD.NS at 0.42
on 2022-01-06 and 2022-01-07, against a true price near 43 -- a botched unit
adjustment. Two rows out of 1239, 0.16% of the sample, took the gold ETF pair's
spread standard deviation from roughly 15 bps to 1851 bps, and every downstream
number built on it: the half-life, the horizon gate, the net edge. The gate
reported a +1400 bps opportunity on an ETF pair that tracks to within 20 bps.

Nothing about that failure announced itself. The series had no NaNs, no infs,
no gaps. It parsed, it plotted, it produced confident numbers. The only symptom
was that the answer was absurd, and an answer only looks absurd if you already
know roughly what it should be -- which is precisely what you do not have when
scanning fifty pairs.

Two screens, both reporting what they remove rather than silently cleaning:

SPIKES. A price that moves more than `max_daily_move` in a day and comes
straight back is a bad print, not a market event. Real moves of that size
persist; data errors reverse.

MAD OUTLIERS. Median absolute deviation rather than standard deviation, because
the outlier being hunted is exactly what corrupts a standard deviation. A
3-sigma screen computed on contaminated data moves its own threshold out to
cover the contamination.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

#: A single-day log move beyond this, which then reverses, is treated as a bad
#: print. 0.4 is ~50%: far outside anything an ETF or large-cap does honestly.
DEFAULT_MAX_DAILY_MOVE = 0.4

#: Scaling that makes MAD comparable to a standard deviation for normal data.
MAD_TO_SIGMA = 1.4826


@dataclass
class ScreenReport:
    """What was removed, and why. Always surfaced, never swallowed."""

    rows_in: int
    rows_out: int
    spikes: dict[str, list[pd.Timestamp]] = field(default_factory=dict)
    outliers: list[pd.Timestamp] = field(default_factory=list)

    @property
    def removed(self) -> int:
        return self.rows_in - self.rows_out

    @property
    def removed_fraction(self) -> float:
        return self.removed / self.rows_in if self.rows_in else 0.0

    @property
    def clean(self) -> bool:
        return self.removed == 0

    def summary(self) -> str:
        if self.clean:
            return f"{self.rows_in} rows, nothing removed"
        parts = [
            f"{self.rows_in} rows, removed {self.removed} ({self.removed_fraction:.2%})"
        ]
        for symbol, dates in self.spikes.items():
            shown = ", ".join(str(d.date()) for d in dates[:3])
            more = f" +{len(dates) - 3} more" if len(dates) > 3 else ""
            parts.append(f"spike in {symbol}: {shown}{more}")
        if self.outliers:
            shown = ", ".join(str(d.date()) for d in self.outliers[:3])
            more = f" +{len(self.outliers) - 3} more" if len(self.outliers) > 3 else ""
            parts.append(f"MAD outliers: {shown}{more}")
        return "; ".join(parts)


def find_spikes(
    series: pd.Series, *, max_daily_move: float = DEFAULT_MAX_DAILY_MOVE
) -> list[pd.Timestamp]:
    """Dates where the price jumped hugely and came straight back.

    The reversal is what distinguishes a bad print from a real crash. A genuine
    50% move persists into the next session; a data error is corrected by it.
    """
    log_price = np.log(series.replace(0, np.nan)).dropna()
    if len(log_price) < 3:
        return []

    change = log_price.diff()
    next_change = change.shift(-1)

    # Big move, then a comparable move the other way.
    spiked = (
        (change.abs() > max_daily_move)
        & (next_change.abs() > max_daily_move)
        & (np.sign(change) != np.sign(next_change))
    )
    return list(log_price.index[spiked.fillna(False)])


def find_mad_outliers(spread: pd.Series, *, threshold: float = 8.0) -> list[pd.Timestamp]:
    """Spread observations absurdly far from the median, by MAD.

    MAD rather than standard deviation on purpose: a standard-deviation screen
    computed on contaminated data inflates its own threshold to cover the
    contamination, and then finds nothing.
    """
    values = spread.dropna()
    if len(values) < 30:
        return []

    median = values.median()
    mad = float((values - median).abs().median())
    if mad == 0:
        return []

    deviation = (values - median).abs() / (mad * MAD_TO_SIGMA)
    return list(values.index[deviation > threshold])


def screen(
    frame: pd.DataFrame,
    *,
    max_daily_move: float = DEFAULT_MAX_DAILY_MOVE,
    mad_threshold: float = 8.0,
) -> tuple[pd.DataFrame, ScreenReport]:
    """Remove bad prints from a two-or-more column price frame.

    Returns the cleaned frame and a report of exactly what went. The report is
    the point: a screen that silently drops data is a screen that can quietly
    delete a real crash.
    """
    frame = frame.dropna()
    report = ScreenReport(rows_in=len(frame), rows_out=len(frame))
    if frame.empty:
        return frame, report

    drop: set[pd.Timestamp] = set()
    for column in frame.columns:
        dates = find_spikes(frame[column], max_daily_move=max_daily_move)
        if dates:
            report.spikes[str(column)] = dates
            drop.update(dates)

    if len(frame.columns) >= 2:
        a, b = frame.columns[0], frame.columns[1]
        positive = (frame[a] > 0) & (frame[b] > 0)
        spread = np.log(frame.loc[positive, a]) - np.log(frame.loc[positive, b])
        outliers = find_mad_outliers(spread, threshold=mad_threshold)
        if outliers:
            report.outliers = outliers
            drop.update(outliers)

    cleaned = frame.drop(index=[d for d in drop if d in frame.index])
    report.rows_out = len(cleaned)
    return cleaned, report
