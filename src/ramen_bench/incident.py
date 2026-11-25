"""An incident: an event in which an AI system acted dangerously.

All incidents, real and artificial, are stored as JSON Lines, one record per line,
in ``data/incidents.jsonl``. The ``origin`` field tells them apart.
See the README for the fields.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Self

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, ValidationError, model_validator

from .taxonomy import Entity, HarmDomain, HarmType, Intent, Origin, System, Timing, Trigger

DATA_DIR = Path(__file__).resolve().parents[2] / "data"  # present in a source checkout only
INCIDENTS_FILE = DATA_DIR / "incidents.jsonl"

_NonBlank = Annotated[str, Field(min_length=1, pattern=r"\S")]


class Incident(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", use_enum_values=False)

    id: Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
    origin: Origin
    title: _NonBlank
    summary: _NonBlank
    date: Annotated[str, Field(pattern=r"^\d{4}-\d{2}(-\d{2})?$")] | None = None  # YYYY-MM-DD or YYYY-MM
    system: System
    harm_domains: Annotated[tuple[HarmDomain, ...], Field(min_length=1)]
    harm_types: Annotated[tuple[HarmType, ...], Field(min_length=1)]
    entity: Entity
    intent: Intent
    timing: Timing
    trigger: Trigger
    actionable: bool
    sources: tuple[AnyHttpUrl, ...] = ()
    aiid_id: Annotated[int, Field(gt=0)] | None = None
    aiaaic_id: Annotated[str, Field(pattern=r"^AIAAIC\d{4}$")] | None = None
    regulations: tuple[_NonBlank, ...] = ()

    @model_validator(mode="after")
    def _origin_rules(self) -> Self:
        if self.origin is Origin.REAL and not self.sources:
            raise ValueError("a real incident needs at least one source URL")
        if self.origin is Origin.ARTIFICIAL and not self.regulations:
            raise ValueError("an artificial incident needs at least one regulation or standard")
        if self.origin is Origin.ARTIFICIAL and (self.aiid_id is not None or self.aiaaic_id is not None):
            raise ValueError("an artificial incident has no incident-database record")
        if self.date is not None:
            datetime.date.fromisoformat(self.date if len(self.date) == 10 else f"{self.date}-01")
        for name in ("harm_domains", "harm_types", "sources", "regulations"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} has duplicate entries")
        return self


class IncidentFileError(ValueError):
    """A JSONL incident file could not be read; the message names the file and line."""


def load_incidents(path: str | Path = INCIDENTS_FILE) -> list[Incident]:
    """Read a JSONL incident file. Blank lines are skipped; ids must be unique."""
    path = Path(path)
    incidents: list[Incident] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            incident = Incident.model_validate(json.loads(line))
        except (json.JSONDecodeError, ValidationError) as error:
            raise IncidentFileError(f"{path}:{number}: {error}") from error
        if incident.id in seen:
            raise IncidentFileError(f"{path}:{number}: duplicate id {incident.id!r}")
        seen.add(incident.id)
        incidents.append(incident)
    return incidents


def dump_incidents(incidents: Iterable[Incident], path: str | Path) -> None:
    """Write incidents as JSONL, one compact record per line, in the order given."""
    lines = [incident.model_dump_json(exclude_defaults=True) for incident in incidents]
    Path(path).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
