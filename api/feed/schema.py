from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr
from datetime import date
from pydantic import model_validator, validator
from datetime import datetime

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
    
class FeedInventorySchema(Schema):
    farm_id: int
    feed_name: str
    quantity_available: float
    unit: str
    reorder_level: Optional[float] = None
    
class FeedPlanSchema(Schema):
    farm_id: int
    plan_type: Literal["species", "group"]
    species_id: Optional[int] = None
    group_id: Optional[int] = None
    feed_inventory_id: int
    daily_feed_quantity: float
    unit: str
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None