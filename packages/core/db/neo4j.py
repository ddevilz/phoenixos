import os
from collections.abc import AsyncGenerator

from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession

_driver: AsyncDriver | None = None


async def init_driver() -> None:
    """Call from FastAPI lifespan startup (T08 wires this)."""
    global _driver
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    auth_env = os.getenv("NEO4J_AUTH", "none")
    if auth_env == "none":
        auth: tuple[str, str] | None = None
    else:
        user, password = auth_env.split("/", 1)
        auth = (user, password)
    _driver = AsyncGraphDatabase.driver(uri, auth=auth)


async def close_driver() -> None:
    """Call from FastAPI lifespan shutdown."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async generator for FastAPI Depends() injection."""
    assert _driver is not None, "Driver not initialized — init_driver() must run first"
    async with _driver.session() as session:
        yield session
