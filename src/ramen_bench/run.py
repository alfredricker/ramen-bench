"""``ramen-bench run``: run the bench from a config file.

    ramen-bench run                    # reads ./config.yaml
    ramen-bench run runs/coding.yaml --dry-run

The config (see ``config.example.yaml``) names the model, the scenarios to run
(``select``, a ``Selection``), the environment variables the run needs, and keyword
arguments for Inspect's ``eval_set`` (``eval``), which are passed through as written,
except for a list under ``eval.approval``: it is wrapped as ``{approvers: [...]}`` and
ends with an ``auto`` approver for every tool it does not name. A firewall guards the
tools it lists; Inspect would otherwise reject the rest, including the agent's
``submit``. An approval policy given as a mapping or a file path is left as it is.

One Inspect task runs per system with selected scenarios. ``.env`` in the working
directory (or a parent) is loaded first, without overriding variables already set.
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Any

import yaml
from dotenv import find_dotenv, load_dotenv
from inspect_ai import Task, eval_set
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .scenario import Scenario, ScenarioFileError, load_scenarios
from .selection import Selection
from .taxonomy import System

_SET_BY_RUN = frozenset({"tasks", "model"})  # eval_set arguments the config sets itself
_EVAL_SET_ARGS = frozenset(inspect.signature(eval_set).parameters) - _SET_BY_RUN


class ConfigError(ValueError):
    """The config file is missing, malformed, or asks for something that cannot run."""


class RunConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str | Annotated[tuple[str, ...], Field(min_length=1)]  # <provider>/<model>, or several
    select: Selection = Selection()
    require_env: tuple[str, ...] = ()  # names of variables that must be set
    eval: dict[str, Any] = {}  # keyword arguments for inspect_ai.eval_set

    @field_validator("eval")
    @classmethod
    def _eval_set_arguments(cls, value: dict[str, Any]) -> dict[str, Any]:
        clash = sorted(set(value) & _SET_BY_RUN)
        if clash:
            raise ValueError(f"set {clash} at the top level of the config, not under eval")
        unknown = sorted(set(value) - _EVAL_SET_ARGS)
        if unknown:
            raise ValueError(f"not arguments of inspect_ai.eval_set: {unknown}")
        return value

    def eval_set_args(self) -> dict[str, Any]:
        """``eval`` with ``approval`` in a form ``eval_set`` accepts."""
        from inspect_ai.approval._policy import ApprovalPolicyConfig  # not exported publicly

        args = dict(self.eval)
        approval = args.get("approval")
        if isinstance(approval, list):
            approval = {"approvers": [*approval, {"name": "auto", "tools": "*"}]}
        if isinstance(approval, dict):
            args["approval"] = ApprovalPolicyConfig.model_validate(approval)
        return args


def load_config(path: str | Path) -> RunConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"{path}: no such file (start from config.example.yaml)") from None
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: {error}") from None
    try:
        return RunConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigError(f"{path}: {error}") from None


def suites() -> dict[System, Callable[..., Task]]:
    """The Inspect task that runs each system's scenarios."""
    from .harness.coding.task import coding
    from .harness.embodied.task import embodied

    return {System.CODING_AGENT: coding, System.EMBODIED: embodied}


def plan(config: RunConfig, scenarios: Sequence[Scenario] | None = None) -> dict[System, list[Scenario]]:
    """The selected scenarios by system, checking that each system has a suite."""
    try:
        selected = config.select.apply(load_scenarios() if scenarios is None else scenarios)
    except ScenarioFileError:
        raise
    except ValueError as error:  # unknown ids
        raise ConfigError(f"select: {error}") from None
    if not selected:
        raise ConfigError("select matches no scenarios")
    by_system: dict[System, list[Scenario]] = {}
    for scenario in selected:
        by_system.setdefault(scenario.system, []).append(scenario)
    missing = sorted(system.value for system in set(by_system) - set(suites()))
    if missing:
        raise ConfigError(f"no suite runs {missing} scenarios yet; exclude those systems")
    return by_system


def missing_env(config: RunConfig) -> list[str]:
    return [name for name in config.require_env if not os.environ.get(name)]


def run(config: RunConfig, *, dry_run: bool = False) -> bool:
    """Run the bench; ``dry_run`` prints what would run instead. True when every task succeeded."""
    load_dotenv(find_dotenv(usecwd=True))
    by_system = plan(config)
    missing = missing_env(config)
    if dry_run:
        models = [config.model] if isinstance(config.model, str) else list(config.model)
        print(f"models: {', '.join(models)}")
        for system, scenarios in by_system.items():
            print(f"{system.value}:")
            for scenario in scenarios:
                print(f"  {scenario.id}  ({'harmful' if scenario.harmful else 'harmless'})")
        if missing:
            print(f"missing environment variables: {', '.join(missing)}")
        return not missing
    if missing:
        raise ConfigError(f"missing environment variables: {', '.join(missing)} (set them in .env)")
    select = config.select.model_dump(mode="json", exclude_defaults=True)
    tasks = [suites()[system](select=select) for system in by_system]
    model = config.model if isinstance(config.model, str) else list(config.model)
    success, _ = eval_set(tasks=tasks, model=model, **config.eval_set_args())
    return success


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ramen-bench", description="Run the Ramen safety bench.")
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="run the scenarios a config selects")
    run_parser.add_argument("config", nargs="?", default="config.yaml", help="run config (default: config.yaml)")
    run_parser.add_argument("--dry-run", action="store_true", help="list what would run, then stop")
    args = parser.parse_args(argv)
    try:
        ok = run(load_config(args.config), dry_run=args.dry_run)
    except (ConfigError, ScenarioFileError) as error:
        print(f"ramen-bench: {error}", file=sys.stderr)
        return 2
    return 0 if ok else 1
