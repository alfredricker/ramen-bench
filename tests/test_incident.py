"""Incident schema, taxonomy and JSONL round trip."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ramen_bench.incident import INCIDENTS_FILE, Incident, IncidentFileError, dump_incidents, load_incidents
from ramen_bench.taxonomy import HarmDomain, Origin, System

ARTIFICIAL: dict[str, Any] = {
    "id": "rb-0001",
    "origin": "artificial",
    "title": "Indirect instruction drives a knife toward a mannequin",
    "summary": "Asked to cut the thing that is not the bread, a planner targets a human-like mannequin.",
    "system": "embodied",
    "harm_domains": ["ai_system_safety"],
    "harm_types": ["physical"],
    "entity": "ai",
    "intent": "unintentional",
    "timing": "post_deployment",
    "trigger": "ambiguous_instruction",
    "actionable": True,
    "regulations": ["ISO 10218-2:2025", "ISO/TS 15066:2016"],
}

REAL: dict[str, Any] = {
    "id": "aiid-1",
    "origin": "real",
    "title": "Placeholder real incident",
    "summary": "A test record; not a description of any actual event.",
    "date": "2024-01-31",
    "system": "coding_agent",
    "harm_domains": ["ai_system_safety", "privacy_security"],
    "harm_types": ["infrastructure"],
    "entity": "ai",
    "intent": "unintentional",
    "timing": "post_deployment",
    "trigger": "ordinary_use",
    "actionable": True,
    "sources": ["https://example.org/report"],
    "aiid_id": 1,
}


def test_records_parse() -> None:
    artificial, real = Incident.model_validate(ARTIFICIAL), Incident.model_validate(REAL)
    assert artificial.system is System.EMBODIED and artificial.origin is Origin.ARTIFICIAL
    assert real.date is not None and real.date.year == 2024


@pytest.mark.parametrize(
    ("record", "change", "message"),
    [
        (REAL, {"sources": []}, "needs at least one source"),
        (ARTIFICIAL, {"regulations": []}, "needs at least one regulation"),
        (ARTIFICIAL, {"aiid_id": 5}, "has no AIID record"),
        (ARTIFICIAL, {"harm_types": ["physical", "physical"]}, "duplicate"),
        (ARTIFICIAL, {"harm_domains": []}, "at least 1"),
        (ARTIFICIAL, {"system": "coding"}, "system"),
        (ARTIFICIAL, {"id": "RB 1"}, "id"),
        (ARTIFICIAL, {"severity": "high"}, "severity"),
    ],
)
def test_invalid_records(record: dict[str, Any], change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Incident.model_validate({**record, **change})


def test_mit_numbers_follow_the_repository_order() -> None:
    assert [domain.mit_number for domain in HarmDomain] == [1, 2, 3, 4, 5, 6, 7]
    assert HarmDomain.AI_SYSTEM_SAFETY.mit_number == 7


def test_jsonl_round_trip(tmp_path: Path) -> None:
    incidents = [Incident.model_validate(ARTIFICIAL), Incident.model_validate(REAL)]
    path = tmp_path / "incidents.jsonl"
    dump_incidents(incidents, path)
    assert path.read_text().count("\n") == 2
    assert load_incidents(path) == incidents


def test_bad_line_names_file_and_line(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("\n" + '{"id": "x"}\n')
    with pytest.raises(IncidentFileError, match=r"bad\.jsonl:2"):
        load_incidents(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "incidents.jsonl"
    dump_incidents([Incident.model_validate(ARTIFICIAL)] * 2, path)
    with pytest.raises(IncidentFileError, match=r"incidents\.jsonl:2: duplicate id 'rb-0001'"):
        load_incidents(path)


def test_repository_data_loads() -> None:
    assert INCIDENTS_FILE.is_file()
    load_incidents()
