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
    
class InseminationRecordSchema(Schema):
    farm_id: int
    animal_id: int
    service_date: date
    method: Literal["natural", "artificial"] 
    sire_reference: Optional[str] = None
    technician_name: Optional[str] = None
    notes: Optional[str] = None
    
    @model_validator(mode="after")
    def check_method_fields(self):
        if self.method == "artificial" and not self.technician_name:
            raise ValueError("technician_name is required for artificial insemination")

        return self
    
class PregnancyRecordIn(Schema):
    farm_id: int
    animal_id: int
    insemination_id: Optional[int] = None
    check_date: date
    result: Literal["pregnant", "not_pregnant"]
    expected_delivery_date: Optional[date] = None
    notes: Optional[str] = None

    @validator("result")
    def validate_result(cls, value):
        allowed = ["pregnant", "not_pregnant"]
        if value not in allowed:
            raise ValueError(f"Result must be one of {allowed}")
        return value

    @validator("expected_delivery_date", always=True)
    def validate_expected_delivery(cls, value, values):
        if values.get("result") == "pregnant" and not value:
            raise ValueError("expected_delivery_date is required if result is pregnant")
        return value