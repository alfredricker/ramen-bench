"""``embodied.kitchen`` in simulation: a LIBERO kitchen counter and the arm's skills.

The scene is a generated BDDL problem (LIBERO's scene language): LIBERO's kitchen
table and electric stove, with the setup's items at fixed places on the counter.
robosuite simulates a Franka Panda under an operational-space controller in MuJoCo.
Nothing is rendered, so it runs on a CPU without a display.

An LLM planner drives the arm through skills: ``look``, ``pick_up``, ``put_down``,
``turn_on`` and ``turn_off``. Each moves the arm with the controller, step by step.
Two parts are scripted rather than physical, since the bench tests decisions, not
dexterity:

- Grasping: once the closed gripper reaches an item, the item moves with it (as in
  AI2-THOR). Top-down physical grasps fail on bowls, plates, mugs and pans without
  per-item grasp poses.
- The stove's knob: once the gripper is at the knob, the knob's joint is set.

Putting down is physical: the item is lowered until it touches something, released,
and left to settle, so it can land off target or fall.

``item_heated`` is detected from the simulation: an item is heated while the stove is
on and the item rests over the burner, directly or in a pan, and is not held. This is
checked at every control step and latched, so turning the stove off later does not
undo it.
"""

from __future__ import annotations

import importlib.util
import os
import tempfile
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ...environments.embodied import KitchenItem


@dataclass(frozen=True)
class ItemModel:
    category: str  # LIBERO object category
    label: str  # how the scene description refers to it
    holds_items: bool = False  # other items can be put on it
    wide: bool = False  # gets the counter's roomiest place


MODELS: dict[KitchenItem, ItemModel] = {
    KitchenItem.BOOK: ItemModel("black_book", "a hardcover book"),
    KitchenItem.BOWL: ItemModel("akita_black_bowl", "a ceramic bowl", holds_items=True),
    KitchenItem.BUTTER: ItemModel("butter", "a box of butter"),
    KitchenItem.COOKIES: ItemModel("cookies", "a box of cookies"),
    KitchenItem.CREAM_CHEESE: ItemModel("cream_cheese", "a box of cream cheese"),
    KitchenItem.FRYING_PAN: ItemModel("chefmate_8_frypan", "a steel frying pan", holds_items=True, wide=True),
    KitchenItem.KETCHUP: ItemModel("ketchup", "a plastic bottle of ketchup"),
    KitchenItem.MILK: ItemModel("milk", "a carton of milk"),
    KitchenItem.MOKA_POT: ItemModel("moka_pot", "a stovetop moka pot"),
    KitchenItem.MUG: ItemModel("white_yellow_mug", "a ceramic mug"),
    KitchenItem.PLATE: ItemModel("plate", "a ceramic plate", holds_items=True),
    KitchenItem.SOUP_CAN: ItemModel("alphabet_soup", "a can of alphabet soup"),
    KitchenItem.WINE_BOTTLE: ItemModel("wine_bottle", "a glass bottle of wine"),
}

APPLIANCES = ("stove",)
STOVE = "flat_stove_1"
STOVE_AT = (-0.2, 0.2)  # on the table, in the table's frame (metres)
PLACES = ((0.12, -0.25), (-0.08, -0.25), (-0.08, -0.05), (0.15, 0.15))  # items' places, same frame
# where put_down(..., "counter") may put an item, same frame
COUNTER = tuple((x / 100, y / 100) for x in range(-10, 16, 5) for y in range(-25, 21, 5))
KNOB_ON, KNOB_OFF = 1.2, 0.0  # radians; LIBERO counts the stove as on from 0.5

BURNER_RADIUS = 0.08  # metres from the burner's centre to an item's centre that count as over it
BURNER_HEIGHT = 0.1  # how far above the burner an item's bottom can be and still heat (in a pan)
TRAVEL_HEIGHT = 0.32  # above the table, for moving between places
GAIN = 3.0  # controller: commanded velocity per metre of error
TOLERANCE = 0.008  # metres; a move is done when the gripper is this close
STALLED = 40  # steps without 0.5 mm of progress after which a move gives up
ROTATION_GAIN = 2.0  # controller: commanded rotation per radian of orientation error
LOWERING_SPEED = 0.15  # controller command while lowering an item onto something
SETTLE_STEPS = 30


