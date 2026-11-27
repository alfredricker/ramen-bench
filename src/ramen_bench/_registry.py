"""Inspect entry point: importing this registers the bench's tasks and approvers as ``ramen_bench/<name>``."""

from .harness.coding.task import coding  # noqa: F401
from .harness.firewalls.ramen import ramen  # noqa: F401
