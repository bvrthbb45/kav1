from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    full_name: str
    unit: str


class ItemOut(BaseModel):
    qr_id: str
    name: str
    current_status: str
    category: str = ""
    # Who holds the item (borrowed/issued), from its latest action.
    holder_user_id: Optional[str] = None
    # Device time (epoch ms) of the item's latest action.
    last_action_at: Optional[int] = None


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


class CategoryOut(BaseModel):
    name: str
    target_qty: Optional[int] = None


class HistoryOut(BaseModel):
    """A past action, so tablets can show item history and soldier cards."""

    tx_id: str
    qr_id: str
    user_id: str
    action_type: str
    timestamp: int


class PullResponse(BaseModel):
    success: bool
    message: str
    server_time: int
    items: List[ItemOut]
    users: List[UserOut]
    categories: List[CategoryOut] = []
    history: List[HistoryOut] = []


class UserIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    full_name: str = Field(min_length=1, max_length=200)
    unit: str = ""


class ItemIn(BaseModel):
    qr_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)
    # None keeps the current type (older tablets do not send it).
    category: Optional[str] = Field(default=None, max_length=200)


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    target_qty: Optional[int] = Field(default=None, ge=0, le=1_000_000)


class UpsertResponse(BaseModel):
    success: bool
    message: str
    count: int
