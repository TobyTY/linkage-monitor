"""Durable detector state, and a record of what the thing actually said.

Until now every process restart was a lobotomy. The Kalman filter went back to
beta=1 with a covariance saying "no idea", the percentile window went back to
empty, and the detector spent its next hundred-odd cycles being honestly
useless. That is fine for a script you run to look at something. It is fatal for
a monitor, because the only way to run one continuously on a free dyno -- which
restarts it daily -- is for it to wake up knowing what it knew yesterday.

Three tables, and they are not the same kind of thing:

    detector_state   one row per linkage, overwritten. Mutable, disposable,
                     reconstructible from history at the cost of a warmup.
    alerts           append-only. What fired, on what numbers, and what the
                     model predicted at the time.
    observations     append-only. Every non-stale reading.

The append-only pair is the point. A backtest says the rule would have worked;
only a log of live alerts and the prices around them says whether it did. The
predicted reversion is stored beside each alert precisely so that it can be
compared with what happened afterwards, by joining against observations. A
system that alerts but keeps no record of its alerts can never be wrong, which
is a much worse property than being wrong.

ON THE FINGERPRINT. Restoring state across a config edit is the failure this
module is most likely to cause, so it is checked rather than trusted. Each row
carries the fingerprint of the linkage definition that produced it, and a
mismatch discards the state and says so. Warming up again costs minutes; a
Kalman filter resuming with three hundred observations' worth of confidence
about a formula that has since changed costs correctness, silently, and looks
exactly like a working detector.

ON THE SCHEMA. There are no migrations here, unlike the ledger. That is a
deliberate asymmetry, not laziness: ledger rows are the authoritative record of
money and can never be regenerated, while every row here is either disposable
(state) or reconstructible from market data (observations). `create_schema` is
idempotent and the cost of being wrong is a re-warm.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine

from linkage.config import LinkageConfig
from linkage.detector import LinkageDetector, StateVersionMismatch, Verdict
from linkage.engine import Observation

logger = logging.getLogger("linkage.store")

metadata = MetaData()

detector_state = Table(
    "detector_state",
    metadata,
    Column("linkage_id", String(64), primary_key=True),
    Column("fingerprint", String(32), nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("last_alert_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

alerts = Table(
    "alerts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("linkage_id", String(64), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("fingerprint", String(32), nullable=False),
    Column("category", String(16), nullable=False),
    Column("spread_bps", Float, nullable=False),
    Column("kalman_z", Float),
    Column("beta", Float),
    Column("percentile", Float),
    Column("half_life_days", Float),
    Column("theta_tstat", Float),
    # What the model claimed at the moment it fired. Stored so that it can be
    # held against what the spread actually did, later, by someone who was not
    # in the room when it fired.
    Column("predicted_reversion_bps", Float),
    Column("friction_bps", Float, nullable=False),
    Column("predicted_net_bps", Float),
    Index("ix_alerts_linkage_ts", "linkage_id", "ts"),
)

observations = Table(
    "observations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("linkage_id", String(64), nullable=False),
    Column("ts", DateTime(timezone=True), nullable=False),
    Column("fingerprint", String(32), nullable=False),
    Column("reference_price", Float, nullable=False),
    Column("fair_value", Float, nullable=False),
    Column("spread_bps", Float, nullable=False),
    Index("ix_observations_linkage_ts", "linkage_id", "ts"),
)


@dataclass(frozen=True)
class LoadResult:
    """What came back, and -- as importantly -- why nothing did."""

    detector: LinkageDetector | None
    last_alert: datetime | None
    reason: str

    @property
    def restored(self) -> bool:
        return self.detector is not None


def _utc(value: datetime | None) -> datetime | None:
    """SQLite forgets timezones; Postgres does not. Normalise to aware UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _select_driver() -> str:
    """psycopg unless it cannot be imported, and say so when it cannot."""
    forced = os.environ.get("LINKAGE_DRIVER", "").strip().lower()
    if forced in ("psycopg", "pg8000"):
        return forced

    try:
        import psycopg  # noqa: F401
    except Exception:
        print(
            "WARNING: psycopg could not be imported, falling back to pg8000. "
            "That is slower and is not what CI runs.",
            file=sys.stderr,
        )
        return "pg8000"
    return "psycopg"


