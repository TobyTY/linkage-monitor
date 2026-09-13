"""Getting an alert off the machine that produced it.

A monitor whose output only exists in a terminal is a monitor you have to watch,
which defeats the point of building one. This sends alerts to Telegram.

TWO RULES SHAPE EVERYTHING HERE.

DELIVERY MUST NEVER BREAK DETECTION. A network timeout, a revoked token, a
Telegram outage, a chat id typed wrong -- none of these are reasons for the
scanner to stop scanning or to lose a cycle's state. Every send is wrapped, every
failure is logged and counted, and the scan carries on. The failure mode this
avoids is the one where a monitor dies overnight because the messaging service it
depends on had a bad hour.

AN ALERT MUST CARRY ITS OWN ARITHMETIC. The message is not "GOLDBEES diverged".
It is the z, the percentile, the half-life and its t-statistic, the expected
reversion, the friction subtracted from it, and what is left -- because the
recipient is on a phone, will not be opening a terminal, and the only way that
number can be judged is if the workings arrive with it. The category line is
there for the same reason: on an observational linkage the net edge is a
statement about whether the relationship is holding, and a message that does not
say so is a message that will eventually be read as a profit estimate.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from linkage.config import Category, LinkageConfig
from linkage.detector import Verdict

logger = logging.getLogger("linkage.notify")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 10.0

#: Telegram rejects anything past 4096 characters outright.
MAX_MESSAGE_CHARS = 4000

CATEGORY_NOTE = {
    Category.VALIDATION: (
        "VALIDATION linkage — this is a mathematical identity. A persistent gap "
        "here means the engine has a bug, not that there is money on the table."
    ),
    Category.OBSERVATIONAL: (
        "OBSERVATIONAL — at least one leg is not reachable from an Indian retail "
        "account. Net edge says whether the linkage is HOLDING. It is not a "
        "profit estimate."
    ),
    Category.TRADEABLE: (
        "TRADEABLE — both legs reachable. Net edge means what it says, at the "
        "reference trade size the friction was computed for."
    ),
}


@runtime_checkable
class Notifier(Protocol):
    """Anywhere an alert can be sent."""

    def send(self, text: str) -> bool:
        """Deliver. Returns whether it arrived; never raises."""
        ...


def render(linkage: LinkageConfig, verdict: Verdict) -> str:
    """The alert as it arrives on a phone.

    Every number the decision rested on, in the order the decision used them.
    """
    gate, ou, kalman, threshold = (
        verdict.gate,
        verdict.ou,
        verdict.kalman,
        verdict.threshold,
    )

    lines = [
        f"⚠️ {linkage.id}",
        f"{linkage.description}",
        "",
        f"spread      {verdict.spread_bps:+.1f} bps",
    ]

    if kalman is not None:
        lines.append(f"kalman z    {kalman.z:+.2f}   (beta {kalman.beta:.4f})")
    if threshold is not None:
        lines.append(
            f"percentile  {threshold.percentile:.2f}  "
            f"of {threshold.samples} observations"
        )
    if ou is not None and ou.half_life is not None:
        lines.append(
            f"half-life   {ou.half_life:.2f}d  (t={ou.theta_tstat:+.1f})"
        )
    if gate is not None:
        lines += [
            "",
            f"reverts     {gate.expected_reversion_bps:+.1f} bps in the horizon",
            f"friction    {linkage.total_friction_bps:.1f} bps",
            f"NET         {gate.net_after_friction_bps:+.1f} bps",
        ]

    # Beta drifting away from 1 means the declared relationship is going stale.
    # It is the single most likely reason for a divergence that is not real, so
    # it goes in the message rather than in a log nobody reads.
    drift = verdict.beta_drift
    if drift is not None and drift > 0.01:
        lines += [
            "",
            f"⚑ beta has drifted {drift:.1%} from 1 — the conversion constant "
            f"may be stale rather than the price.",
        ]

    lines += ["", CATEGORY_NOTE[linkage.category]]
    text = "\n".join(lines)
    return text[: MAX_MESSAGE_CHARS - 3] + "..." if len(text) > MAX_MESSAGE_CHARS else text


@dataclass
class ConsoleNotifier:
    """The default. Always available, never fails."""

    def send(self, text: str) -> bool:
        print(text)
        return True


@dataclass
class TelegramNotifier:
    """Sends to one chat. Counts its own failures rather than raising them."""

    token: str
    chat_id: str
    sent: int = 0
    failed: int = 0
    last_error: str | None = field(default=None)

    @classmethod
    def from_env(cls) -> TelegramNotifier | None:
        """Build from TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or return None.

        Absent configuration is the normal case, not an error: the scan runs
        perfectly well printing to a terminal.
        """
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            return None
        return cls(token=token, chat_id=chat_id)

    def send(self, text: str) -> bool:
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode()

        request = urllib.request.Request(
            TELEGRAM_API.format(token=self.token),
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode())
            if not body.get("ok"):
                return self._failure(str(body.get("description", body)))
            self.sent += 1
            return True
        # Deliberately broad. Everything urllib can raise -- DNS failure, TLS
        # error, timeout, a proxy returning HTML -- means the same thing here:
        # the alert did not arrive, and the scanner must keep running anyway.
        except Exception as exc:  # noqa: BLE001
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _failure(self, message: str) -> bool:
        self.failed += 1
        self.last_error = message
        logger.warning("telegram send failed: %s", message)
        return False

    def verify(self) -> str:
        """Check the token and chat id at startup rather than at 09:15.

        A bad token is silent until the first alert, which may be days away and
        is exactly the moment you need it to work. Same reasoning as validating
        the universe at load time.
        """
        try:
            url = f"https://api.telegram.org/bot{self.token}/getMe"
            with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
                body = json.loads(response.read().decode())
        except Exception as exc:  # noqa: BLE001
            return f"unreachable ({type(exc).__name__})"

        if not body.get("ok"):
            return f"rejected: {body.get('description', 'unknown')}"

        name = body.get("result", {}).get("username", "?")
        if self.send("linkage-monitor connected."):
            return f"@{name}, test message delivered"
        return f"@{name} is valid, but sending to chat {self.chat_id} failed: {self.last_error}"


@dataclass
class NtfyNotifier:
    """Push to a phone with no account anywhere.

    ntfy.sh needs no signup, no bot and no token: pick a topic name, subscribe
    to it in the app, and anything POSTed to that topic arrives as a
    notification. The whole configuration is one string.

    THE TOPIC IS THE ONLY SECRET, and on the public server it is a weak one.
    Anyone who guesses the topic can read the alerts, and anyone who knows it
    can post to it. So the topic has to be long and random, and the alerts
    themselves have to stay non-sensitive -- which they are, being prices,
    z-scores and public instrument names. Anything genuinely private belongs on
    a self-hosted server via NTFY_SERVER.
    """

    topic: str
    server: str = "https://ntfy.sh"
    sent: int = 0
    failed: int = 0
    last_error: str | None = field(default=None)

    #: ntfy accepts large bodies. Matching the Telegram cap keeps one alert
    #: reading the same on every channel.
    limit: int = MAX_MESSAGE_CHARS

    @classmethod
    def from_env(cls) -> NtfyNotifier | None:
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic:
            return None
        server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").strip().rstrip("/")
        return cls(topic=topic, server=server)

    def send(self, text: str) -> bool:
        body = text[: self.limit - 3] + "..." if len(text) > self.limit else text
        request = urllib.request.Request(
            f"{self.server}/{self.topic}",
            data=body.encode("utf-8"),
            headers={"Title": "linkage-monitor", "Tags": "chart_with_upwards_trend"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
                pass
            self.sent += 1
            return True
        except Exception as exc:  # noqa: BLE001
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _failure(self, message: str) -> bool:
        self.failed += 1
        self.last_error = message
        logger.warning("ntfy send failed: %s", message)
        return False

    def verify(self) -> str:
        if self.send("linkage-monitor connected."):
            return f"{self.server}/{self.topic}, test message delivered"
        return f"{self.server}/{self.topic} failed: {self.last_error}"


@dataclass
class DiscordNotifier:
    """Post to a channel through an incoming webhook.

    One URL out of a channel's settings, no bot registration and no approval
    step. Worth preferring over Telegram when the alerts should be visible to
    more than one person, since a webhook posts into a channel rather than a
    private chat.

    THE WEBHOOK URL IS A BEARER CREDENTIAL. Anyone holding it can post to that
    channel as this integration, so it belongs in .env with everything else and
    never in a commit.
    """

    webhook_url: str
    sent: int = 0
    failed: int = 0
    last_error: str | None = field(default=None)

    #: Discord rejects anything past 2000 characters. Lower than the Telegram
    #: cap, so truncation happens per channel rather than once in the renderer
    #: -- otherwise every Telegram alert would be cut to Discord's limit for no
    #: reason.
    limit: int = 1900

    @classmethod
    def from_env(cls) -> DiscordNotifier | None:
        url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        return cls(webhook_url=url) if url else None

    def send(self, text: str) -> bool:
        body = text[: self.limit - 3] + "..." if len(text) > self.limit else text
        request = urllib.request.Request(
            self.webhook_url,
            data=json.dumps({"content": body}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
                pass
            self.sent += 1
            return True
        except Exception as exc:  # noqa: BLE001
            return self._failure(f"{type(exc).__name__}: {exc}")

    def _failure(self, message: str) -> bool:
        self.failed += 1
        self.last_error = message
        logger.warning("discord send failed: %s", message)
        return False

    def verify(self) -> str:
        if self.send("linkage-monitor connected."):
            return "webhook accepted, test message delivered"
        return f"webhook failed: {self.last_error}"


@dataclass
class MultiNotifier:
    """Send everywhere, report whether anywhere worked."""

    targets: list[Notifier] = field(default_factory=list)

    def send(self, text: str) -> bool:
        # Every target is called before the result is computed. The list
        # comprehension is deliberate: any() over a generator short-circuits,
        # which would leave the second channel silent whenever the first one
        # worked.
        return any([target.send(text) for target in self.targets])


#: Every off-machine channel, in the order they are tried. Console is handled
#: separately because it is not optional and cannot fail.
REMOTE_CHANNELS = (TelegramNotifier, NtfyNotifier, DiscordNotifier)


def build(*, console: bool = True) -> Notifier:
    """Console always; every configured remote channel as well.

    Configuring none of them is the normal case rather than an error. The scan
    runs perfectly well printing to a terminal, and a monitor that refuses to
    start without a messaging service has made delivery a dependency of
    detection -- which is the first rule at the top of this file.
    """
    targets: list[Notifier] = [ConsoleNotifier()] if console else []
    for channel in REMOTE_CHANNELS:
        built = channel.from_env()
        if built is not None:
            targets.append(built)
    return MultiNotifier(targets)
