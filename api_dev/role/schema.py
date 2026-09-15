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
    meta: Optional[Any] = None
    
class RoleIn(Schema):
    name: str
    description: str = ""
    web_access: bool = False
    mobile_access: bool = False
    client_request_id: Optional[str] = None
    
class RoleUpdateSchema(Schema):
    active: Optional[bool] = None
    web_access: Optional[bool] = None
    mobile_access: Optional[bool] = None
    client_request_id: Optional[str] = None
    role_id: int
    name: Optional[str] = None
    description: Optional[str] = None
    
class NewUserIn(Schema):
    email: EmailStr
    client_request_id: Optional[str] = None


OTP = Annotated[str, Field(min_length=6, max_length=6)]
class NewUserActivateAccountIn(Schema):
    email: EmailStr
    otp: OTP
    password: str
    confirm_password: str
    
class NewUserRoleIn(Schema):
    client_request_id: Optional[str] = None
    role_id: int
    farm_id:int
    user_id: UUID

class UserRolePatchIn(Schema):
    client_request_id: Optional[str] = None
    farm_id: Optional[int] = None
    role_id: Optional[int] = None
    
class RolePermissionIn(Schema):
    client_request_id: Optional[str] = None
    role_id: int
    permission_ids: List[int]
