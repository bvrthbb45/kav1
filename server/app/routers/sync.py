import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import messages, schemas, services
from ..database import get_db

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/push", response_model=schemas.PushResponse)
def push(request: schemas.PushRequest, db: Session = Depends(get_db)):
    try:
        result = services.push_transactions(db, request.transactions)
    except SQLAlchemyError:
        log.exception("push failed (device=%s)", request.device_id)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": messages.PUSH_DB_ERROR,
                "accepted": [],
                "rejected": [],
            },
        )
    log.info(
        "push from %s: %d accepted, %d rejected",
        request.device_id,
        len(result.accepted),
        len(result.rejected),
    )
    return result


@router.get("/pull", response_model=schemas.PullResponse)
def pull(db: Session = Depends(get_db)):
    return services.pull_state(db)
