from pydantic import BaseModel
from typing import List, Optional, Dict


# ============================================
# MODULE PERMISSION SCHEMA
# ============================================

class ModulePermissionSchema(BaseModel):
    module_name: str
    read: bool = False
    write: bool = False
    delete: bool = False
    export: bool = False
    approve: bool = False


# ============================================
# CREATE ROLE
# ============================================

class RoleCreate(BaseModel):

    role_name: str

    is_system_role: bool = False

    default_for_new_employees: bool = False

    modules: List[ModulePermissionSchema]


# ============================================
# UPDATE ROLE
# ============================================

class RoleUpdate(BaseModel):

    role_name: Optional[str] = None

    is_system_role: Optional[bool] = None

    default_for_new_employees: Optional[bool] = None

    modules: Optional[List[ModulePermissionSchema]] = None

    status: Optional[str] = None


# ============================================
# UPDATE PERMISSION (TOGGLE)
# ============================================

class PermissionToggle(BaseModel):
    module: str
    permission: str  # read, write, delete, export, approve
    value: bool


# ============================================
# ROLE RESPONSE
# ============================================

class RoleResponse(BaseModel):
    id: str
    role_name: str
    is_system_role: bool
    default_for_new_employees: bool
    total_permissions: int
    status: str
    modules: List[ModulePermissionSchema]
    created_at: str