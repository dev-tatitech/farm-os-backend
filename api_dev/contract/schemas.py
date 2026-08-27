from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from ninja import Schema


class OrgPatchIn(Schema):
    name: Optional[str] = None
    status: Optional[str] = None
    client_request_id: Optional[str] = None


class FarmPatchIn(Schema):
    name: Optional[str] = None
    city: Optional[str] = None
    location_address: Optional[str] = None
    status: Optional[str] = None
    is_primary: Optional[bool] = None
    client_request_id: Optional[str] = None


class AnimalCreateIn(Schema):
    farm_id: int
    tag_id: str
    gender: str
    source_type: str
    status: str = "active"
    livestock_species_id: Optional[int] = None
    livestock_breed_id: Optional[int] = None
    housing_unit_id: Optional[int] = None
    dob: Optional[date] = None
    estimated_age_months: Optional[int] = None
    mother_id: Optional[int] = None
    notes: Optional[str] = None
    client_request_id: Optional[str] = None


class TaskCreateIn(Schema):
    farm_id: int
    task_type: str
    title: str
    description: str = ""
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    due_at: Optional[datetime] = None
    priority: str = "normal"
    assignee_id: Optional[UUID] = None
    client_request_id: Optional[str] = None


class TaskAssignIn(Schema):
    assignee_id: UUID
    client_request_id: Optional[str] = None


class TaskCancelIn(Schema):
    reason: str = ""
    client_request_id: Optional[str] = None


class TaskCompleteIn(Schema):
    notes: Optional[str] = None
    evidence: Optional[str] = None
    client_request_id: Optional[str] = None
    vaccine_name: Optional[str] = None
    date_given: Optional[date] = None
    next_due_date: Optional[date] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    severity: Optional[str] = None
    treatment_date: Optional[date] = None
    next_follow_up_date: Optional[date] = None
    drug_id: Optional[int] = None
    drug_batch_id: Optional[int] = None
    quantity_administered: Optional[float] = None
    feed_inventory_id: Optional[int] = None
    feed_batch_id: Optional[int] = None
    quantity_issued: Optional[float] = None
    target_type: Optional[str] = None
    issue_date: Optional[date] = None
    feeding_period: Optional[str] = None
    allocation_method: Optional[str] = None
    buyer_name: Optional[str] = None
    price: Optional[float] = None
    sale_date: Optional[datetime] = None
    override_reason: Optional[str] = None
    reason: Optional[str] = None
    to_housing_unit_id: Optional[int] = None
    to_unit_id: Optional[int] = None
    move_date: Optional[datetime] = None
    symptoms: Optional[str] = None
    observed_at: Optional[datetime] = None
    case_id: Optional[int] = None
    payload: Optional[Any] = None


class ScheduleCreateIn(Schema):
    farm_id: int
    task_type: str
    title: str
    description: str = ""
    recurrence: str = "once"
    next_run_at: datetime
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    assignee_id: Optional[UUID] = None
    template_payload: Optional[Any] = None
    run_now: bool = False
    client_request_id: Optional[str] = None


class ObservationIn(Schema):
    farm_id: int
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    case_id: Optional[int] = None
    symptoms: str
    severity: str = "mild"
    observed_at: Optional[datetime] = None
    create_task: bool = False
    assignee_id: Optional[UUID] = None
    client_request_id: Optional[str] = None


class HealthCaseIn(Schema):
    farm_id: int
    title: str
    notes: str = ""
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    client_request_id: Optional[str] = None


class HealthCaseCloseIn(Schema):
    notes: str = ""
    client_request_id: Optional[str] = None
