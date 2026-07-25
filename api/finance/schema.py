from ninja import Schema
from typing import Optional, Any, Literal
from datetime import date


class ListResponseSchema(Schema):
    success: bool
    message: str
    data: Any
    num_pages: int
    current_page: int
    total_items: int
    has_next: bool
    has_previous: bool


class APIResponse(Schema):
    success: bool
    message: str
    data: Any


class TransactionSchemaIn(Schema):
    farm_id: int
    type: Literal["expense", "income"]
    category_id: int
    amount: float
    currency: str = "NGN"
    transaction_date: date
    description: Optional[str] = ""
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    payment_status: Literal["paid", "pending", "partial"] = "paid"
    payment_method: Optional[str] = None
    transaction_reference: Optional[str] = None
    notes: Optional[str] = None
