"""Delivery, and the rule that it must never take the scanner down with it.

No network is touched. `urllib.request.urlopen` is replaced, which is the only
honest way to test the failure paths -- a test that needs Telegram to be down in
order to check what happens when Telegram is down is a test that never runs.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timezone
from io import BytesIO

import pytest

from linkage.config import Category
from linkage.detector import Verdict
from linkage.kalman import KalmanStep
from linkage.notify import (
    MAX_MESSAGE_CHARS,
    ConsoleNotifier,
    DiscordNotifier,
    MultiNotifier,
    NtfyNotifier,
    TelegramNotifier,
    build,
    render,
)
from linkage.ou import GateResult, OUFit
from linkage.thresholds import ThresholdReading
from tests.test_engine import linkage

NOW = datetime(2026, 9, 12, 9, 30, tzinfo=timezone.utc)


def verdict(**overrides) -> Verdict:
    base = dict(
        linkage_id="adr",
        ts=NOW,
        should_alert=True,
        reason="fires",
        spread_bps=-341.2,
        kalman=KalmanStep(
            beta=1.0004,
            intercept=0.0,
            beta_var=0.01,
            prediction=100.0,
            innovation=-3.4,
            innovation_var=1.0,
            z=-3.41,
        ),
        threshold=ThresholdReading(
            value=-341.2,
            percentile=0.6,
            exceeds_warn=True,
            exceeds_alert=True,
            samples=740,
        ),
        gate=GateResult(True, "passes", 63.7, 32.7),
        ou=OUFit(
            theta=0.29,
            mu=-300.0,
            sigma=20.0,
            half_life=2.38,
            observations=250,
            r_squared=0.31,
            theta_tstat=-14.5,
        ),
    )
    base.update(overrides)
    return Verdict(**base)


class FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ---------------------------------------------------------------------------
# What the message says
# ---------------------------------------------------------------------------


def test_the_message_carries_the_whole_arithmetic():
    """The recipient is on a phone and cannot open a terminal to check."""
    text = render(linkage(), verdict())

    for expected in ("-341.2 bps", "-3.41", "0.60", "2.38d", "t=-14.5", "+63.7", "30.0"):
        assert expected in text, f"{expected!r} missing from:\n{text}"
    assert "NET" in text


def test_an_observational_alert_says_it_is_not_a_profit_estimate():
    """The single most likely way this tool could mislead someone."""
    text = render(linkage(category=Category.OBSERVATIONAL), verdict())
    assert "not a profit estimate" in text.lower()


def test_a_validation_alert_says_the_bug_is_ours():
    text = render(linkage(category=Category.VALIDATION), verdict())
    assert "bug" in text.lower()


def test_beta_drift_is_flagged_in_the_message():
    """A stale conversion constant looks exactly like a real divergence."""
    drifted = verdict(
        kalman=KalmanStep(1.03, 0.0, 0.01, 100.0, -3.4, 1.0, -3.41)
    )
    assert "drifted" in render(linkage(), drifted)


def test_a_quiet_beta_is_not_flagged():
    assert "drifted" not in render(linkage(), verdict())


def test_a_partial_verdict_still_renders():
    """Not every alert path fills in every field, and a crash in the renderer
    would lose an alert that the detector got right."""
    text = render(linkage(), verdict(gate=None, ou=None, threshold=None))
    assert "adr" in text
    assert "-341.2 bps" in text


def test_the_message_is_cut_to_what_telegram_accepts():
    long_description = "x" * 6000
    text = render(linkage(description=long_description), verdict())
    assert len(text) <= MAX_MESSAGE_CHARS


# ---------------------------------------------------------------------------
# Delivery never takes the scanner down
# ---------------------------------------------------------------------------


def test_a_successful_send_is_counted(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["body"] = request.data.decode()
        return FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = TelegramNotifier(token="T", chat_id="42")

    assert notifier.send("hello")
    assert notifier.sent == 1
    assert notifier.failed == 0
    assert "chat_id=42" in sent["body"]


@pytest.mark.parametrize(
    "boom",
    [
        urllib.error.URLError("dns is down"),
        urllib.error.HTTPError("u", 500, "server error", {}, BytesIO(b"")),
        TimeoutError("took too long"),
        ValueError("proxy returned html, not json"),
    ],
)
def test_no_transport_failure_escapes(monkeypatch, boom):
    """The rule this module exists to keep.

    Every one of these is a real thing that happens on a home connection, and
    not one of them is a reason to stop monitoring markets.
    """

    def fake_urlopen(request, timeout=None):
        raise boom

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = TelegramNotifier(token="T", chat_id="42")

    assert notifier.send("hello") is False
    assert notifier.failed == 1
    assert notifier.last_error


def test_a_rejection_from_telegram_is_a_failure_not_a_crash(monkeypatch):
    """HTTP 200 with ok:false -- a revoked token, or a chat that blocked the
    bot. Looks like success at the transport layer and is not."""

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout=None: FakeResponse(
            {"ok": False, "description": "chat not found"}
        ),
    )
    notifier = TelegramNotifier(token="T", chat_id="wrong")

    assert notifier.send("hello") is False
    assert "chat not found" in notifier.last_error


def test_one_dead_target_does_not_silence_the_others():
    class Dead:
        def send(self, text):
            return False

    console = ConsoleNotifier()
    assert MultiNotifier([Dead(), console]).send("x") is True
    assert MultiNotifier([Dead(), Dead()]).send("x") is False


def test_every_target_is_tried_even_after_one_fails():
    """`any()` short-circuits. If the first target succeeds and the second is
    never called, an alert silently stops reaching Telegram the day the console
    is listed first -- which it always is."""
    calls = []

    class Recorder:
        def __init__(self, name, result):
            self.name, self.result = name, result

        def send(self, text):
            calls.append(self.name)
            return self.result

    MultiNotifier([Recorder("a", True), Recorder("b", True)]).send("x")
    assert calls == ["a", "b"]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_telegram_is_absent_rather_than_broken_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert TelegramNotifier.from_env() is None


def test_half_configured_is_treated_as_unconfigured(monkeypatch):
    """A token with no chat id cannot deliver. Better to say nothing is
    configured than to fail once per alert forever."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert TelegramNotifier.from_env() is None


