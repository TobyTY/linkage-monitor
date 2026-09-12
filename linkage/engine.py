"""Turning quotes into an observation.

Per linkage, per cycle: resolve the fair value from config, measure the spread
against the reference leg, score it against that linkage's own history, subtract
friction, and hand back an Observation.

Two guards matter more than the arithmetic.

Staleness. A divergence computed from a leg that stopped updating is an artefact
of the plumbing. It is also exactly what a broken feed looks like from the
inside: one price frozen, the other moving, the gap widening beautifully. Every
observation records whether any leg was too old, and a stale observation is
never eligible to alert.

Insufficient history. A z-score over eight samples is not a z-score. Below a
minimum sample count the score is None rather than a confident-looking number
computed from nothing.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from linkage.config import LinkageConfig
from linkage.formula import evaluate
from linkage.providers.base import Quote

# Below this many samples a z-score is noise dressed as a statistic.
MIN_SAMPLES_FOR_Z = 30

# Default tolerance for how old a leg may be, as a multiple of the cadence floor.
DEFAULT_MAX_AGE_MULTIPLE = 3


@dataclass
class SpreadHistory:
    """Rolling spread history for one linkage, in basis points.

    Basis points rather than absolute spread so the window survives a stock
    split, a redenomination, or simply a price that has drifted a long way over
    the window -- all of which would silently corrupt an absolute-spread mean.
    """

    window: int = 720  # 12h of minute observations
    _values: deque[float] = field(default_factory=deque)

    def __post_init__(self) -> None:
        self._values = deque(self._values, maxlen=self.window)

    def __len__(self) -> int:
        return len(self._values)

    def append(self, spread_bps: float) -> None:
        self._values.append(spread_bps)

    def z_score(self, spread_bps: float) -> float | None:
        """Score against history *excluding* the current point.

        Including it drags the mean toward the observation being scored, which
        systematically shrinks extreme readings -- precisely the readings this
        system exists to find.
        """
        if len(self._values) < MIN_SAMPLES_FOR_Z:
            return None
        stdev = statistics.stdev(self._values)
        if stdev == 0:
            return None
        return (spread_bps - statistics.fmean(self._values)) / stdev


@dataclass(frozen=True)
class Observation:
    linkage_id: str
    ts: datetime
    leg_prices: dict[str, Decimal]
    fair_value: Decimal
    reference_price: Decimal
    spread: Decimal
    spread_bps: float
    z_score: float | None
    net_edge_bps: float | None
    stale: bool
    stale_reason: str | None = None

    @property
    def alertable(self) -> bool:
        """Eligible to be considered by the state machine at all."""
        return (
            not self.stale
            and self.z_score is not None
            and self.net_edge_bps is not None
        )


def evaluate_linkage(
    linkage: LinkageConfig,
    quotes: dict[str, Quote],
    history: SpreadHistory,
    *,
    now: datetime | None = None,
    max_age_seconds: float = 180,
) -> Observation:
    """Evaluate one linkage against one cycle's quotes."""
    now = now or datetime.now(timezone.utc)

    missing = set(linkage.legs) - set(quotes)
    if missing:
        raise KeyError(
            f"{linkage.id}: no quote for leg(s) {', '.join(sorted(missing))}"
        )

    stale_reason: str | None = None
    for leg_name, quote in quotes.items():
        if quote.stale:
            stale_reason = f"{leg_name} reported stale by provider"
            break
        age = quote.age_seconds(now)
        if age > max_age_seconds:
            stale_reason = f"{leg_name} is {age:.0f}s old (limit {max_age_seconds:.0f}s)"
            break

    names: dict[str, object] = {name: q.price for name, q in quotes.items()}
    names.update(linkage.params)

    fair_value = evaluate(linkage.fair_value, names)
    reference_price = quotes[linkage.reference].price
    spread = reference_price - fair_value

    if reference_price == 0:
        raise ValueError(f"{linkage.id}: reference price is zero")
    spread_bps = float(spread / reference_price) * 10_000

    z_score = history.z_score(spread_bps)

    # Friction is unsigned: capturing the gap costs the same whichever way it
    # points. A negative net edge means the gap is smaller than the cost of
    # trading it, which is the expected answer most of the time.
    net_edge_bps = (
        abs(spread_bps) - linkage.total_friction_bps if z_score is not None else None
    )

    return Observation(
        linkage_id=linkage.id,
        ts=now,
        leg_prices={name: q.price for name, q in quotes.items()},
        fair_value=fair_value,
        reference_price=reference_price,
        spread=spread,
        spread_bps=spread_bps,
        z_score=z_score,
        net_edge_bps=net_edge_bps,
        stale=stale_reason is not None,
        stale_reason=stale_reason,
    )
