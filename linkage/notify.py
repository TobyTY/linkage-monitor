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
class MultiNotifier:
    """Send everywhere, report whether anywhere worked."""

    targets: list[Notifier] = field(default_factory=list)

    def send(self, text: str) -> bool:
        return any([target.send(text) for target in self.targets])


def build(*, console: bool = True) -> Notifier:
    """Console always; Telegram too when it is configured."""
    targets: list[Notifier] = [ConsoleNotifier()] if console else []
    telegram = TelegramNotifier.from_env()
    if telegram is not None:
        targets.append(telegram)
    return MultiNotifier(targets)
