from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr
from datetime import date
from pydantic import model_validator

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
    
class AnimalsSchemaIn(Schema):
    status: Literal["active", "pregnant","lactating", "sick", "quarantine", "sold", "dead"]
    gender: Literal["male", "female"]    
    source: Literal["born","purchased","imported"]

    farm_id: int
    unit_id: int
    tag_id: str
    species_id: int
    breed_id: int 

    dob: Optional[date] = None
    estimated_age_months: Optional[int] = None
    mother_id: Optional[int] = None

    health_status: Literal["healthy", "sick", "recovering", "at_risk"]

    is_pregnant: bool
    is_lactating: bool
    is_quarantine: bool
    is_active: bool

    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_birth_rules(self):
        if self.source == "born":
            if not self.mother_id:
                raise ValueError("mother_id is required when source is 'born'")
            if not self.dob:
                raise ValueError("dob is required when source is 'born'")
        return self