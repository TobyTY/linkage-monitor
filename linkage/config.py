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


class LinkageConfig(BaseModel):
    id: str
    description: str
    legs: dict[str, LegConfig]
    fair_value: str
    params: dict[str, float] = Field(default_factory=dict)
    reference: str
    friction_bps: dict[str, float] = Field(default_factory=dict)
    alert: AlertConfig

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


class Universe(BaseModel):
    linkages: list[LinkageConfig]

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
