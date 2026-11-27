import pytest
from app.db import connect


@pytest.fixture
def db():
    conn = connect()
    yield conn
    conn.close()
