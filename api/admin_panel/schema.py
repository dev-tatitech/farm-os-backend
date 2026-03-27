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