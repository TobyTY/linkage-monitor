"""State that survives a restart -- and refuses to, when it should not.

The test that matters here is `test_a_restart_is_invisible_to_the_verdict`. It
does not compare snapshots field by field, because a snapshot that round-trips
perfectly can still be missing something the detector needs; it runs the same
series through two detectors, one of which is saved and reloaded halfway, and
demands the same verdict out of both. Anything left out of `snapshot()` shows up
there as a divergence, which is exactly what forgetting it would cost live.

The rest of the file is about the failure this feature introduces: resuming
state that no longer means what it meant when it was written.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from sqlalchemy import create_engine, select

from linkage.detector import STATE_VERSION, WARMUP_OBSERVATIONS, LinkageDetector
from linkage.store import StateStore, alerts, detector_state, observations
from tests.test_detector_pipeline import obs
from tests.test_engine import linkage


@pytest.fixture
def store() -> StateStore:
    """A real database, in memory. Sqlite because the schema is portable and a
    test that needs a network round-trip to Neon is a test nobody runs."""
    store = StateStore(create_engine("sqlite://", future=True))
    store.create_schema()
    return store


def series(n: int, seed: int = 7) -> list[float]:
    rng = np.random.default_rng(seed)
    return [float(v) for v in rng.normal(0, 12, n)]


# ---------------------------------------------------------------------------
# The one that proves it works
# ---------------------------------------------------------------------------


def test_a_restart_is_invisible_to_the_verdict(store):
    cfg = linkage()
    values = series(WARMUP_OBSERVATIONS + 400)
    cut = len(values) // 2

    uninterrupted = LinkageDetector("adr")
    for i, v in enumerate(values):
        uninterrupted.observe(obs(v, day=i), cfg)

    restarted = LinkageDetector("adr")
    for i, v in enumerate(values[:cut]):
        restarted.observe(obs(v, day=i), cfg)

    store.save(cfg, restarted)
    loaded = store.load(cfg)
    assert loaded.restored, loaded.reason
    restarted = loaded.detector

    for i, v in enumerate(values[cut:], start=cut):
        restarted.observe(obs(v, day=i), cfg)

    # A deviation large enough to be interesting, put through both.
    probe = obs(90.0, day=len(values))
    a = uninterrupted.observe(probe, cfg)
    b = restarted.observe(probe, cfg)

    assert a.should_alert == b.should_alert
    assert a.reason == b.reason
    assert a.z == pytest.approx(b.z)
    assert a.threshold.percentile == pytest.approx(b.threshold.percentile)
    assert a.kalman.beta == pytest.approx(b.kalman.beta)
    assert uninterrupted.seen == restarted.seen


def test_the_filters_own_uncertainty_survives_too(store):
    """P is the half of the Kalman state that is easy to forget.

    Reloading `state` but not `P` gives a filter that knows the right beta and
    has forgotten how sure it is of it -- so S_t is wrong, every z is wrong by a
    constant factor, and nothing about the output looks broken.
    """
    cfg = linkage()
    det = LinkageDetector("adr")
    for i, v in enumerate(series(300)):
        det.observe(obs(v, day=i), cfg)

    store.save(cfg, det)
    back = store.load(cfg).detector

    assert np.allclose(back.kalman.P, det.kalman.P)
    assert np.allclose(back.kalman.state, det.kalman.state)
    assert back.kalman.steps == det.kalman.steps


# ---------------------------------------------------------------------------
# Refusing to resume
# ---------------------------------------------------------------------------


def test_a_changed_formula_discards_the_state(store):
    """The failure this module exists to prevent.

    State accumulated under one fair-value expression describes a different
    quantity under another. Resuming across the edit would leave a detector
    that is confident, wrong, and indistinguishable from a working one.
    """
    cfg = linkage()
    det = LinkageDetector("adr")
    for i, v in enumerate(series(200)):
        det.observe(obs(v, day=i), cfg)
    store.save(cfg, det)

    edited = linkage(fair_value="adr * fx * 1.02")
    result = store.load(edited)

    assert not result.restored
    assert "config changed" in result.reason


def test_a_changed_symbol_discards_the_state(store):
    cfg = linkage()
    store.save(cfg, LinkageDetector("adr"))

    moved = linkage(
        legs={
            "local": {"symbol": "INFY.BO", "provider": "fake"},  # BSE, not NSE
            "adr": {"symbol": "INFY", "provider": "fake"},
            "fx": {"symbol": "USDINR=X", "provider": "fake"},
        }
    )
    assert not store.load(moved).restored


def test_retuning_friction_keeps_the_state(store):
    """The other half of the fingerprint decision, and the more useful half.

    Friction and alert thresholds are applied fresh to every verdict; they
    accumulate in nothing. If changing a brokerage number threw away the
    percentile window, nobody would ever correct one.
    """
    cfg = linkage()
    det = LinkageDetector("adr")
    for i, v in enumerate(series(200)):
        det.observe(obs(v, day=i), cfg)
    store.save(cfg, det)

    cheaper = linkage(
        friction_bps={"fx_spread": 18, "brokerage": 3},
        alert={
            "warn_z": 2.0,
            "alert_z": 3.0,
            "min_net_edge_bps": 5,
            "cooldown_minutes": 30,
        },
    )
    result = store.load(cheaper)

    assert result.restored
    assert result.detector.seen == 200


def test_a_snapshot_from_another_build_is_refused(store):
    cfg = linkage()
    store.save(cfg, LinkageDetector("adr"))

    with store.engine.begin() as conn:
        row = conn.execute(select(detector_state)).one()
        stale = dict(row.snapshot)
        stale["version"] = STATE_VERSION + 1
        conn.execute(detector_state.update().values(snapshot=stale))

    result = store.load(cfg)
    assert not result.restored
    assert "version" in result.reason


def test_an_unreadable_snapshot_does_not_crash_the_scan(store):
    """Corrupt state should cost a warmup, not the process."""
    cfg = linkage()
    store.save(cfg, LinkageDetector("adr"))
    with store.engine.begin() as conn:
        conn.execute(
            detector_state.update().values(snapshot={"version": STATE_VERSION})
        )

    result = store.load(cfg)
    assert not result.restored
    assert "unreadable" in result.reason


def test_no_stored_state_is_not_an_error(store):
    result = store.load(linkage())
    assert not result.restored
    assert result.reason == "no stored state"


# ---------------------------------------------------------------------------
# The append-only record
# ---------------------------------------------------------------------------


def test_saving_twice_updates_one_row(store):
    cfg = linkage()
    det = LinkageDetector("adr")
    for i in range(5):
        det.observe(obs(float(i), day=i), cfg)
        store.save(cfg, det)

    with store.engine.connect() as conn:
        rows = conn.execute(select(detector_state)).all()
    assert len(rows) == 1
    assert rows[0].snapshot["seen"] == 5


def test_last_alert_survives_so_the_cooldown_does(store):
    """Otherwise a restart re-fires every alert that was already sent."""
    cfg = linkage()
    when = datetime(2026, 9, 12, 9, 30, tzinfo=timezone.utc)
    store.save(cfg, LinkageDetector("adr"), last_alert=when)

    assert store.load(cfg).last_alert == when


def test_an_alert_records_what_it_predicted(store):
    """So it can be held against what happened, by someone who was not there."""
    import numpy as np

    cfg = linkage()
    det = LinkageDetector("adr")

    # A strongly mean-reverting series, so the horizon gate can pass.
    rng = np.random.default_rng(5)
    level = 0.0
    for i in range(WARMUP_OBSERVATIONS + 400):
        level = 0.5 * level + float(rng.normal(0, 20))
        det.observe(obs(level, day=i), cfg)

    verdict = det.observe(obs(400.0, day=900), cfg)
    assert verdict.should_alert, verdict.reason

    store.record_alert(cfg, verdict)

    with store.engine.connect() as conn:
        row = conn.execute(select(alerts)).one()

    assert row.linkage_id == "adr"
    assert row.spread_bps == pytest.approx(400.0)
    assert row.friction_bps == pytest.approx(cfg.total_friction_bps)
    assert row.predicted_reversion_bps > 0
    assert row.half_life_days is not None
    assert row.fingerprint == cfg.state_fingerprint


def test_stale_readings_never_reach_the_observation_log(store):
    """The same rule the detector applies, applied to the record.

    A logged price that was never real is worse than a gap, because anything
    that later fits a model to this table cannot tell the difference.
    """
    cfg = linkage()
    good = obs(12.0, day=1)
    bad = obs(9_999.0, day=2, stale=True)

    store.record_observations([(cfg, good), (cfg, bad)])

    with store.engine.connect() as conn:
        rows = conn.execute(select(observations)).all()

    assert len(rows) == 1
    assert rows[0].spread_bps == pytest.approx(12.0)


def test_a_cycle_of_observations_is_one_insert(store):
    cfg = linkage()
    batch = [(cfg, obs(float(i), day=i)) for i in range(30)]
    store.record_observations(batch)
    with store.engine.connect() as conn:
        assert len(conn.execute(select(observations)).all()) == 30


def test_recording_nothing_is_allowed(store):
    """A cycle where every leg was stale must not raise."""
    store.record_observations([])
    store.record_observations([(linkage(), obs(1.0, stale=True))])
    assert store.alert_count() == 0


def test_timestamps_come_back_as_utc(store):
    """Sqlite drops the tzinfo; comparing a naive datetime to an aware one
    raises, and it raises inside the cooldown check, at alert time."""
    cfg = linkage()
    when = datetime.now(timezone.utc) - timedelta(hours=2)
    store.save(cfg, LinkageDetector("adr"), last_alert=when)

    last = store.load(cfg).last_alert
    assert last.tzinfo is not None
    assert datetime.now(timezone.utc) - last > timedelta(hours=1)


# ---------------------------------------------------------------------------
# Readiness, not the existence of a row
# ---------------------------------------------------------------------------


def test_a_detector_that_learned_nothing_does_not_count_as_warm(store):
    """The regression for a bug this feature caused on its first live run.

    The market was closed, so every quote was stale, so every detector learned
    nothing -- and a row was written anyway. The next run read "a row exists"
    as "already warm", skipped the history replay, and printed a line saying
    everything had resumed. The scanner would have suppressed its own warmup
    forever while looking entirely healthy.
    """
    from linkage.config import Universe
    from linkage.scan import resume

    cfg = linkage()
    universe = Universe(linkages=[cfg])

    barely = LinkageDetector("adr")
    for i in range(5):
        barely.observe(obs(float(i), day=i), cfg)
    store.save(cfg, barely)

    detectors, last_alert = {}, {}
    ready = resume(universe, store, detectors, last_alert)

    assert ready == set()                    # not warm: must still be replayed
    assert detectors["adr"].seen == 5        # but not thrown away either


def test_a_detector_past_warmup_is_not_replayed_again(store):
    from linkage.config import Universe
    from linkage.scan import resume

    cfg = linkage()
    warm = LinkageDetector("adr")
    for i, v in enumerate(series(WARMUP_OBSERVATIONS + 50)):
        warm.observe(obs(v, day=i), cfg)
    store.save(cfg, warm)

    ready = resume(Universe(linkages=[cfg]), store, {}, {})
    assert ready == {"adr"}
