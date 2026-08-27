from ninja import Schema
from typing import Optional, Any, Literal, List
from uuid import UUID
from pydantic import EmailStr
from datetime import date

class APIResponse(Schema):
    success: bool
    message: str
    data: Any
    