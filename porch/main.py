"""Entry point for the BFF."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from . import api as api_module
from . import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)

app = FastAPI(title="TriAgent BFF")
app.include_router(api_module.router)
api_module.mount_spa(app)


def main() -> None:
    uvicorn.run(
        "porch.main:app",
        host="127.0.0.1",
        port=settings.DEFAULT_PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()
