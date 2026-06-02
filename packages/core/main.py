from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()  # must run before any module that reads env vars at import time

from fastapi import FastAPI  # noqa: E402

from core.api.evals import router as evals_router  # noqa: E402
from core.api.graph import router as graph_router  # noqa: E402
from core.api.webhooks import router as webhooks_router  # noqa: E402
from core.api.ws import router as ws_router  # noqa: E402
import core.db.neo4j as _neo4j_mod  # noqa: E402
from core.db.neo4j import close_driver, init_driver, init_schema  # noqa: E402
from core.db.sqlite import init_db  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_driver()
    await init_schema()
    yield
    await close_driver()


app = FastAPI(title="PhoenixOS", lifespan=lifespan)
app.include_router(webhooks_router)
app.include_router(graph_router)
app.include_router(ws_router)
app.include_router(evals_router)


@app.get("/health")
async def health():
    neo4j_status = "pending"
    driver = _neo4j_mod._driver
    if driver is not None:
        try:
            async with driver.session() as s:
                await s.run("RETURN 1")
            neo4j_status = "ok"
        except Exception:
            neo4j_status = "error"
    return {"status": "ok", "neo4j": neo4j_status}
