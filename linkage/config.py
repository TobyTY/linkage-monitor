"""Universe configuration.

A linkage is declared, not coded. Adding a pair is a config edit; the engine
never learns new names. The validation below exists so that a typo fails when
the file is loaded -- at startup, on a laptop -- rather than at 09:15 when the
market opens and a formula silently resolves to nothing.

The rule that earns its keep is `_check_formula_names`: every name a fair-value
expression references must be a declared leg or a declared param. Without it,
`spot * fx` in a linkage whose legs are `spot` and `usdinr` fails at evaluation
time, once, quietly, for one pair, and the alert simply never fires.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from linkage.formula import FormulaError, referenced_names


class LegConfig(BaseModel):
    symbol: str
    provider: str


class AlertConfig(BaseModel):
    warn_z: float = Field(gt=0)
    alert_z: float = Field(gt=0)
    min_net_edge_bps: float = Field(ge=0)
    cooldown_minutes: int = Field(gt=0)

    @model_validator(mode="after")
    def _alert_above_warn(self) -> AlertConfig:
        if self.alert_z <= self.warn_z:
            raise ValueError(
                f"alert_z ({self.alert_z}) must exceed warn_z ({self.warn_z}); "
                "otherwise the state machine can never sit in WATCHING"
            )
        return self


class Category(str, Enum):
    """What a net-edge number on this linkage actually means.

    Recorded per linkage because the same arithmetic carries three different
    meanings, and conflating them is how a monitoring tool turns into a tool
    that quietly implies every gap is money.
    """

    #: The relationship is a mathematical identity. Exists to prove the engine
    #: works against something whose answer is known in advance.
    VALIDATION = "validation"

    #: The relationship is real and worth watching, but the legs are not both
    #: reachable from an Indian retail account. Net edge measures whether the
    #: linkage is holding -- it is not a profit estimate.
    OBSERVATIONAL = "observational"

    #: Both legs reachable from a demat account. Net edge means what it says.
    TRADEABLE = "tradeable"


class LinkageConfig(BaseModel):
    id: str
    description: str
    category: Category = Category.OBSERVATIONAL
    legs: dict[str, LegConfig]
    fair_value: str
    params: dict[str, float] = Field(default_factory=dict)
    reference: str
    friction_bps: dict[str, float] = Field(default_factory=dict)
    alert: AlertConfig

    #: How fast this relationship's hedge ratio is believed to drift, as the
    #: Kalman's delta. None means the filter's own default.
    #:
    #: This is per-linkage because the honest prior genuinely differs. An ADR
    #: ratio moves on corporate actions and an index tracker's units drift with
    #: rebalancing, so beta there really can wander. A triangular FX identity
    #: cannot: INR/X is USDINR times USD/X by construction, and no amount of
    #: market activity changes that arithmetic. Handing both the same prior
    #: tells the filter it does not know something it does know.
    #:
    #: It matters for the diagnostic, not just for tidiness. The validation
    #: lane exists so an engine bug shows up where the answer is known in
    #: advance, and a permissive prior lets beta wander a few percent on its
    #: own -- which is indistinguishable, to a reader of the dashboard, from
    #: the bug it is supposed to reveal.
    kalman_delta: float | None = None

    @field_validator("legs")
    @classmethod
    def _at_least_two_legs(cls, legs: dict[str, LegConfig]) -> dict[str, LegConfig]:
        if len(legs) < 2:
            raise ValueError("a linkage needs at least two legs to relate")
        return legs

    @model_validator(mode="after")
    def _reference_is_a_leg(self) -> LinkageConfig:
        if self.reference not in self.legs:
            raise ValueError(
                f"reference {self.reference!r} is not one of the legs "
                f"({', '.join(sorted(self.legs))})"
            )
        return self

    @model_validator(mode="after")
    def _check_formula_names(self) -> LinkageConfig:
        try:
            used = referenced_names(self.fair_value)
        except FormulaError as exc:
            raise ValueError(f"fair_value: {exc}") from exc

        available = set(self.legs) | set(self.params)
        unknown = used - available
        if unknown:
            raise ValueError(
                f"fair_value references undeclared name(s) "
                f"{', '.join(sorted(unknown))} -- declared legs and params are "
                f"{', '.join(sorted(available))}"
            )
        return self

    @property
    def total_friction_bps(self) -> float:
        return sum(self.friction_bps.values())

    @property
    def state_fingerprint(self) -> str:
        """Identity of the QUANTITY this linkage measures.

        Persisted detector state is only meaningful against the config that
        produced it. A Kalman state and a percentile window accumulated under
        `spot * usdinr / 10` describe a different number than the same fields
        under `spot * usdinr / 12`, and silently resuming across that edit
        produces a detector that is confidently wrong -- worse than one that
        is honestly ignorant, because it does not look like it is warming up.

        So this covers exactly the fields that change what the stored numbers
        MEAN: the legs, the formula, its parameters, and which leg is the
        reference. Deliberately excluded are friction and the alert thresholds:
        those are applied fresh to every verdict and accumulate in nothing, so
        retuning them must not throw away a month of history.
        """
        canonical = json.dumps(
            {
                "legs": {
                    name: [leg.symbol, leg.provider]
                    for name, leg in sorted(self.legs.items())
                },
                "fair_value": self.fair_value,
                "params": dict(sorted(self.params.items())),
                "reference": self.reference,
                # In the fingerprint because it shapes the state that
                # accumulates, which is the stated test for inclusion --
                # unlike friction and the alert thresholds, which are applied
                # fresh to every verdict and so are deliberately left out.
                "kalman_delta": self.kalman_delta,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class Universe(BaseModel):
    linkages: list[LinkageConfig]

    @field_validator("linkages", mode="before")
    @classmethod
    def _empty_is_allowed(cls, value: Any) -> Any:
        """`linkages:` with nothing under it means no linkages.

        This is not a hypothetical. `stat_pairs --fit` writes exactly that file
        when no pair survives the multiple-testing correction, which is the
        correct output and must not crash the scanner that reads it.
        """
        return [] if value is None else value

    @field_validator("linkages")
    @classmethod
    def _unique_ids(cls, linkages: list[LinkageConfig]) -> list[LinkageConfig]:
        seen: set[str] = set()
        for linkage in linkages:
            if linkage.id in seen:
                raise ValueError(f"duplicate linkage id {linkage.id!r}")
            seen.add(linkage.id)
        return linkages

    def by_id(self, linkage_id: str) -> LinkageConfig:
        for linkage in self.linkages:
            if linkage.id == linkage_id:
                return linkage
        raise KeyError(linkage_id)

    def providers_used(self) -> set[str]:
        return {
            leg.provider for linkage in self.linkages for leg in linkage.legs.values()
        }

    def symbols_for(self, provider: str) -> set[str]:
        """Distinct symbols one provider must supply.

        Distinct matters: USDINR appears in nearly every linkage, and quoting it
        once per cycle rather than once per linkage is most of the difference
        between a scan that fits in the cadence floor and one that does not.
        """
        return {
            leg.symbol
            for linkage in self.linkages
            for leg in linkage.legs.values()
            if leg.provider == provider
        }


def load_universe(path: str | Path) -> Universe:
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return Universe.model_validate(raw)

class Access(str, Enum):
    """What can actually be done with this pair from a Groww account.

    Recorded because it changes what a net-edge number means, and because it is
    the field most likely to be quietly ignored. A cointegrated pair whose short
    leg is unreachable is a pair you can watch, not a pair you can trade.
    """

    #: Both legs tradeable, short side included.
    FULL = "full"

    #: Both legs buyable, but shorting needs F&O or intraday -- so the classic
    #: A - beta*B spread is not available overnight.
    LONG_ONLY = "long_only"

    #: At least one leg is unreachable from an Indian retail account.
    NONE = "none"

    @property
    def category(self) -> Category:
        """How an edge number on this pair should be read."""
        return Category.TRADEABLE if self is Access.FULL else Category.OBSERVATIONAL


class PairSpec(BaseModel):
    """One statistical pair, as written down by a human.

    Deliberately holds no hedge ratio. The relationship between these two
    symbols is not knowable in advance -- it has to be estimated from data and
    then tested -- so a beta living in this file would be a fitted number
    disguised as a declared one, and nobody would know when it went stale.
    Fitting happens in `stat_pairs.py`, which writes its output somewhere
    visible and dated.
    """

    id: str
    group: str
    a: str
    b: str
    access: Access
    mechanism: str
    breaks_when: str

    @model_validator(mode="after")
    def _legs_differ(self) -> PairSpec:
        if self.a == self.b:
            raise ValueError(f"{self.id}: both legs are {self.a}")
        return self


class Catalogue(BaseModel):
    pairs: list[PairSpec]

    @field_validator("pairs")
    @classmethod
    def _unique_ids(cls, pairs: list[PairSpec]) -> list[PairSpec]:
        seen: set[str] = set()
        for pair in pairs:
            if pair.id in seen:
                raise ValueError(f"duplicate pair id {pair.id!r}")
            seen.add(pair.id)
        return pairs

    def symbols(self) -> set[str]:
        return {s for pair in self.pairs for s in (pair.a, pair.b)}

    def by_id(self, pair_id: str) -> PairSpec:
        for pair in self.pairs:
            if pair.id == pair_id:
                return pair
        raise KeyError(pair_id)


def load_catalogue(path: str | Path) -> Catalogue:
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    return Catalogue.model_validate(raw)