def test_build_always_yields_something_that_works(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert build().send("still delivered to the console") is True


def test_verify_reports_a_bad_token_without_raising(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda url, timeout=None: FakeResponse(
            {"ok": False, "description": "Unauthorized"}
        ),
    )
    assert "Unauthorized" in TelegramNotifier(token="bad", chat_id="1").verify()


def test_verify_reports_an_unreachable_api_without_raising(monkeypatch):
    def boom(url, timeout=None):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert "unreachable" in TelegramNotifier(token="T", chat_id="1").verify()


# ---------------------------------------------------------------------------
# ntfy and Discord: the channels that exist so Telegram is not a dependency.


def test_ntfy_posts_the_body_to_the_topic_url(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["body"] = request.data.decode()
        return FakeResponse({})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = NtfyNotifier(topic="abc123")

    assert notifier.send("GOLDBEES z=2.4")
    assert sent["url"] == "https://ntfy.sh/abc123"
    assert sent["body"] == "GOLDBEES z=2.4"
    assert notifier.sent == 1


def test_ntfy_honours_a_self_hosted_server(monkeypatch):
    """The public server makes the topic the only secret, and a guessable one.
    A self-hosted server is the answer for anything that should stay private."""
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.com/")
    notifier = NtfyNotifier.from_env()
    assert notifier.server == "https://ntfy.example.com"  # trailing slash dropped


@pytest.mark.parametrize(
    "boom",
    [
        urllib.error.URLError("dns is down"),
        urllib.error.HTTPError("u", 503, "unavailable", {}, BytesIO(b"")),
        TimeoutError("took too long"),
    ],
)
def test_ntfy_transport_failures_do_not_escape(monkeypatch, boom):
    def fake_urlopen(request, timeout=None):
        raise boom

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = NtfyNotifier(topic="t")

    assert notifier.send("anything") is False
    assert notifier.failed == 1
    assert notifier.last_error


def test_discord_sends_json_content(monkeypatch):
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["body"] = json.loads(request.data.decode())
        return FakeResponse({})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/1/x")

    assert notifier.send("hello")
    assert sent["body"] == {"content": "hello"}


def test_discord_truncates_to_its_own_shorter_limit(monkeypatch):
    """Discord rejects anything past 2000 characters, Telegram allows 4096.
    Truncating once in the renderer would cut every Telegram alert down to
    Discord's limit for no reason, so each channel trims its own."""
    sent = {}

    def fake_urlopen(request, timeout=None):
        sent["body"] = json.loads(request.data.decode())
        return FakeResponse({})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/1/x")

    notifier.send("x" * 5000)
    assert len(sent["body"]["content"]) == notifier.limit
    assert sent["body"]["content"].endswith("...")
    assert notifier.limit < MAX_MESSAGE_CHARS


@pytest.mark.parametrize(
    "variable,value,expected",
    [
        ("NTFY_TOPIC", "some-topic", NtfyNotifier),
        ("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x", DiscordNotifier),
    ],
)
def test_build_picks_up_each_channel_from_the_environment(
    monkeypatch, variable, value, expected
):
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NTFY_TOPIC", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(variable, value)

    targets = build().targets
    assert any(isinstance(t, expected) for t in targets)


def test_several_channels_can_run_at_once(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/x")

    kinds = {type(t).__name__ for t in build().targets}
    assert {"ConsoleNotifier", "TelegramNotifier", "NtfyNotifier", "DiscordNotifier"} <= kinds


def test_no_channel_configured_still_leaves_the_console(monkeypatch):
    """Configuring nothing is the normal case, not an error. A monitor that
    refuses to start without a messaging service has made delivery a dependency
    of detection."""
    for name in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NTFY_TOPIC", "DISCORD_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)

    targets = build().targets
    assert len(targets) == 1
    assert isinstance(targets[0], ConsoleNotifier)
