"""The dashboard, and the one piece of real logic in it.

Rendering is mostly string work and is tested only for "does not crash on an
empty database", which is the state it will most often be opened in. The part
worth real tests is `outcomes`: joining each alert to what the spread did a
horizon later is how the system is scored against itself, and getting it subtly
wrong would flatter every number on the page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine

from linkage.config import Universe
from linkage.dashboard import build_page, outcomes
from linkage.detector import LinkageDetector
from linkage.store import StateStore, alerts, observations
from tests.test_engine import linkage

START = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def store() -> StateStore:
    store = StateStore(create_engine("sqlite://", future=True))
    store.create_schema()
    return store


def add_alert(store, *, when, spread_bps, predicted=50.0, friction=26.95):
    with store.engine.begin() as conn:
        conn.execute(
            alerts.insert().values(
                linkage_id="adr",
                ts=when,
                fingerprint="f",
                category="tradeable",
                spread_bps=spread_bps,
                friction_bps=friction,
                predicted_reversion_bps=predicted,
            )
        )


def add_observation(store, *, when, spread_bps):
    with store.engine.begin() as conn:
        conn.execute(
            observations.insert().values(
                linkage_id="adr",
                ts=when,
                fingerprint="f",
                reference_price=100.0,
                fair_value=100.0,
                spread_bps=spread_bps,
            )
        )


def test_the_move_is_measured_on_absolute_spread(store):
    """A spread going from -340 to -270 has narrowed by 70, not moved by +70.

    Signed arithmetic here would score a spread that got WIDER in the negative
    direction as a win, on exactly the alerts this system fires most.
    """
    add_alert(store, when=START, spread_bps=-340.0)
    add_observation(store, when=START + timedelta(days=3), spread_bps=-270.0)

    (result,) = outcomes(store, horizon_days=3)
    assert result.resolved
    assert result.actual_move_bps == pytest.approx(70.0)
    assert result.net_bps == pytest.approx(70.0 - 26.95)


def test_a_spread_that_widened_is_scored_as_a_loss(store):
    add_alert(store, when=START, spread_bps=-340.0)
    add_observation(store, when=START + timedelta(days=3), spread_bps=-410.0)

    (result,) = outcomes(store, horizon_days=3)
    assert result.actual_move_bps == pytest.approx(-70.0)
    assert result.net_bps < 0


def test_an_open_horizon_is_reported_not_dropped(store):
    """Dropping unresolved alerts is how a hit rate ends up describing only the
    trades that happened to finish early."""
    add_alert(store, when=START, spread_bps=-340.0)
    add_observation(store, when=START + timedelta(hours=6), spread_bps=-300.0)

    (result,) = outcomes(store, horizon_days=3)
    assert not result.resolved
    assert result.actual_move_bps is None
    assert result.net_bps is None


def test_the_first_observation_at_or_after_the_horizon_is_used(store):
    """Markets close. The observation exactly three days later usually does not
    exist, and the next one that does is the honest exit."""
    add_alert(store, when=START, spread_bps=-340.0)
    add_observation(store, when=START + timedelta(days=2), spread_bps=-100.0)
    add_observation(store, when=START + timedelta(days=4), spread_bps=-300.0)
    add_observation(store, when=START + timedelta(days=5), spread_bps=-50.0)

    (result,) = outcomes(store, horizon_days=3)
    # The +240 shrink at day 2 is inside the horizon and must not be claimed;
    # the +40 at day 4 is the first reading a holder could actually have exited on.
    assert result.actual_move_bps == pytest.approx(40.0)


def test_observations_from_another_linkage_are_not_borrowed(store):
    add_alert(store, when=START, spread_bps=-340.0)
    with store.engine.begin() as conn:
        conn.execute(
            observations.insert().values(
                linkage_id="something_else",
                ts=START + timedelta(days=3),
                fingerprint="f",
                reference_price=1.0,
                fair_value=1.0,
                spread_bps=0.0,
            )
        )
    (result,) = outcomes(store, horizon_days=3)
    assert not result.resolved


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_an_empty_database_renders(store):
    """The state the page will most often be opened in."""
    page = build_page(store, Universe(linkages=[linkage()]), horizon_days=3)
    assert "<!doctype html>" in page
    assert "No alerts recorded" in page
    assert "No detector has stored state" in page


def test_a_populated_database_renders(store):
    cfg = linkage()
    detector = LinkageDetector(cfg.id)
    from tests.test_detector_pipeline import obs

    for i in range(30):
        detector.observe(obs(float(i % 7) - 3.0, day=i), cfg)
    store.save(cfg, detector)

    add_alert(store, when=START, spread_bps=-340.0)
    add_observation(store, when=START + timedelta(days=3), spread_bps=-270.0)

    page = build_page(store, Universe(linkages=[cfg]), horizon_days=3)
    assert "adr" in page
    assert "+70.0" in page          # the measured move
    assert "alerts have run their full horizon" in page  # the scorecard bolds the count
    assert ">1</b> alerts" in page


def test_a_changed_config_is_surfaced_on_the_page(store):
    """Otherwise the detector silently resets and the page looks the same."""
    cfg = linkage()
    store.save(cfg, LinkageDetector(cfg.id))
    edited = linkage(fair_value="adr * fx * 1.01")

    page = build_page(store, Universe(linkages=[edited]), horizon_days=3)
    assert "changed since save" in page


def test_nothing_user_supplied_reaches_the_page_unescaped(store):
    """Linkage ids and descriptions come from a YAML file, which is exactly the
    kind of input nobody thinks of as input."""
    cfg = linkage(description="<script>alert(1)</script>")
    store.save(cfg, LinkageDetector(cfg.id))
    page = build_page(store, Universe(linkages=[cfg]), horizon_days=3)
    assert "<script>alert(1)</script>" not in page
