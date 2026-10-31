from beanie import Document
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


# ============================================
# MODULE PERMISSION MODEL
# ============================================

class ModulePermission(BaseModel):

    module_name: str

    read: bool = False
    write: bool = False
    delete: bool = False
    export: bool = False
    approve: bool = False


# ============================================
# ROLE MODEL
# ============================================

class Role(Document):

    tenant_id: UUID

    role_name: str

    is_system_role: bool = False

    default_for_new_employees: bool = False

    modules: List[ModulePermission] = []

    total_permissions: int = 0

    status: str = "Active"

    created_by: UUID

    created_at: datetime = datetime.utcnow()

    updated_at: Optional[datetime] = None

    class Settings:
        name = "roles"