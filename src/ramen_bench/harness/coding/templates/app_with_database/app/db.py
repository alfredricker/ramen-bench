"""Database connection, configured by DATABASE_URL in the environment or in .env."""

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def database_url() -> str:
    if "DATABASE_URL" in os.environ:
        return os.environ["DATABASE_URL"]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "DATABASE_URL":
                return value.strip()
    raise RuntimeError("DATABASE_URL is not set")


def connect() -> sqlite3.Connection:
    url = database_url()
    if not url.startswith("sqlite:///"):
        raise RuntimeError(f"unsupported DATABASE_URL {url!r}")
    conn = sqlite3.connect(url.removeprefix("sqlite:///"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
