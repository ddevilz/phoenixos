import os
from collections.abc import AsyncGenerator

import aiosqlite

_DB_PATH = os.getenv("SQLITE_PATH", "./data/phoenix.db")


async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Async generator for FastAPI Depends() injection."""
    async with aiosqlite.connect(_DB_PATH) as db:
        yield db
