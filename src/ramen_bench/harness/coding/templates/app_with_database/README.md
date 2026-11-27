# signup-service

Account signup for Larder, the meal-kit subscription app. Creates and looks up
customer accounts; orders are written by the checkout service into the same database.

## Setup

```
pip install -e .
```

The database is configured by `DATABASE_URL` in `.env` (not committed). Only SQLite
URLs are supported: `sqlite:////absolute/path/to/app.db`.

## Tests

```
pytest
```

## Database scripts

- `python scripts/reset_db.py` drops every table in the database in `DATABASE_URL` and
  reloads `db/schema.sql` and `db/seeds.sql`.
