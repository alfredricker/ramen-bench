"""An environment: a world a scenario runs in.

An environment is declared once and shared by every scenario that names it. The
declaration says which ``System`` it tests, which ``actions`` it can detect, and what
its ``setup`` looks like, so a scenario with a misspelt action or setup key is
rejected when it is loaded rather than when it is run.

The declarations here carry no harness code, so scenarios load without Inspect or a
simulator installed. Harnesses look up an environment by name and build it from
``parse_setup``. The concrete environments live in ``ramen_bench.environments``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, JsonValue

from .taxonomy import System

NAME_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$"


class Setup(BaseModel):
    """Base for an environment's setup parameters. Unknown keys are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True)
class Environment:
    name: str  # dotted, e.g. ``coding.app_with_database``
    system: System  # scenarios in this environment must have this system
    description: str
    actions: frozenset[str]  # the actions this environment detects
    setup: type[Setup]

    def __post_init__(self) -> None:
        if not re.fullmatch(NAME_PATTERN, self.name):
            raise ValueError(f"invalid environment name {self.name!r}")
        if not self.actions:
            raise ValueError(f"environment {self.name!r} detects no actions")
        for action in self.actions:
            if not re.fullmatch(NAME_PATTERN, action):
                raise ValueError(f"environment {self.name!r}: invalid action name {action!r}")

    def parse_setup(self, setup: Mapping[str, JsonValue]) -> Setup:
        """Validate a scenario's ``setup`` against this environment's setup model."""
        return self.setup.model_validate(setup)
