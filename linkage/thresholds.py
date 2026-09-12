"""Empirical thresholds, because spreads are not Gaussian.

A z-score of 3 is quoted as a one-in-370 event. That number comes from the
normal distribution, and spread series are not normal -- they have fat tails,
so three-sigma readings arrive several times more often than the arithmetic
promises. The consequence is not academic: a detector set at 3 sigma expecting
one alert a year gets one a month, the channel fills with noise, and the
threshold gets raised for the wrong reason.

So score against the observed distribution instead of an assumed one. "This
deviation is larger than 99.2% of everything I have seen on this pair" is a
statement about reality. "This is 3 sigma" is a statement about an assumption.

`sigma_lie` reports the gap directly: how often |z| > 3 actually occurred,
against the 0.27% a normal distribution predicts. It belongs in the README of
any pairs project that quotes sigma thresholds.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

MIN_SAMPLES = 100
NORMAL_3SIGMA_RATE = 0.0026998  # two-tailed P(|Z| > 3)


@dataclass(frozen=True)
class ThresholdReading:
    value: float
    percentile: float        # where this sits in the observed distribution, 0-100
    exceeds_warn: bool
    exceeds_alert: bool
    samples: int

    @property
    def tail_probability(self) -> float:
        """Observed frequency of a move at least this extreme, either direction."""
        return 2 * min(self.percentile, 100 - self.percentile) / 100


class EmpiricalThreshold:
    """Percentile-based thresholds over a rolling window of spread readings."""

    def __init__(
        self,
        *,
        window: int = 750,
        warn_percentile: float = 95.0,
        alert_percentile: float = 99.0,
    ) -> None:
        if not 0 < warn_percentile < alert_percentile < 100:
            raise ValueError("need 0 < warn < alert < 100")
        self.window = window
        self.warn_percentile = warn_percentile
        self.alert_percentile = alert_percentile
        self._values: deque[float] = deque(maxlen=window)

    def __len__(self) -> int:
        return len(self._values)

    def append(self, value: float) -> None:
        if math.isfinite(value):
            self._values.append(float(value))

    @property
    def ready(self) -> bool:
        return len(self._values) >= MIN_SAMPLES

    def score(self, value: float) -> ThresholdReading | None:
        """Where does `value` sit in the observed distribution?

        Scored against history EXCLUDING the current reading, for the same
        reason the rolling z-score excludes it: a point included in its own
        reference distribution is dragged toward the middle of it.
        """
        if not self.ready:
            return None

        history = np.fromiter(self._values, dtype=float)
        percentile = float((history < value).mean() * 100)

        # Thresholds are two-tailed: a deviation is extreme in either direction.
        warn_hi = float(np.percentile(history, self.warn_percentile))
        warn_lo = float(np.percentile(history, 100 - self.warn_percentile))
        alert_hi = float(np.percentile(history, self.alert_percentile))
        alert_lo = float(np.percentile(history, 100 - self.alert_percentile))

        return ThresholdReading(
            value=value,
            percentile=percentile,
            exceeds_warn=value > warn_hi or value < warn_lo,
            exceeds_alert=value > alert_hi or value < alert_lo,
            samples=len(history),
        )

    def sigma_lie(self) -> tuple[float, float]:
        """(observed rate of |z|>3, normal-implied rate).

        The ratio between them is how much a sigma-based threshold
        under-estimates its own alert rate on this series.
        """
        if not self.ready:
            return (float("nan"), NORMAL_3SIGMA_RATE)
        history = np.fromiter(self._values, dtype=float)
        sd = history.std(ddof=1)
        if sd == 0:
            return (0.0, NORMAL_3SIGMA_RATE)
        z = np.abs((history - history.mean()) / sd)
        return (float((z > 3).mean()), NORMAL_3SIGMA_RATE)
