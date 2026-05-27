from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from core.api.graph import router as graph_router
from core.api.webhooks import router as webhooks_router
from core.api.ws import router as ws_router
from core.db.neo4j import close_driver, init_driver, init_schema
from core.db.sqlite import init_db


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


@app.get("/health")
async def health():
    return {"status": "ok", "neo4j": "pending"}
