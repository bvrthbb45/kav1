"""Endpoints for loading users and items into the server (bulk upsert)."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import messages, schemas, services
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/users", response_model=schemas.UpsertResponse)
def upsert_users(users: List[schemas.UserIn], db: Session = Depends(get_db)):
    count = services.upsert_users(db, users)
    return schemas.UpsertResponse(
        success=True, message=messages.UPSERT_OK.format(count=count), count=count
    )


@router.post("/items", response_model=schemas.UpsertResponse)
def upsert_items(items: List[schemas.ItemIn], db: Session = Depends(get_db)):
    count = services.upsert_items(db, items)
    return schemas.UpsertResponse(
        success=True, message=messages.UPSERT_OK.format(count=count), count=count
    )
