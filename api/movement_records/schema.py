from datetime import datetime
from typing import Optional
from ninja import Schema


class MovementRecordSchema(Schema):
    farm_id: int
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    from_unit_id: Optional[int] = None
    to_unit_id: Optional[int] = None
    move_date: datetime
    reason: Optional[str] = None


class SalesRecordSchema(Schema):
    farm_id: int
    animal_id: int
    buyer_name: str
    price: float
    sale_date: datetime
    reason: Optional[str] = None
    notes: str


class MoveSchemaV2(Schema):
    farm_id: int
    animal_id: Optional[int] = None
    group_id: Optional[int] = None
    from_housing_unit_id: int
    to_housing_unit_id: int
    move_date: datetime
    reason: Optional[str] = None
