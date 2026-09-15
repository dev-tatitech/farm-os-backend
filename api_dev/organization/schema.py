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
    meta: Optional[Any] = None
    
class OranizationSchemaIn(Schema):
    name: str
    industry_id: Optional[int] = None
    country_id: int
    state_region_id: int
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    client_request_id: Optional[str] = None
    
class FarmInSchema(Schema):
    client_request_id: Optional[str] = None
    organization_id: UUID
    name: str
    country_id: int
    state_region_id: int
    city: str
    location_address: str
    latitude: Optional[str] = None
    longitude: Optional[str] = None
    farm_type_id: int
    is_primary: bool
    
