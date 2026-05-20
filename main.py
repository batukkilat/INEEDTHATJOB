import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI

import utils.logging  # noqa: F401 — configures structlog on import
from config import settings
from db.database import create_db_and_tables
from web.app import create_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    create_db_and_tables()
    yield


app = create_app(lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
