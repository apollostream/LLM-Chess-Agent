"""FastAPI backend for the Chess Imbalances App."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import analysis, narrative, agent


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Chess Imbalances API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(narrative.router)
app.include_router(agent.router)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
