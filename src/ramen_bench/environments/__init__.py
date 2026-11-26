"""Every environment a scenario can name, keyed by name.

To add one, declare it in the module for its system and list it in ``_ALL``.
"""

from __future__ import annotations

from ..environment import Environment
from . import coding

_ALL: tuple[Environment, ...] = (
    coding.APP_WITH_DATABASE,
    coding.REPO_WITH_REGISTRY,
)

ENVIRONMENTS: dict[str, Environment] = {}
for _environment in _ALL:
    if _environment.name in ENVIRONMENTS:
        raise ValueError(f"duplicate environment {_environment.name!r}")
    ENVIRONMENTS[_environment.name] = _environment


def get_environment(name: str) -> Environment:
    """The environment called ``name``; ``KeyError`` names the known ones if missing."""
    try:
        return ENVIRONMENTS[name]
    except KeyError:
        raise KeyError(f"unknown environment {name!r}; known: {sorted(ENVIRONMENTS)}") from None
