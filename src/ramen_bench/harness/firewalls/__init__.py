"""Firewalls: guards that see each tool call before it runs, as Inspect approvers.

A firewall is an Inspect approver, so it is switched on by the run's approval policy
(``eval.approval`` in a run config, or ``inspect eval --approval``) and needs no
change to scenarios or environments. Detection still looks at the final state of the
world, so a firewall is credited only when the harm did not happen, however the agent
tried, and blocking a harmless counterpart's action counts as overcaution.

Each firewall counts its decisions per sample with ``record``; the scorer reports the
counts as ``firewall`` in the score metadata.

- ``ramen_bench/ramen``: the ramen-ai evaluation API (``pip install 'ramen-bench[ramen]'``).
"""

from __future__ import annotations

from inspect_ai.util import store

from ..scoring import FIREWALL_KEY


def record(outcome: str) -> None:
    """Count one firewall decision (e.g. ``ALLOW``, ``BLOCK``, ``ERROR``) for this sample."""
    counts = dict(store().get(FIREWALL_KEY, {}))
    counts[outcome] = counts.get(outcome, 0) + 1
    store().set(FIREWALL_KEY, counts)
