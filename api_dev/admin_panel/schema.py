from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr
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
    
class SpeciesSchemaIn(Schema):
    name: str
    
class SpecieUpdateSchema(Schema):
    species_id: int
    name: str
    
class BreedSchemaIn(Schema):
    species_id: int
    name: str
    
class BreedUpdateSchema(Schema):
    breed_id: int
    species_id: Optional[int] = None
    name: Optional[str] = None
    
class UnitTypeSchemaIn(Schema):
    name: str


class UnitTypeUpdateSchema(Schema):
    unit_type_id: int
    name: str


# ─── Livestock Master Data Schemas ───────────────────────────────────────────

class LivestockBreedIn(Schema):
    species_id: int
    name: str
    description: Optional[str] = None
    origin: Optional[str] = None


class LivestockBreedUpdate(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    origin: Optional[str] = None
    is_active: Optional[bool] = None


class FarmHousingUnitIn(Schema):
    name: str
    capacity: Optional[int] = None
    allowed_species_ids: Optional[List[int]] = None
    location: Optional[str] = None


class FarmHousingUnitUpdate(Schema):
    name: Optional[str] = None
    capacity: Optional[int] = None
    allowed_species_ids: Optional[List[int]] = None
    location: Optional[str] = None
    status: Optional[Literal["active", "inactive"]] = None


# ─── Contact Enquiry Schemas ──────────────────────────────────────────────────

class ContactEnquiryIn(Schema):
    full_name: str
    farm_name: Optional[str] = None
    email: EmailStr
    phone: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    farm_type: Optional[Literal[
        "livestock", "poultry", "fishery", "crop", "mixed_farming",
        "cooperative", "government", "ngo", "other"
    ]] = None
    farm_size: Optional[Literal["small", "medium", "large", "enterprise"]] = None
    record_method: Optional[Literal[
        "paper", "excel", "existing_software", "combination", "other"
    ]] = None
    modules_of_interest: Optional[List[str]] = None
    challenges: Optional[str] = None
    preferred_contact_method: Optional[Literal["phone", "email", "whatsapp"]] = None
    consultation_date: Optional[str] = None


class ContactEnquiryStatusUpdate(Schema):
    status: Literal["new", "in_review", "contacted", "converted", "closed"]
    notes: Optional[str] = None


# ─── Newsletter Subscription Schema ──────────────────────────────────────────

class NewsletterSubscribeIn(Schema):
    email: EmailStr