"""Episode tracking: one notification per divergence, not one per poll."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from linkage.engine import Observation
from linkage.signals import SignalState, SignalTracker
from tests.test_engine import linkage

NOW = datetime(2026, 9, 12, 9, 30, tzinfo=timezone.utc)


def obs(z: float, *, net_edge: float = 100.0, minute: int = 0, stale: bool = False):
    return Observation(
        linkage_id="adr",
        ts=NOW + timedelta(minutes=minute),
        leg_prices={"local": Decimal("1550")},
        fair_value=Decimal("1548"),
        reference_price=Decimal("1550"),
        spread=Decimal("2"),
        spread_bps=13.0,
        z_score=None if stale else z,
        net_edge_bps=None if stale else net_edge,
        stale=stale,
        stale_reason="feed hiccup" if stale else None,
    )


def test_quiet_spread_stays_dormant():
    tracker = SignalTracker()
    assert tracker.observe(obs(0.4), linkage()) is None
    assert tracker.episode("adr").state is SignalState.DORMANT


def test_crossing_warn_opens_an_episode_without_alerting():
    tracker = SignalTracker()
    assert tracker.observe(obs(2.0), linkage()) is None
    assert tracker.episode("adr").state is SignalState.WATCHING


def test_one_alert_per_episode_not_one_per_poll():
    """The reason this layer exists.

    Without it a gap that persists for two hours produces 120 notifications for
    one occurrence, which trains you to ignore the channel. Muted alerts are
    worse than no alerts, because you still believe you are being watched.
    """
    tracker = SignalTracker()
    cfg = linkage()

    tracker.observe(obs(2.0, minute=0), cfg)  # WATCHING
    first = tracker.observe(obs(3.1, minute=1), cfg)  # ALERT
    assert first is not None
    assert first.z_score == 3.1

    for minute in range(2, 40):
        assert tracker.observe(obs(3.4, minute=minute), cfg) is None


def test_high_z_without_net_edge_never_alerts():
    """A four-sigma gap smaller than its own trading cost is not an opportunity.

    This is the friction ledger doing its job, and it is expected to suppress
    most of what the z-score finds.
    """
    tracker = SignalTracker()
    cfg = linkage()

    tracker.observe(obs(2.0, net_edge=-5.0, minute=0), cfg)
    for minute in range(1, 10):
        assert tracker.observe(obs(4.0, net_edge=-5.0, minute=minute), cfg) is None
    assert tracker.episode("adr").state is SignalState.WATCHING


def test_a_stale_observation_does_not_close_an_open_episode():
    """A feed hiccup is not evidence the gap relaxed.

    If staleness closed the episode, the tracker would reopen and re-alert the
    same divergence the moment data returned -- turning a flaky connection into
    an alert generator.
    """
    tracker = SignalTracker()
    cfg = linkage()

    tracker.observe(obs(2.0, minute=0), cfg)
    assert tracker.observe(obs(3.1, minute=1), cfg) is not None
    state_before = tracker.episode("adr").state

    for minute in range(2, 8):
        assert tracker.observe(obs(0.0, minute=minute, stale=True), cfg) is None

    assert tracker.episode("adr").state is state_before


def test_relaxing_closes_the_episode_and_a_new_stretch_alerts_again():
    tracker = SignalTracker()
    cfg = linkage()

    tracker.observe(obs(2.0, minute=0), cfg)
    assert tracker.observe(obs(3.1, minute=1), cfg) is not None

    tracker.observe(obs(2.0, minute=2), cfg)  # ALERT -> DECAYING
    tracker.observe(obs(0.3, minute=3), cfg)  # DECAYING -> DORMANT
    assert tracker.episode("adr").state is SignalState.DORMANT

    # A genuinely new divergence, well past the cooldown.
    tracker.observe(obs(2.0, minute=200), cfg)
    assert tracker.observe(obs(3.5, minute=201), cfg) is not None


def test_cooldown_suppresses_re_alerting_within_one_episode():
    """A spread oscillating around the threshold must not machine-gun the channel."""
    tracker = SignalTracker()
    cfg = linkage()  # cooldown_minutes = 60

    tracker.observe(obs(2.0, minute=0), cfg)
    assert tracker.observe(obs(3.1, minute=1), cfg) is not None

    tracker.observe(obs(2.0, minute=2), cfg)  # decaying
    assert tracker.observe(obs(3.6, minute=3), cfg) is None  # inside cooldown

    tracker.observe(obs(2.0, minute=70), cfg)
    assert tracker.observe(obs(3.6, minute=71), cfg) is not None  # cooldown elapsed


def test_alert_carries_the_friction_breakdown():
    """The number that makes the alert honest travels with it."""
    tracker = SignalTracker()
    cfg = linkage()

    tracker.observe(obs(2.0, minute=0), cfg)
    alert = tracker.observe(obs(3.1, net_edge=42.0, minute=1), cfg)

    assert alert.friction_bps == 30  # fx_spread 25 + brokerage 5
    assert alert.net_edge_bps == 42.0