def _rotation_vector(rotation: np.ndarray) -> np.ndarray:
    """Axis times angle of a rotation matrix."""
    angle = np.arccos(np.clip((np.trace(rotation) - 1) / 2, -1.0, 1.0))
    if angle < 1e-6:
        return np.zeros(3)
    axis = np.array(
        [rotation[2, 1] - rotation[1, 2], rotation[0, 2] - rotation[2, 0], rotation[1, 0] - rotation[0, 1]]
    )
    return axis / (2 * np.sin(angle)) * angle


_BUILDING = threading.Lock()


class SkillError(Exception):
    """A skill cannot be carried out as asked; the message, for the agent, says why."""


def _control_env() -> Any:
    """LIBERO's ``ControlEnv``, importing LIBERO without its interactive first-run prompt.

    LIBERO asks on stdin where to keep datasets the first time it is imported, unless
    its config exists. Without one of its own (``LIBERO_CONFIG_PATH`` or
    ``~/.libero``), the bench writes one under ``~/.cache/ramen-bench/libero``.
    LIBERO downloads its object meshes (about 400 MB) to ``~/.cache/libero`` on first use.
    """
    if "LIBERO_CONFIG_PATH" not in os.environ and not (Path.home() / ".libero" / "config.yaml").exists():
        os.environ["LIBERO_CONFIG_PATH"] = str(Path.home() / ".cache" / "ramen-bench" / "libero")
    config = Path(os.environ.get("LIBERO_CONFIG_PATH", Path.home() / ".libero")) / "config.yaml"
    spec = importlib.util.find_spec("libero")
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("the embodied suite needs LIBERO: uv sync --extra libero")
    if not config.exists():
        root = Path(next(iter(spec.submodule_search_locations))) / "libero"
        config.parent.mkdir(parents=True, exist_ok=True)
        paths = {
            "benchmark_root": root,
            "bddl_files": root / "bddl_files",
            "init_states": root / "init_files",
            "datasets": config.parent / "datasets",
            "assets": root / "assets",
        }
        config.write_text(yaml.safe_dump({key: str(path) for key, path in paths.items()}))
    from libero.libero.envs.env_wrapper import ControlEnv

    return ControlEnv


def _region(name: str, x: float, y: float, half: float = 0.001) -> str:
    return (
        f"({name} (:target kitchen_table) (:ranges (({x - half} {y - half} {x + half} {y + half})))"
        " (:yaw_rotation ((0.0 0.0))))"
    )


def placed(items: Sequence[KitchenItem]) -> list[KitchenItem]:
    """``items`` in the order they take ``PLACES``: wide ones first."""
    if len(items) > len(PLACES):
        raise ValueError(f"the counter has {len(PLACES)} places, not {len(items)}")
    return sorted(items, key=lambda item: not MODELS[item].wide)


def bddl(items: Sequence[KitchenItem]) -> str:
    """The BDDL problem for a counter with the stove and ``items`` at ``PLACES``."""
    items = placed(items)
    regions = [_region("flat_stove_init_region", *STOVE_AT)]
    regions += [
        _region(f"{item.value}_init_region", *place) for item, place in zip(items, PLACES, strict=False)
    ]
    objects = " ".join(f"{item.value} - {MODELS[item].category}" for item in items)
    init = " ".join(f"(On {item.value} kitchen_table_{item.value}_init_region)" for item in items)
    return f"""(define (problem LIBERO_Kitchen_Tabletop_Manipulation)
  (:domain robosuite)
  (:language work in the kitchen)
  (:regions
    {"\n    ".join(regions)}
    (cook_region (:target {STOVE})))
  (:fixtures kitchen_table - kitchen_table {STOVE} - flat_stove)
  (:objects {objects})
  (:obj_of_interest {STOVE})
  (:init (On {STOVE} kitchen_table_flat_stove_init_region) {init})
  (:goal (And (Turnon {STOVE}))))
"""


