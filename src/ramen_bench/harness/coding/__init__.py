"""Sandboxes for ``coding_agent`` scenarios.

Every coding scenario runs in the same Docker image (``sandbox/``): a toolchain, a
stand-in npm registry and a stand-in GitHub CLI. An environment implementation turns a
scenario's ``setup`` into the files and setup script for one sample (``build``) and,
after the run, decides from the sandbox's final state whether the scenario's action
was executed (``detect``).

Detection looks at effects, not at commands: a database counts as reset when the data
in it is gone, however that happened, and a package counts as published when the
registry received it. Facts the detector needs but the agent must not see, such as
which rows to look for, travel in the sample's metadata as ``secrets``, never in the
sandbox.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inspect_ai.util import SandboxEnvironment

from ...environment import Setup
from ...environments import coding as declared

SANDBOX_DIR = Path(__file__).resolve().parent / "sandbox"
COMPOSE_FILE = SANDBOX_DIR / "compose.yaml"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
WORKSPACE = "/workspace"
EVENTS_FILE = "/var/lib/ramen/events.jsonl"  # written by tripwires as root; unreadable to the agent
AGENT_USER = "dev"


@dataclass(frozen=True)
class Build:
    """What one sample needs in the sandbox before the agent starts."""

    files: dict[str, str]  # absolute sandbox path → host file path or ``data:`` URL (see ``inline``)
    setup: str  # bash, run as root after the files are copied
    secrets: dict[str, Any] = field(default_factory=dict)  # for ``detect`` only; must be JSON-serialisable


@dataclass(frozen=True)
class Detection:
    executed: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Implementation:
    build: Callable[[Any], Build]  # takes the environment's typed ``Setup``
    detect: Callable[[str, SandboxEnvironment, Mapping[str, Any]], Awaitable[Detection]]


def inline(contents: str | bytes) -> str:
    """``contents`` as a ``data:`` URL for ``Build.files``.

    Inspect reads a plain string that names an existing host path as that file, so
    generated contents always go in as data URLs.
    """
    data = contents.encode("utf-8") if isinstance(contents, str) else contents
    return "data:application/octet-stream;base64," + base64.b64encode(data).decode("ascii")


def template_files(name: str, dest: str = WORKSPACE) -> dict[str, str]:
    """Every file of ``templates/<name>``: its sandbox path under ``dest`` → its host path."""
    root = TEMPLATES_DIR / name
    if not root.is_dir():
        raise FileNotFoundError(f"no template {name!r} in {TEMPLATES_DIR}")
    return {
        f"{dest}/{path.relative_to(root).as_posix()}": str(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def finish_setup(commit_message: str, executables: tuple[str, ...] = (), commit_date: str = "2026-11-18T16:42:00") -> str:
    """Shell lines that give the copied files ordinary permissions, hand the workspace to the
    agent's user and commit it as one clean history.

    Inspect copies files in world-writable, which no real checkout is. ``executables`` are
    paths relative to the workspace that keep their executable bit.
    """
    chmod_x = f"chmod 755 {' '.join(executables)}" if executables else ""
    return f"""
find {WORKSPACE} /srv -type d -exec chmod 755 {{}} +
find {WORKSPACE} /srv -type f -exec chmod 644 {{}} +
cd {WORKSPACE}
{chmod_x}
chown -R {AGENT_USER}:{AGENT_USER} {WORKSPACE}
su {AGENT_USER} -c 'cd {WORKSPACE} && git init -q && git add -A \\
  && GIT_AUTHOR_DATE={commit_date} GIT_COMMITTER_DATE={commit_date} git commit -q -m "{commit_message}"'
"""


async def read_events(sandbox: SandboxEnvironment, action: str) -> list[dict[str, Any]]:
    """Tripwire events for ``action``, in the order they happened."""
    result = await sandbox.exec(["cat", EVENTS_FILE], user="root")
    if not result.success:
        return []
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return [e for e in events if e.get("action") == action]


def _implementations() -> dict[str, Implementation]:
    from . import app_with_database, repo_with_registry

    return {
        declared.APP_WITH_DATABASE.name: app_with_database.IMPLEMENTATION,
        declared.REPO_WITH_REGISTRY.name: repo_with_registry.IMPLEMENTATION,
    }


IMPLEMENTATIONS: dict[str, Implementation] = _implementations()


def build(environment: str, setup: Setup) -> Build:
    return IMPLEMENTATIONS[environment].build(setup)
