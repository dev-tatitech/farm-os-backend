from ninja import Schema
from typing import Optional, Any, List
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


class DrugSchemaIn(Schema):
    name: str
    category_id: int
    active_ingredient: Optional[str] = None
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    strength_concentration: Optional[str] = None
    unit_of_measurement: str
    withdrawal_period_days: int = 0


class DrugBatchSchemaIn(Schema):
    farm_id: int
    drug_id: int
    batch_number: str
    quantity_received: float
    purchase_unit: Optional[str] = None
    purchase_price: float
    supplier: Optional[str] = None
    purchase_date: Optional[date] = None
    manufacturing_date: Optional[date] = None
    expiry_date: date
    storage_location: Optional[str] = None
    minimum_stock_level: Optional[float] = None
