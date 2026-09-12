"""Turning a stream of observations into episodes.

A divergence is not an event, it is a period. Without this layer an alert fires
on every poll for as long as the gap persists -- a hundred notifications for one
occurrence, which trains you to ignore all of them. Muted alerts are worse than
no alerts, because you still believe you are being watched.

So each linkage carries a state, an episode opens when the spread first stretches
and closes when it relaxes, and exactly one notification is emitted per episode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from linkage.config import LinkageConfig
from linkage.engine import Observation


class SignalState(str, Enum):
    DORMANT = "dormant"
    WATCHING = "watching"
    ALERT = "alert"
    DECAYING = "decaying"


@dataclass
class Episode:
    linkage_id: str
    state: SignalState = SignalState.DORMANT
    opened_at: datetime | None = None
    alerted_at: datetime | None = None
    closed_at: datetime | None = None
    peak_z: float = 0.0
    peak_net_edge_bps: float = 0.0
    observations: int = 0


@dataclass(frozen=True)
class AlertEvent:
    """Emitted at most once per episode, and only when the money survives."""

    linkage_id: str
    ts: datetime
    z_score: float
    spread_bps: float
    net_edge_bps: float
    friction_bps: float
    leg_prices: dict
    fair_value: object
    reference_price: object


@dataclass
class SignalTracker:
    """One tracker per process; holds an Episode per linkage."""

    episodes: dict[str, Episode] = field(default_factory=dict)

    def episode(self, linkage_id: str) -> Episode:
        return self.episodes.setdefault(linkage_id, Episode(linkage_id=linkage_id))

    def observe(
        self, observation: Observation, linkage: LinkageConfig
    ) -> AlertEvent | None:
        """Advance the state machine. Returns an alert only on the transition."""
        episode = self.episode(observation.linkage_id)

        # A stale or unscoreable observation cannot advance anything. It also
        # must not close an open episode: a feed hiccup is not evidence the gap
        # has relaxed, and treating it as one would reopen -- and re-alert --
        # the same episode the moment data returns.
        if not observation.alertable:
            return None

        z = abs(observation.z_score)
        net_edge = observation.net_edge_bps
        cfg = linkage.alert

        episode.observations += 1
        episode.peak_z = max(episode.peak_z, z)
        episode.peak_net_edge_bps = max(episode.peak_net_edge_bps, net_edge)

        if episode.state is SignalState.DORMANT:
            if z >= cfg.warn_z:
                episode.state = SignalState.WATCHING
                episode.opened_at = observation.ts
                episode.closed_at = None
                episode.peak_z = z
                episode.peak_net_edge_bps = net_edge
            return None

        if episode.state is SignalState.WATCHING:
            if z < cfg.warn_z:
                self._close(episode, observation.ts)
                return None
            if z >= cfg.alert_z and net_edge >= cfg.min_net_edge_bps:
                if self._in_cooldown(episode, observation.ts, cfg.cooldown_minutes):
                    return None
                episode.state = SignalState.ALERT
                episode.alerted_at = observation.ts
                return self._alert(observation, linkage)
            return None

        if episode.state is SignalState.ALERT:
            if z < cfg.alert_z:
                episode.state = SignalState.DECAYING
            return None

        # DECAYING
        if z < cfg.warn_z:
            self._close(episode, observation.ts)
        elif z >= cfg.alert_z and net_edge >= cfg.min_net_edge_bps:
            # The same episode stretching again. Re-alert only once the cooldown
            # has elapsed, so a spread oscillating around the threshold does not
            # machine-gun the notification channel.
            if not self._in_cooldown(episode, observation.ts, cfg.cooldown_minutes):
                episode.state = SignalState.ALERT
                episode.alerted_at = observation.ts
                return self._alert(observation, linkage)
            episode.state = SignalState.ALERT
        return None

    # -- internals -------------------------------------------------------

    @staticmethod
    def _in_cooldown(episode: Episode, now: datetime, minutes: int) -> bool:
        if episode.alerted_at is None:
            return False
        return now - episode.alerted_at < timedelta(minutes=minutes)

    @staticmethod
    def _close(episode: Episode, now: datetime) -> None:
        episode.state = SignalState.DORMANT
        episode.closed_at = now
        episode.opened_at = None
        episode.peak_z = 0.0
        episode.peak_net_edge_bps = 0.0
        episode.observations = 0

    @staticmethod
    def _alert(observation: Observation, linkage: LinkageConfig) -> AlertEvent:
        return AlertEvent(
            linkage_id=observation.linkage_id,
            ts=observation.ts,
            z_score=observation.z_score,
            spread_bps=observation.spread_bps,
            net_edge_bps=observation.net_edge_bps,
            friction_bps=linkage.total_friction_bps,
            leg_prices=observation.leg_prices,
            fair_value=observation.fair_value,
            reference_price=observation.reference_price,
        )
