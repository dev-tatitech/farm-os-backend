from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr, Field
from datetime import date
from typing_extensions import Annotated

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
    
class RoleIn(Schema):
    name: str
    description: str
    
class RoleUpdateSchema(Schema):
    role_id: int
    name: Optional[str] = None
    description: Optional[str] = None
    
class NewUserIn(Schema):
    email: EmailStr


OTP = Annotated[str, Field(min_length=6, max_length=6)]
class NewUserActivateAccountIn(Schema):
    email: EmailStr
    otp: OTP
    password: str
    confirm_password: str
    
class NewUserRoleIn(Schema):
    role_id: int
    farm_id:int
    user_id: UUID
    
class RolePermissionIn(Schema):
    role_id: int
    permission_id: int