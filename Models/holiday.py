from beanie import Document
from datetime import date, datetime
from uuid import UUID
from typing import Optional

class Holiday(Document):
    name: str
    holiday_date: datetime   # ✅ use datetime (important)
    type: str = "National"
    region: str = "All India"
    description: Optional[str] = None

    tenant_id: Optional[UUID] = None  # ✅ multi-tenant support

    class Settings:
        name = "holidays"