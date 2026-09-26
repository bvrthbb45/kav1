"""Entry point: python main.py  (serves on 0.0.0.0:8000 by default)."""

import logging

import uvicorn

from app.config import HOST, PORT
from app.main import app

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    uvicorn.run(app, host=HOST, port=PORT)
