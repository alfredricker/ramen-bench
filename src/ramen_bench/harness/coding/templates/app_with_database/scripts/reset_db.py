"""Drop every table in the database in DATABASE_URL and reload the schema and seed data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import ROOT, connect, database_url


def main() -> None:
    conn = connect()
    conn.execute("PRAGMA foreign_keys = OFF")
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for table in tables:
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    conn.executescript((ROOT / "db" / "schema.sql").read_text())
    conn.executescript((ROOT / "db" / "seeds.sql").read_text())
    conn.commit()
    print(f"Reset {database_url()}: dropped {len(tables)} tables, loaded schema and seeds.")


if __name__ == "__main__":
    main()
