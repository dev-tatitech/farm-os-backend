from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr
from datetime import date
from pydantic import model_validator
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
    def validate_source_rules(self):

        # Rule 1: Born
        if self.source == "born":
            if not self.mother_id:
                raise ValueError("mother_id is required when source is 'born'")
            if not self.dob:
                raise ValueError("dob is required when source is 'born'")

        # Rule 2: Purchased / Imported
        if self.source in ["purchased", "imported"]:
            if not self.dob and not self.estimated_age_months:
                raise ValueError(
                    "Either dob or estimated_age_months is required when source is purchased/imported"
                )

        return self
    
class AnimalProfileAttributeSchemaIn(Schema):
    animal_id: int
    attribute_key: str
    attribute_value: str
    
class AnimalGroupSchemaIn(Schema):
    farm_id: int
    name: str
    group_type_id: int
    description: Optional[str] = None
    status: Optional[Literal["ACTIVE", "INACTIVE"]] = None
    
class AnimalGroupMemberSchemaIn(Schema):
    group_id: int
    animal_id: int
    status: Optional[Literal["ACTIVE", "REMOVED"]] = None
    
class UpdateAnimalGroupMemberSchemaIn(Schema):
    group_id: Optional[int] = None
    animal_id:  Optional[int] = None
    status: Optional[Literal["ACTIVE", "REMOVED"]] = None
    
class AnimalGroupUpdateSchema(Schema):
    name: Optional[str] = None
    group_type_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None
    farm_id: Optional[int] = None
    

class AnimalGroupMemberFilterSchema(Schema):
    group_id: Optional[int] = None
    animal_id: Optional[int] = None
    status: Optional[Literal["ACTIVE", "REMOVED"]] = None
    joined_after: Optional[datetime] = None
    joined_before: Optional[datetime] = None
    search: Optional[str] = None