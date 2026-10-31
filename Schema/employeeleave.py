from pydantic import BaseModel
from datetime import date

class LeaveApplyRequest(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: str
    attachment: str | None = None