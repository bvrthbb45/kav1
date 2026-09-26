import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import messages
from .database import init_db
from .routers import admin, sync

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Warehouse Inventory Sync", lifespan=lifespan)
app.include_router(sync.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return {"success": True, "message": messages.HEALTH_OK}


# Every error that reaches a client carries a Hebrew "message" field.


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": messages.VALIDATION_ERROR,
            "details": exc.errors(),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException):
    message = {
        404: messages.NOT_FOUND,
        405: messages.METHOD_NOT_ALLOWED,
    }.get(exc.status_code, messages.REQUEST_FAILED)
    return JSONResponse(
        status_code=exc.status_code, content={"success": False, "message": message}
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, _exc: Exception):
    log.exception("unhandled server error")
    return JSONResponse(
        status_code=500, content={"success": False, "message": messages.INTERNAL_ERROR}
    )
