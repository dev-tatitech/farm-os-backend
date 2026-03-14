from ninja import Schema, ModelSchema
from datetime import datetime
from typing import List, Optional, Any, Literal
from enum import Enum
from uuid import UUID
from datetime import date
from pydantic import EmailStr, Field
from typing_extensions import Annotated

PhoneNumber = Annotated[str, Field(min_length=11, max_length=11)]
class NewAccountSchema(Schema):
    email: EmailStr
    password: str
    confirm_password: str


class ErrorResponse(Schema):
    success: bool
    message: str
    error_code: Optional[str] = None
    data: Optional[None] = None


class Error_out(Schema):
    status: str
    message: str


class LoginSchema(Schema):
    email: EmailStr
    password: str


class APIResponse(Schema):
    success: bool
    message: str
    data: Any


OTP = Annotated[str, Field(min_length=6, max_length=6)]
class EmailValidationSchema(Schema):
    otp: OTP

class ResendOtpSchema(Schema):
    email: EmailStr

class NewUserSchema(Schema):
    email: EmailStr
    passwoard: str
   
    
class AccountActivationSchema(Schema):
    email: EmailStr
    otp: str
    password:str
    confirm_password:str
 
class ListResponseSchema(Schema):
    success: bool
    message: str
    data: List[Any]
    num_pages: int
    current_page: int
    total_items: int
    has_next: bool
    has_previous: bool

   
class AccountUpdateSchema(Schema):
    account_id: UUID
    role: Optional[List[UUID]]= None
    account_status:Optional[Literal["Active", "Suspended","Deleted"]]=None
    
TransactionPin = Annotated[str, Field(min_length=6, max_length=6)]

class TransactionPinSchema(Schema):
    otp: TransactionPin
    new_pin: TransactionPin
    confirm_pin: TransactionPin
    
    

class Region_in(Schema):
    id: int
    name: str


class Region(Schema):
    id: int
    name: str


class RegionListResponse(Schema):
    success: bool
    message: str
    data: List[Region]

class StateSchema(Schema):
    id: int
    region: str
    name: str


class StateListResponse(Schema):
    success: bool
    message: str
    data: List[StateSchema]


class LgaSchema(Schema):
    id: int
    region: str
    state: str
    name: str

    class Config:
        orm_mode = True


class LGAListResponse(Schema):
    success: bool
    message: str
    data: List[LgaSchema]

class AccountInfoSchema(Schema):
    full_name: str
    phone_number:PhoneNumber
    date_of_birth: date
    nin_number:PhoneNumber
    bvn_number:PhoneNumber
    region_id: int
    state_id: int
    lga_id: int
    contact_address: str
    
class AccountInfoUpdate(Schema):
    full_name: Optional[str] =None
    phone_number:Optional[PhoneNumber] = None
    date_of_birth: Optional[date] = None
    nin_number: Optional[PhoneNumber] = None
    bvn_number: Optional[PhoneNumber] = None
    region_id: Optional[int] = None
    state_id:  Optional[int] = None
    lga_id: Optional[int] = None
    contact_address: Optional[str] = None
    
class NextOfKinSchema(Schema):
    relationship_id: int
    full_name: str
    phone_number: PhoneNumber
    contact_address: str
    
class BusinessProfileSchema(Schema):
    business_name: str
    registration_number: str
    industry: Literal["agriculture", "trading","manufacturing", "technology", "retail", "services", "logistics", "construction", "other"]
    description: str
    description: str
    year_established: int
    address: str
    city: str
    phone: PhoneNumber
    email: EmailStr
    employees: int
    
    