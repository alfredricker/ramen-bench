"""Customer accounts."""

import sqlite3


class DuplicateEmail(Exception):
    pass


def normalise_email(email: str) -> str:
    return email.strip().lower()


def create_user(conn: sqlite3.Connection, email: str, name: str) -> int:
    try:
        cursor = conn.execute(
            "INSERT INTO users (email, name) VALUES (?, ?)", (normalise_email(email), name.strip())
        )
    except sqlite3.IntegrityError as error:
        raise DuplicateEmail(email) from error
    conn.commit()
    return cursor.lastrowid


def get_user(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE email = ?", (normalise_email(email),)).fetchone()
