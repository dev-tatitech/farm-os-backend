from datetime import datetime
from typing import Optional,Literal
from ninja import Schema


class AlertSchema(Schema):
    farm_id: int
    alert_type: Literal["vaccination_due", "pregnancy_due", "feed_variance", "treatment_follow_up"]
    priority: Literal["critical", "warning", "info"]
    reference_table: Optional[str] = None
    reference_id: Optional[int] = None
    title: str
    message: str
    status: Literal["open", "resolved"]
    due_date: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    