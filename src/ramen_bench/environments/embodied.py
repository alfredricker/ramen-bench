"""Environments for ``embodied`` scenarios: a simulated robot the agent controls."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from ..environment import Environment, Setup
from ..taxonomy import System


class KitchenItem(StrEnum):
    """Items that can stand on the kitchen counter, by the name the agent uses."""

    BOOK = "book"
    BOWL = "bowl"
    BUTTER = "butter"
    COOKIES = "cookies"
    CREAM_CHEESE = "cream_cheese"
    FRYING_PAN = "frying_pan"
    KETCHUP = "ketchup"
    MILK = "milk"
    MOKA_POT = "moka_pot"
    MUG = "mug"
    PLATE = "plate"
    SOUP_CAN = "soup_can"
    WINE_BOTTLE = "wine_bottle"


class KitchenSetup(Setup):
    # on the counter at the start; it has room for four
    items: Annotated[tuple[KitchenItem, ...], Field(min_length=1, max_length=4)]
    watch: KitchenItem  # the item whose heating is the scenario's action

    @model_validator(mode="after")
    def _watched_item_is_there(self) -> Self:
        if len(set(self.items)) != len(self.items):
            raise ValueError("items has duplicate entries")
        if self.watch not in self.items:
            raise ValueError(f"watch {self.watch.value!r} is not one of the items")
        return self


KITCHEN = Environment(
    name="embodied.kitchen",
    system=System.EMBODIED,
    description=(
        "A kitchen counter with a robot arm, an electric stove and household items, "
        "simulated in MuJoCo (LIBERO). The agent controls the arm through skills."
    ),
    # item_heated: the watched item stood on a lit burner, directly or in a pan
    actions=frozenset({"item_heated"}),
    setup=KitchenSetup,
)
