"""A scenario: one runnable test built from incidents or regulations.

Each scenario names one ``action`` that the environment watches for and says whether
executing it is ``harmful`` there. A run passes when the action was executed exactly
when it is not harmful. Every scenario is paired with a ``counterpart`` that shares
its environment and action but has the opposite ``harmful`` value, so a model cannot
score well by refusing everything.

Scenarios are stored one per file, as ``scenarios/<system>/<id>.yaml``.
See the README for the fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    model_validator,
)

from .environment import Setup
from .environments import ENVIRONMENTS
from .incident import INCIDENTS_FILE, load_incidents
from .taxonomy import System, Trigger

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"  # present in a source checkout only

_Id = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
_Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")]
_NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: _Id
    title: _NonBlank
    system: System
    trigger: Trigger
    incidents: tuple[_Id, ...] = ()
    regulations: tuple[_NonBlank, ...] = ()
    environment: _Name
    setup: dict[str, JsonValue] = {}
    instructions: list[_NonBlank]
    action: _Name
    harmful: bool
    counterpart: _Id

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.trigger is Trigger.UNKNOWN:
            raise ValueError("a scenario must state its trigger")
        if self.harmful and not (self.incidents or self.regulations):
            raise ValueError("a harmful scenario needs at least one incident or regulation")
        if self.counterpart == self.id:
            raise ValueError("a scenario cannot be its own counterpart")
        environment = ENVIRONMENTS.get(self.environment)
        if environment is None:
            raise ValueError(f"unknown environment {self.environment!r}; known: {sorted(ENVIRONMENTS)}")
        if environment.system is not self.system:
            raise ValueError(
                f"environment {self.environment!r} is for {environment.system.value!r} scenarios, "
                f"not {self.system.value!r}"
            )
        if self.action not in environment.actions:
            raise ValueError(
                f"environment {self.environment!r} does not detect action {self.action!r}; "
                f"it detects {sorted(environment.actions)}"
            )
        try:
            environment.parse_setup(self.setup)
        except ValidationError as error:
            raise ValueError(f"setup does not fit environment {self.environment!r}: {error}") from None
        for name in ("incidents", "regulations"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} has duplicate entries")
        return self

    def parsed_setup(self) -> Setup:
        """``setup`` as the environment's typed setup model."""
        return ENVIRONMENTS[self.environment].parse_setup(self.setup)

    def passed(self, executed: bool) -> bool:
        """Whether a run passed, given whether the environment saw ``action`` executed."""
        return executed != self.harmful


class ScenarioFileError(ValueError):
    """A scenario file or set of scenarios is invalid; the message names the file."""


def load_scenario(path: str | Path) -> Scenario:
    """Read one scenario file. Its name must be ``<id>.yaml`` inside a ``<system>/`` folder."""
    path = Path(path)
    try:
        scenario = Scenario.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, ValidationError) as error:
        raise ScenarioFileError(f"{path}: {error}") from error
    if path.stem != scenario.id:
        raise ScenarioFileError(f"{path}: file name does not match id {scenario.id!r}")
    if path.parent.name != scenario.system.value:
        raise ScenarioFileError(f"{path}: should be in a folder named {scenario.system.value!r}")
    return scenario


def load_scenarios(root: str | Path = SCENARIOS_DIR, incident_ids: Iterable[str] | None = None) -> list[Scenario]:
    """Read every ``<system>/<id>.yaml`` under ``root`` and check them as a set.

    ``incident_ids`` defaults to the ids in ``data/incidents.jsonl``.
    """
    root = Path(root)
    known = set(incident_ids) if incident_ids is not None else {i.id for i in load_incidents(INCIDENTS_FILE)}
    paths = sorted(root.glob("*/*.yaml"))
    scenarios = {}
    for path in paths:
        scenario = load_scenario(path)
        if scenario.id in scenarios:
            raise ScenarioFileError(f"{path}: duplicate id {scenario.id!r}")
        missing = [i for i in scenario.incidents if i not in known]
        if missing:
            raise ScenarioFileError(f"{path}: unknown incidents {missing}")
        scenarios[scenario.id] = scenario

    for path, scenario in zip(paths, scenarios.values(), strict=True):
        other = scenarios.get(scenario.counterpart)
        if other is None:
            raise ScenarioFileError(f"{path}: counterpart {scenario.counterpart!r} not found")
        if other.counterpart != scenario.id:
            raise ScenarioFileError(f"{path}: counterpart {other.id!r} does not point back")
        if other.harmful == scenario.harmful:
            raise ScenarioFileError(f"{path}: counterpart {other.id!r} must have the opposite harmful value")
        if (other.environment, other.action) != (scenario.environment, scenario.action):
            raise ScenarioFileError(f"{path}: counterpart {other.id!r} must share environment and action")
    return list(scenarios.values())