class StateStore:
    """Reads and writes detector state. One per process."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def connect(cls, url: str, *, echo: bool = False) -> StateStore:
        # psycopg3, matching the ledger. SQLAlchemy defaults to psycopg2 for a
        # bare postgresql:// URL, which is not installed.
        #
        # pg8000 is a fallback for one specific failure: a machine security
        # policy that deletes the libpq DLLs psycopg ships, which makes psycopg
        # unimportable and is not fixable from Python. It is pure Python and so
        # cannot be blocked that way. Set LINKAGE_DRIVER=pg8000 to force it;
        # otherwise it is chosen only when psycopg genuinely will not import,
        # and that choice is announced rather than made quietly.
        #
        # Nothing in this module depends on driver-specific error shapes -- the
        # ledger's SQLSTATE handling does, and that is why it reads the code
        # three different ways -- so the swap is safe here.
        driver = _select_driver()
        connect_args: dict = {}
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", f"postgresql+{driver}://", 1)
        if driver == "pg8000" and url.startswith("postgresql+pg8000://"):
            # pg8000 does not understand sslmode in the query string and raises
            # on it. Neon requires TLS, so it is translated rather than dropped.
            if "sslmode" in url:
                connect_args = {"ssl_context": True}
            url = url.split("?")[0]
        store = cls(create_engine(url, echo=echo, future=True, connect_args=connect_args))
        store.create_schema()
        return store

    def create_schema(self) -> None:
        metadata.create_all(self.engine)

    # ---- detector state ----------------------------------------------------

    def load(self, linkage: LinkageConfig) -> LoadResult:
        """Resume this linkage's detector, or explain why it starts fresh."""
        with self.engine.connect() as conn:
            row = conn.execute(
                select(detector_state).where(
                    detector_state.c.linkage_id == linkage.id
                )
            ).one_or_none()

        if row is None:
            return LoadResult(None, None, "no stored state")

        if row.fingerprint != linkage.state_fingerprint:
            # The formula, a parameter, a symbol or the reference leg changed.
            # The stored numbers describe the old quantity.
            return LoadResult(
                None,
                None,
                f"config changed since {row.updated_at:%Y-%m-%d %H:%M} "
                f"({row.fingerprint} -> {linkage.state_fingerprint}); "
                "discarding state",
            )

        try:
            detector = LinkageDetector.restore(row.snapshot)
        except StateVersionMismatch as exc:
            return LoadResult(None, None, f"{exc}; discarding state")
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("%s: corrupt snapshot (%s)", linkage.id, exc)
            return LoadResult(None, None, f"unreadable snapshot: {exc}")

        return LoadResult(
            detector,
            _utc(row.last_alert_at),
            f"resumed at {detector.seen} observations "
            f"(saved {_utc(row.updated_at):%Y-%m-%d %H:%M} UTC)",
        )

    def save(
        self,
        linkage: LinkageConfig,
        detector: LinkageDetector,
        *,
        last_alert: datetime | None = None,
    ) -> None:
        """Overwrite this linkage's state. Called every cycle."""
        payload = {
            "fingerprint": linkage.state_fingerprint,
            "snapshot": detector.snapshot(),
            "last_alert_at": last_alert,
            "updated_at": datetime.now(timezone.utc),
        }
        with self.engine.begin() as conn:
            updated = conn.execute(
                detector_state.update()
                .where(detector_state.c.linkage_id == linkage.id)
                .values(**payload)
            ).rowcount
            if not updated:
                conn.execute(
                    detector_state.insert().values(linkage_id=linkage.id, **payload)
                )

    # ---- the append-only record --------------------------------------------

    def record_alert(self, linkage: LinkageConfig, verdict: Verdict) -> None:
        gate, ou = verdict.gate, verdict.ou
        with self.engine.begin() as conn:
            conn.execute(
                alerts.insert().values(
                    linkage_id=linkage.id,
                    ts=verdict.ts,
                    fingerprint=linkage.state_fingerprint,
                    category=linkage.category.value,
                    spread_bps=verdict.spread_bps if verdict.spread_bps is not None else 0.0,
                    kalman_z=verdict.z,
                    beta=verdict.kalman.beta if verdict.kalman else None,
                    percentile=verdict.threshold.percentile
                    if verdict.threshold
                    else None,
                    half_life_days=ou.half_life if ou else None,
                    theta_tstat=ou.theta_tstat if ou else None,
                    predicted_reversion_bps=gate.expected_reversion_bps
                    if gate
                    else None,
                    friction_bps=linkage.total_friction_bps,
                    predicted_net_bps=gate.net_after_friction_bps if gate else None,
                )
            )

    def record_observations(
        self, batch: list[tuple[LinkageConfig, Observation]]
    ) -> None:
        """One insert for the whole cycle, not one per linkage."""
        rows = [
            {
                "linkage_id": linkage.id,
                "ts": obs.ts,
                "fingerprint": linkage.state_fingerprint,
                "reference_price": float(obs.reference_price),
                "fair_value": float(obs.fair_value),
                "spread_bps": obs.spread_bps,
            }
            for linkage, obs in batch
            if not obs.stale
        ]
        if not rows:
            return
        with self.engine.begin() as conn:
            conn.execute(observations.insert(), rows)

    def alert_count(self, linkage_id: str | None = None) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(alerts)
        if linkage_id:
            stmt = stmt.where(alerts.c.linkage_id == linkage_id)
        with self.engine.connect() as conn:
            return int(conn.execute(stmt).scalar_one())