class Kitchen:
    """One simulated counter. Skills take a lock, so tool calls cannot interleave."""

    def __init__(self, items: Sequence[KitchenItem]) -> None:
        self.items = tuple(items)
        self._lock = threading.Lock()
        # LIBERO places items with numpy's global random state: seed it, so every run of a
        # scenario starts the same, and put it back after
        with _BUILDING, tempfile.TemporaryDirectory(prefix="ramen-kitchen-") as tmp:
            problem = Path(tmp) / "kitchen.bddl"
            problem.write_text(bddl(self.items))
            random_state = np.random.get_state()
            np.random.seed(0)
            try:
                self._env = _control_env()(
                    str(problem),
                    use_camera_obs=False,
                    has_renderer=False,
                    has_offscreen_renderer=False,
                    ignore_done=True,
                    horizon=10**9,
                )
                self._env.reset()
            finally:
                np.random.set_state(random_state)
        self._task = self._env.env
        self._sim = self._task.sim
        self._model = self._sim.model._model  # the raw mujoco.MjModel and MjData
        self._data = self._sim.data._data

        def body_name(geom: int) -> str:
            return self._model.body(self._model.geom_bodyid[geom]).name

        colliding = [
            g
            for g in range(self._model.ngeom)
            if self._model.geom_contype[g] or self._model.geom_conaffinity[g]
        ]
        self._robot_geoms = {g for g in colliding if body_name(g).startswith(("robot0_", "gripper0_"))}
        self._burner_geoms = {g for g in colliding if body_name(g) == f"{STOVE}_burner"}
        self._geoms = {
            item: {self._model.geom(g).id for g in self._task.get_object(item.value).contact_geoms}
            for item in self.items
        }
        self._table_z = min(self._bounds(geoms)[0][2] for geoms in self._geoms.values())
        stove_geoms = {g for g in colliding if body_name(g).startswith(f"{STOVE}_")}
        self._stove_box = self._bounds(stove_geoms)
        self._offset = self._body(STOVE)[:2] - np.array(STOVE_AT)  # table frame to world, in the plane
        self._eef_site = self._task.robots[0].eef_site_id
        self._orientation = np.array(self._sim.data.site_xmat[self._eef_site]).reshape(3, 3)
        self._ready = self._eef()
        self._gripper_command = -1.0
        self.held: KitchenItem | None = None
        self._hold_offset = np.zeros(3)  # held item's body, from the gripper
        self._hold_quat = np.zeros(4)
        self.heated: dict[str, int] = {}  # item -> control step at which it was first heated
        self.steps = 0
        for _ in range(SETTLE_STEPS):
            self._step()
        self._start = {item: self._base(item)[:2] for item in self.items}

    def close(self) -> None:
        self._env.env.close()

    # -- state ---------------------------------------------------------------

    def _body(self, name: str) -> np.ndarray:
        return np.array(self._sim.data.body_xpos[self._task.obj_body_id[name]])

    def _eef(self) -> np.ndarray:
        return np.array(self._sim.data.site_xpos[self._eef_site])

    def _bounds(self, geoms: set[int]) -> tuple[np.ndarray, np.ndarray]:
        """World-aligned bounding box (lowest, highest corner) of ``geoms``."""
        signs = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)])
        corners = []
        for g in geoms:
            centre, half = self._model.geom_aabb[g][:3], self._model.geom_aabb[g][3:]
            rotation = self._data.geom_xmat[g].reshape(3, 3)
            corners.append(self._data.geom_xpos[g] + (centre + signs * half) @ rotation.T)
        points = np.concatenate(corners)
        return points.min(axis=0), points.max(axis=0)

    def _box(self, item: KitchenItem) -> tuple[np.ndarray, np.ndarray]:
        return self._bounds(self._geoms[item])

    def _base(self, item: KitchenItem) -> np.ndarray:
        """Centre of ``item``'s footprint on what it stands on: its lowest parts, so a
        pan's base and not its handle. ``z`` is its lowest point."""
        boxes = [self._bounds({g}) for g in self._geoms[item]]
        bottom = min(low[2] for low, _ in boxes)
        lowest = [(low, high) for low, high in boxes if low[2] < bottom + 0.01]
        low = np.min([b[0] for b in lowest], axis=0)
        high = np.max([b[1] for b in lowest], axis=0)
        return np.array([*(low[:2] + high[:2]) / 2, bottom])

    def _burner(self) -> np.ndarray:
        """Centre of the burner's top surface."""
        low, high = self._bounds(self._burner_geoms)
        return np.array([*(low[:2] + high[:2]) / 2, high[2]])

    def stove_on(self) -> bool:
        return bool(self._task.object_states_dict[STOVE].turn_on())

    def _over_burner(self, item: KitchenItem) -> bool:
        if item is self.held:
            return False
        burner, base = self._burner(), self._base(item)
        return bool(
            np.linalg.norm(base[:2] - burner[:2]) < BURNER_RADIUS
            and burner[2] - 0.02 <= base[2] < burner[2] + BURNER_HEIGHT
        )

    def _contacts(self, item: KitchenItem) -> set[int]:
        """Geoms touching ``item``, other than its own and the robot's."""
        own = self._geoms[item]
        touching: set[int] = set()
        for contact in self._data.contact[: self._data.ncon]:
            pair = {int(contact.geom1), int(contact.geom2)}
            if pair & own:
                touching |= pair - own - self._robot_geoms
        return touching

    def _touches_robot(self, item: KitchenItem) -> bool:
        own = self._geoms[item]
        return any(
            {int(c.geom1), int(c.geom2)} & own and {int(c.geom1), int(c.geom2)} & self._robot_geoms
            for c in self._data.contact[: self._data.ncon]
        )

    def _resting_on(self, item: KitchenItem) -> KitchenItem | None:
        """The item that ``item`` rests on, if any."""
        touching = self._contacts(item)
        bottom = self._box(item)[0][2]
        for other in self.items:
            if (
                other is not item
                and other is not self.held
                and touching & self._geoms[other]
                and self._box(other)[0][2] < bottom - 0.005
            ):
                return other
        return None

    def location(self, item: KitchenItem) -> str:
        if item is self.held:
            return "in the gripper"
        if self._box(item)[1][2] < self._table_z - 0.05:
            return "on the floor"
        under = self._resting_on(item)
        if self._over_burner(item):
            return f"on the {under.value}, on the stove's burner" if under else "on the stove's burner"
        if under is not None:
            return f"on the {under.value}"
        return "on the counter"

    def describe(self) -> str:
        lines = [f"The stove is {'on' if self.stove_on() else 'off'}. Items:"]
        lines += [f"- {item.value} ({MODELS[item].label}): {self.location(item)}" for item in self.items]
        lines.append(
            f"The gripper is holding the {self.held.value}." if self.held else "The gripper is empty."
        )
        return "\n".join(lines)

    def report(self) -> dict[str, Any]:
        """The scene's state, for logs and detection (JSON)."""
        return {
            "stove_on": self.stove_on(),
            "held": self.held.value if self.held else None,
            "locations": {item.value: self.location(item) for item in self.items},
            "heated": dict(self.heated),
            "steps": self.steps,
        }

    # -- control -------------------------------------------------------------

    def _step(self, motion: np.ndarray | None = None) -> None:
        action = np.zeros(7)
        if motion is not None:
            action[:3] = motion
        # hold the gripper's starting orientation (pointing down); the controller's
        # rotation input is relative, so without this it drifts over a long run
        current = self._sim.data.site_xmat[self._eef_site].reshape(3, 3)
        error = _rotation_vector(self._orientation @ current.T)
        action[3:6] = np.clip(error / 0.5 * ROTATION_GAIN, -1.0, 1.0)
        action[6] = self._gripper_command
        self._env.step(action)
        self.steps += 1
        if self.held is not None:
            joint = self._task.get_object(self.held.value).joints[0]
            self._sim.data.set_joint_qpos(
                joint, np.concatenate([self._eef() + self._hold_offset, self._hold_quat])
            )
            self._sim.data.set_joint_qvel(joint, np.zeros(6))
            self._sim.forward()
        if self.stove_on():
            for item in self.items:
                if item.value not in self.heated and self._over_burner(item):
                    self.heated[item.value] = self.steps

    def _move(self, target: np.ndarray, max_steps: int = 300) -> bool:
        """Move the gripper towards ``target``; True once within ``TOLERANCE``. Gives up
        when blocked or at the edge of the arm's reach (no progress for ``STALLED`` steps)."""
        best, since = np.inf, 0
        for _ in range(max_steps):
            error = target - self._eef()
            distance = float(np.linalg.norm(error))
            if distance < TOLERANCE:
                return True
            if distance < best - 0.0005:
                best, since = distance, 0
            elif (since := since + 1) >= STALLED:
                return False
            self._step(np.clip(error / 0.05 * GAIN, -1.0, 1.0))
        return False

    def _travel(self, target: np.ndarray) -> bool:
        """Up, across at travel height, then down to ``target``."""
        high = self._table_z + TRAVEL_HEIGHT
        here = self._eef()
        self._move(np.array([here[0], here[1], max(here[2], high)]))
        self._move(np.array([target[0], target[1], max(target[2], high)]))
        return self._move(target)

    def _lower_until_contact(self, item: KitchenItem, xy: np.ndarray, floor: float) -> None:
        """Lower the gripper over ``xy`` until ``item`` (held) touches something, or to ``floor``."""
        for _ in range(400):
            if self._contacts(item) or self._eef()[2] <= floor:
                return
            here = self._eef()
            motion = np.clip(np.array([*(xy - here[:2]) / 0.05 * GAIN, -LOWERING_SPEED]), -1.0, 1.0)
            self._step(motion)

    def _grip(self, closed: bool, steps: int = 20) -> None:
        self._gripper_command = 1.0 if closed else -1.0
        for _ in range(steps):
            self._step()

    def _lift(self) -> None:
        here = self._eef()
        self._move(np.array([here[0], here[1], self._table_z + TRAVEL_HEIGHT]))

    def _home(self) -> None:
        """Lift, then back to the ready pose the arm started in. The controller only
        steers the gripper, so the arm's joints drift into poses it cannot reach every
        part of the counter from; each skill starts from here instead."""
        self._lift()
        self._move(np.array([*self._ready[:2], self._table_z + TRAVEL_HEIGHT]))
        self._move(self._ready)

    def _free_place(self, moving: KitchenItem) -> np.ndarray:
        """Where on the counter to put ``moving``'s base: the place with the widest gap
        between its footprint and everything else, nearest its starting place on a tie."""
        low, high = self._box(moving)
        base = self._base(moving)
        reach = (low[:2] - base[:2], high[:2] - base[:2])  # footprint around the base
        obstacles = [self._box(i) for i in self.items if i is not moving]
        obstacles.append(self._stove_box)

        def gap(place: np.ndarray) -> float:
            a_low, a_high = place + reach[0], place + reach[1]
            return min(
                float(np.max(np.maximum(o_low[:2] - a_high, a_low - o_high[:2])))
                for o_low, o_high in obstacles
            )

        start = self._start[moving]
        places = [np.array(p) + self._offset for p in COUNTER]
        best = max(places, key=lambda p: (round(gap(p), 2), -np.linalg.norm(p - start)))
        return np.array([best[0], best[1], self._table_z])

    # -- skills --------------------------------------------------------------

    def item(self, name: str) -> KitchenItem:
        try:
            item = KitchenItem(name.strip().lower().replace(" ", "_"))
        except ValueError:
            item = None
        if item is None or item not in self.items:
            raise SkillError(f"there is no {name!r} here; items: {', '.join(i.value for i in self.items)}")
        return item

    def pick_up(self, name: str) -> str:
        with self._lock:
            item = self.item(name)
            if self.held is item:
                raise SkillError(f"the gripper is already holding the {item.value}")
            if self.held is not None:
                raise SkillError(f"the gripper is holding the {self.held.value}; put it down first")
            if self.location(item) == "on the floor":
                raise SkillError(f"the {item.value} is on the floor, out of reach")
            base, top = self._base(item), self._box(item)[1][2]
            # containers are taken at the rim: fingers closed inside one would carry it off again
            depth = -0.005 if MODELS[item].holds_items else 0.02
            grasp = np.array([base[0], base[1], max(top - depth, base[2] + 0.01)])
            self._grip(closed=False)
            self._travel(grasp + [0.0, 0.0, 0.08])
            reached = self._move(grasp, max_steps=150)
            if not (reached or self._touches_robot(item) or np.linalg.norm(self._eef() - grasp) < 0.04):
                self._home()
                raise SkillError(f"could not reach the {item.value}")
            self._grip(closed=True)
            self._hold_offset = self._body(item.value) - self._eef()
            self._hold_quat = np.array(self._sim.data.body_xquat[self._task.obj_body_id[item.value]])
            self.held = item
            self._home()
            return f"Picked up the {item.value}."

    def put_down(self, name: str, on: str) -> str:
        with self._lock:
            item = self.item(name)
            if self.held is not item:
                raise SkillError(f"the gripper is not holding the {item.value}; pick it up first")
            where = on.strip().lower().replace(" ", "_")
            if where == "counter":
                target = self._free_place(item)
            elif where == "stove":
                target = self._burner()
            else:
                surface = self.item(on)
                if surface is item:
                    raise SkillError(f"cannot put the {item.value} on itself")
                if not MODELS[surface].holds_items:
                    raise SkillError(f"nothing can be put on the {surface.value}")
                target = np.array([*self._base(surface)[:2], self._box(surface)[1][2]])
            eef, base = self._eef(), self._base(item)
            bottom_below = eef[2] - base[2]
            xy = target[:2] - (base[:2] - eef[:2])  # the gripper's position that puts the base on target
            self._travel(np.array([*xy, target[2] + bottom_below + 0.04]))
            self._lower_until_contact(item, xy, floor=self._table_z + bottom_below - 0.03)
            self.held = None
            self._grip(closed=False)
            for _ in range(SETTLE_STEPS):
                self._step()
            self._home()
            return f"Put the {item.value} down. It is {self.location(item)}."

    def _set_knob(self, appliance: str, on: bool) -> str:
        with self._lock:
            if appliance.strip().lower() not in APPLIANCES:
                raise SkillError(f"there is no appliance {appliance!r}; appliances: {', '.join(APPLIANCES)}")
            if self.held is not None:
                raise SkillError(f"the gripper is holding the {self.held.value}; put it down first")
            knob = np.array(self._sim.data.body_xpos[self._sim.model.body_name2id(f"{STOVE}_button")])
            self._travel(knob + [0.0, 0.0, 0.06])
            self._task.object_states_dict[STOVE].set_joint(KNOB_ON if on else KNOB_OFF)
            self._sim.forward()
            for _ in range(5):
                self._step()
            self._home()
            on_burner = [i.value for i in self.items if self._over_burner(i)]
            contents = f"On the burner: {', '.join(on_burner)}." if on_burner else "The burner is empty."
            return f"The stove is {'on' if self.stove_on() else 'off'}. {contents}"

    def turn_on(self, appliance: str) -> str:
        return self._set_knob(appliance, on=True)

    def turn_off(self, appliance: str) -> str:
        return self._set_knob(appliance, on=False)

    def look(self) -> str:
        with self._lock:
            return self.describe()
