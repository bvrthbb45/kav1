from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    full_name: str
    unit: str


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    qr_id: str
    name: str
    current_status: str


class PendingTransaction(BaseModel):
    tx_id: str = Field(min_length=1, max_length=64)
    qr_id: str = Field(min_length=1, max_length=128)
    user_id: str = Field(min_length=1, max_length=64)
    action_type: str
    # Epoch milliseconds (UTC) as recorded on the device.
    timestamp: int = Field(ge=0, le=253402300799999)


class PushRequest(BaseModel):
    device_id: Optional[str] = None
    transactions: List[PendingTransaction]


class TxResult(BaseModel):
    tx_id: str
    accepted: bool
    message: str


class PushResponse(BaseModel):
    success: bool
    message: str
    accepted: List[str]
    rejected: List[TxResult]


class PullResponse(BaseModel):
    success: bool
    message: str
    server_time: int
    items: List[ItemOut]
    users: List[UserOut]


class UserIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    unit: str = ""


class ItemIn(BaseModel):
    qr_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)


class UpsertResponse(BaseModel):
    success: bool
    message: str
    count: int
