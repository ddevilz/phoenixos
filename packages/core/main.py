from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    # T08: call core.db.neo4j.init_driver() here
    yield
    # T08: call core.db.neo4j.close_driver() here


app = FastAPI(title="PhoenixOS", lifespan=lifespan)

# Router stubs — uncommented as T04, T09, T16, T23 land
# from core.api import webhooks, graph, evals, ws
# app.include_router(webhooks.router)
# app.include_router(graph.router)
# app.include_router(evals.router)
# app.include_router(ws.router)


@app.get("/health")
async def health():
    return {"status": "ok", "neo4j": "pending"}
