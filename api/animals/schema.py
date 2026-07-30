from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr
from datetime import date
from pydantic import model_validator
from datetime import datetime
from pydantic import validator

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
    
ENTRY_METHOD = Literal["born", "purchased", "imported", "transferred_in", "donated", "opening_record", "other"]


class AnimalsSchemaIn(Schema):
    status: Literal["active", "pregnant","lactating", "sick", "quarantine", "sold", "dead"]
    gender: Literal["male", "female"]
    source: ENTRY_METHOD
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

    @model_validator(mode="before")
    @classmethod
    def empty_strings_to_none(cls, values):
        optional_fields = {"dob", "estimated_age_months", "mother_id", "notes"}
        for field in optional_fields:
            if isinstance(values, dict) and values.get(field) == "":
                values[field] = None
        return values

    @model_validator(mode="after")
    def validate_source_rules(self):

        # Rule 1: Born
        if self.source == "born":
            if not self.mother_id:
                raise ValueError("mother_id is required when source is 'born'")
            if not self.dob:
                raise ValueError("dob is required when source is 'born'")

        # Rule 2: Purchased / Imported — age still required. Financial
        # details (purchase price, cost breakdown, etc.) are recorded
        # separately via the finance app's acquisition endpoint, not here.
        if self.source in ["purchased", "imported"]:
            if not self.dob and not self.estimated_age_months:
                raise ValueError(
                    "Either dob or estimated_age_months is required when source is purchased/imported"
                )

        return self
   
class AnimalsUpdateSchemaIn(Schema):
    status: Optional[Literal["active", "pregnant","lactating", "sick", "quarantine", "sold", "dead"]] = None
    gender: Optional[Literal["male", "female"]] = None
    source: Optional[Literal["born","purchased","imported"]] = None
    new_farm_id: Optional[int] = None
    unit_id: Optional[int] = None
    tag_id: Optional[str] = None
    species_id: Optional[int] = None
    breed_id: Optional[int] = None
    dob: Optional[date] = None
    estimated_age_months: Optional[int] = None
    mother_id: Optional[int] = None
    health_status: Optional[Literal["healthy", "sick", "recovering", "at_risk"]] = None
    is_pregnant: Optional[bool] = None
    is_lactating: Optional[bool] = None
    is_quarantine: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def empty_strings_to_none(cls, values):
        optional_fields = {
            "dob", "estimated_age_months", "mother_id", "notes",
            "status", "gender", "source", "farm_id", "unit_id",
            "tag_id", "species_id", "breed_id", "health_status",
            "is_pregnant", "is_lactating", "is_quarantine", "is_active",
        }
        for field in optional_fields:
            if isinstance(values, dict) and values.get(field) == "":
                values[field] = None
        return values

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
    
class AnimalWeightIn(Schema):
    farm_id: int
    animal_id: int
    weight: float
    date: date
    @validator("weight")
    def validate_weight(cls, value):
        if value <= 0:
            raise ValueError("Weight must be greater than 0")
        return value
    
# ─── v2 Schemas (Livestock Master Data) ──────────────────────────────────────

class AnimalsUpdateSchemaInV2(Schema):
    status: Optional[Literal["active", "pregnant", "lactating", "sick", "quarantine", "sold", "dead"]] = None
    gender: Optional[Literal["male", "female"]] = None
    source: Optional[Literal["born", "purchased", "imported"]] = None
    new_farm_id: Optional[int] = None
    tag_id: Optional[str] = None
    livestock_species_id: Optional[int] = None
    livestock_breed_id: Optional[int] = None
    housing_unit_id: Optional[int] = None
    dob: Optional[date] = None
    estimated_age_months: Optional[int] = None
    mother_id: Optional[int] = None
    health_status: Optional[Literal["healthy", "sick", "recovering", "at_risk"]] = None
    is_pregnant: Optional[bool] = None
    is_lactating: Optional[bool] = None
    is_quarantine: Optional[bool] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def empty_strings_to_none(cls, values):
        for field in list(values.keys()) if isinstance(values, dict) else []:
            if values.get(field) == "":
                values[field] = None
        return values

class AnimalsSchemaInV2(Schema):
    status: Literal["active", "pregnant", "lactating", "sick", "quarantine", "sold", "dead"]
    gender: Literal["male", "female"]
    source: ENTRY_METHOD
    farm_id: int
    tag_id: str
    livestock_species_id: int
    livestock_breed_id: int
    housing_unit_id: int
    dob: Optional[date] = None
    estimated_age_months: Optional[int] = None
    mother_id: Optional[int] = None
    health_status: Literal["healthy", "sick", "recovering", "at_risk"]
    is_pregnant: bool
    is_lactating: bool
    is_quarantine: bool
    is_active: bool
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def empty_strings_to_none(cls, values):
        optional_fields = {
            "dob", "estimated_age_months", "mother_id",
            "notes",
        }
        for field in optional_fields:
            if isinstance(values, dict) and values.get(field) == "":
                values[field] = None
        return values

    @model_validator(mode="after")
    def validate_source_rules(self):
        if self.source == "born":
            if not self.mother_id:
                raise ValueError("mother_id is required when source is 'born'")
            if not self.dob:
                raise ValueError("dob is required when source is 'born'")
        # Financial details (purchase price, cost breakdown, etc.) are
        # recorded separately via the finance app's acquisition endpoint,
        # not on the create call.
        if self.source in ["purchased", "imported"]:
            if not self.dob and not self.estimated_age_months:
                raise ValueError(
                    "Either dob or estimated_age_months is required for purchased/imported"
                )
        return self


class MilkRecordSchema(Schema):
    farm_id: int
    animal_id: int
    record_date: date
    session: Literal["morning", "evening"]
    quantity: float
    notes: Optional[str] = None


class AnimalAcquisitionSchemaIn(Schema):
    # Shared (purchased / imported)
    supplier: Optional[str] = None
    purchase_price: Optional[float] = None
    currency: str = "NGN"
    payment_status: Literal["paid", "pending", "partial"] = "paid"
    payment_method: Optional[str] = None
    transaction_reference: Optional[str] = None
    notes: Optional[str] = None

    # Purchased
    purchase_date: Optional[date] = None
    transportation_cost: Optional[float] = None
    veterinary_inspection_cost: Optional[float] = None
    other_acquisition_cost: Optional[float] = None

    # Imported
    country_of_origin: Optional[str] = None
    import_date: Optional[date] = None
    shipping_cost: Optional[float] = None
    customs_clearance_cost: Optional[float] = None
    quarantine_cost: Optional[float] = None
    veterinary_certification_cost: Optional[float] = None
    insurance_cost: Optional[float] = None
    other_import_cost: Optional[float] = None

    # Born on farm - internal production cost components
    production_cost_dam_feeding: Optional[float] = None
    production_cost_pregnancy_treatment: Optional[float] = None
    production_cost_delivery: Optional[float] = None
    production_cost_breeding: Optional[float] = None

    # Opening record
    estimated_opening_value: Optional[float] = None
    valuation_date: Optional[date] = None
    valuation_method: Optional[Literal["market_comparison", "book_value", "professional_appraisal", "owner_estimate"]] = None
    valuation_notes: Optional[str] = None