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
    
class FeedIssuanceRecordSchema(Schema):
    farm_id: int
    target_type: Literal["animal", "group"]
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    feed_inventory_id: int
    quantity_issued: float
    issue_date: date
    notes: Optional[str] = None
    
class FeedConfirmationRecordSchema(Schema):
    farm_id: int
    status: Literal["confirmed", "variance_detected"]
    issuance_id: int
    actual_used_quantity: float
    confirmation_date: date
    notes: Optional[str] = None

class FeedPlanSchemaV2(Schema):
    farm_id: int
    plan_type: Literal["species", "group"]
    species_id: Optional[int] = None
    livestock_species_id: Optional[int] = None
    group_id: Optional[int] = None
    feed_inventory_id: int
    daily_feed_quantity: float
    unit: str
    start_date: date
    end_date: Optional[date] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# v3 schemas — Feed Master Data Framework
# ---------------------------------------------------------------------------

class FeedUnitSchemaIn(Schema):
    name: str
    abbreviation: Optional[str] = None


class FeedTypeSchemaIn(Schema):
    name: str
    category_id: int
    species_ids: List[int]
    description: Optional[str] = None
    manufacturer: Optional[str] = None


class FeedTypeUpdateSchemaIn(Schema):
    name: Optional[str] = None
    category_id: Optional[int] = None
    species_ids: Optional[List[int]] = None
    description: Optional[str] = None
    manufacturer: Optional[str] = None
    is_active: Optional[bool] = None


class FeedInventorySchemaV3(Schema):
    farm_id: int
    feed_type_id: int
    quantity_available: float
    feed_unit_id: int
    reorder_level: Optional[float] = None