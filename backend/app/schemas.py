from pydantic import BaseModel, Field
from typing import Optional, Dict


class VisitorCreate(BaseModel):
    name: str
    visitorid: str
    properties: Optional[Dict] = Field(default_factory=dict)

    class Config:
        orm_mode = True


class VisitorBase(VisitorCreate):
    dbid: int
    inside: bool


class VisitorUpdate(BaseModel):
    name: Optional[str] = None
    visitorid: Optional[str] = None
    # None = "leave the properties alone". (It used to default to {}, so a
    # rename-only update silently wiped every property of the visitor.)
    properties: Optional[Dict] = None

    class Config:
        orm_mode = True
