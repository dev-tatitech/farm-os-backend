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
    
class TreatmentRecordSchema(Schema):
    farm_id: int
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    diagnosis: str
    treatment: str
    severity: Literal["mild","moderate","severe"]
    treatment_date: date
    next_follow_up_date: Optional[date] = None
    notes: Optional[str] = None

    # Pharmacy-linked treatment workflow (all optional - a treatment can
    # still be recorded as a plain clinical note without drawing from
    # inventory, same as before this was added).
    drug_id: Optional[int] = None
    drug_batch_id: Optional[int] = None
    quantity_administered: Optional[float] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    duration_days: Optional[int] = None
    administration_route: Optional[Literal["oral", "injection", "topical", "other"]] = None
    administered_by_id: Optional[int] = None
    prescribed_by_id: Optional[int] = None
    next_dose_date: Optional[date] = None
    withdrawal_end_date: Optional[date] = None

    @model_validator(mode="after")
    def check_animal_or_group(self):
        if not self.animal_id and not self.group_id:
            raise ValueError("At least one of animal_id or group_id must be provided")
        return self
    
class VaccinationRecordSchema(Schema):
    farm_id: int
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    vaccine_name: str
    date_given: date
    next_due_date: Optional[date] = None
    notes: Optional[str] = None
    
class QuarantineRecordSchema(Schema):
    farm_id: int
    animal_id: int
    reason: str
    start_date: date
    notes: Optional[str] = None

class MortalityRecordSchema(Schema):
    farm_id: int
    animal_id: int
    cause: str
    death_date: date
    notes: Optional[str] = None


class ExternalMedicationSchemaIn(Schema):
    farm_id: int
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    diagnosis: str
    treatment_date: date
    severity: Literal["mild", "moderate", "severe"] = "mild"

    drug_id: Optional[int] = None
    external_drug_name: str
    quantity_administered: float
    unit: str
    external_unit_cost: float
    external_source: str
    external_reason: str
    notes: Optional[str] = None

    @model_validator(mode="after")
    def check_animal_or_group(self):
        if not self.animal_id and not self.group_id:
            raise ValueError("At least one of animal_id or group_id must be provided")
        return self