"""Download an AI Incident Database snapshot and list recent, possibly benchmarkable candidates.

    uv run python scripts/fetch_aiid.py                       # latest known snapshot
    uv run python scripts/fetch_aiid.py --since 2024-01-01

The snapshot (about 120 MB) is cached in .cache/aiid/ and never committed. The output,
.cache/aiid/candidates.jsonl, is a review list, not benchmark data: each candidate is
read by a person, and the ones kept are written to data/incidents.jsonl with our own
summary and labels. AIID data is CC BY-SA 4.0; report article text is not used.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "aiid"
SNAPSHOT_BASE = "https://pub-72b2b2fc36ec423189843747af98f80e.r2.dev"
DEFAULT_SNAPSHOT = "backup-20261123100712.tar.bz2"  # see https://incidentdatabase.ai/research/snapshots/
CSV_DIR = "mongodump_full_snapshot"

# Systems a harness can reproduce: chat models, agents with tools, robots and vehicles.
SYSTEM_TERMS = re.compile(
    r"\b(chat ?bot|chatgpt|gpt-?\d|openai|claude|anthropic|gemini|bard|copilot|grok|llama|mistral|deepseek|"
    r"character\.ai|replika|llm|language model|ai assistant|voice assistant|ai agent|agentic|agents?\b|"
    r"autonomous|self-driving|robotaxi|waymo|cruise|tesla|autopilot|fsd|robot\w*|humanoid|drone|"
    r"coding|replit|cursor|codex|devin|database|deleted|prompt injection|jailbreak\w*|tool)\b",
    re.IGNORECASE,
)
# Mostly people misusing AI as a tool (deepfakes, voice-clone scams), not the system's own action.
HUMAN_MISUSE = re.compile(r"\b(deepfake|voice clon\w*|scam\w*|impersonat\w*|nudify|non-?consensual)\b", re.IGNORECASE)


def download(name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / name
    if not archive.exists():
        print(f"Downloading {name} ...", file=sys.stderr)
        urllib.request.urlretrieve(f"{SNAPSHOT_BASE}/{name}", archive)  # noqa: S310 - fixed https host
    if not (CACHE / CSV_DIR / "incidents.csv").exists():
        with tarfile.open(archive, "r:bz2") as tar:
            members = [m for m in tar.getmembers() if m.name.endswith((".csv", "license.txt"))]
            tar.extractall(CACHE, members=members, filter="data")
    return CACHE / CSV_DIR


def read_csv(path: Path) -> list[dict[str, str]]:
    csv.field_size_limit(sys.maxsize)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def candidates(snapshot: Path, since: str) -> list[dict[str, object]]:
    mit = {row["Incident ID"]: row for row in read_csv(snapshot / "classifications_MIT.csv")}
    urls = {row["report_number"]: row["url"] for row in read_csv(snapshot / "reports.csv")}
    found = []
    for row in read_csv(snapshot / "incidents.csv"):
        if row["date"] < since:
            continue
        text = f"{row['title']} {row['description']}"
        label = mit.get(row["incident_id"], {})
        system_hit = SYSTEM_TERMS.search(text)
        misuse = label.get("Entity") == "Human" and not re.search(r"jailbreak|prompt injection", text, re.I)
        if not system_hit or misuse or HUMAN_MISUSE.search(text):
            continue
        reports = json.loads(row["reports"] or "[]")
        found.append(
            {
                "aiid_id": int(row["incident_id"]),
                "date": row["date"],
                "title": row["title"],
                "description": row["description"],
                "mit": {key: label.get(key) for key in ("Risk Domain", "Risk Subdomain", "Entity", "Intent", "Timing")},
                "sources": [urls[str(number)] for number in reports if urls.get(str(number))][:3],
            }
        )
    return sorted(found, key=lambda item: str(item["date"]), reverse=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", default=DEFAULT_SNAPSHOT, help="snapshot archive name")
    parser.add_argument("--since", default="2024-01-01", help="earliest incident date (YYYY-MM-DD)")
    arguments = parser.parse_args()
    rows = candidates(download(arguments.snapshot), arguments.since)
    out = CACHE / "candidates.jsonl"
    out.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    print(f"{len(rows)} candidates since {arguments.since} -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
