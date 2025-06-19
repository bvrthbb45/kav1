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
    properties: Optional[Dict] = Field(default_factory=dict)

    class Config:
        orm_mode = True
