"""Choosing which scenarios to run.

A ``Selection`` lists allowed values per field and, under ``exclude``, values to
leave out. A field left out allows everything.

- Include: a scenario must match every field given (any value within a field).
- Exclude: a scenario is left out if it matches any value of any field given.

Selection works on pairs, not single scenarios: a pair is run when either scenario
matches the include filters and neither matches the exclude filters. Running one side
of a pair alone would leave its harm rate or overcaution rate without the control it
is meant to be read against.

Unknown systems, triggers, environments and ids are errors, so a typo cannot silently
select nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .environments import ENVIRONMENTS
from .scenario import Scenario
from .taxonomy import System, Trigger


class Filter(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    systems: Annotated[tuple[System, ...], Field(min_length=1)] | None = None
    environments: Annotated[tuple[str, ...], Field(min_length=1)] | None = None
    ids: Annotated[tuple[str, ...], Field(min_length=1)] | None = None
    triggers: Annotated[tuple[Trigger, ...], Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def _known_environments(self) -> Self:
        unknown = sorted(set(self.environments or ()) - set(ENVIRONMENTS))
        if unknown:
            raise ValueError(f"unknown environments {unknown}; known: {sorted(ENVIRONMENTS)}")
        return self

    def _hits(self, scenario: Scenario) -> list[bool]:
        """For each field given, whether ``scenario`` has one of its values."""
        checks = (
            (self.systems, scenario.system),
            (self.environments, scenario.environment),
            (self.ids, scenario.id),
            (self.triggers, scenario.trigger),
        )
        return [value in allowed for allowed, value in checks if allowed is not None]

    def matches_all(self, scenario: Scenario) -> bool:
        return all(self._hits(scenario))

    def matches_any(self, scenario: Scenario) -> bool:
        return any(self._hits(scenario))


class Selection(Filter):
    exclude: Filter = Filter()

    def apply(self, scenarios: Iterable[Scenario]) -> list[Scenario]:
        """The selected scenarios, in their original order. Expects a checked set
        (``load_scenarios``), so every counterpart is present."""
        scenarios = list(scenarios)
        by_id = {s.id: s for s in scenarios}
        unknown = sorted({*(self.ids or ()), *(self.exclude.ids or ())} - set(by_id))
        if unknown:
            raise ValueError(f"unknown scenario ids {unknown}")
        selected = []
        for scenario in scenarios:
            pair = (scenario, by_id[scenario.counterpart])
            if any(map(self.matches_all, pair)) and not any(map(self.exclude.matches_any, pair)):
                selected.append(scenario)
        return selected
