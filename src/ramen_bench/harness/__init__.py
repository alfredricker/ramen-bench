"""Inspect tasks that run scenarios, one suite per ``System``.

- ``coding``: ``coding_agent`` scenarios in a shared Docker sandbox (``harness.coding``).

Scoring is shared by every suite (``harness.scoring``). The tasks are registered with
Inspect under ``ramen_bench/<suite>`` through the ``inspect_ai`` entry point.
"""
