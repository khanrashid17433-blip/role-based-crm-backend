# ============================================
# PERMISSION HELPER UTILITY
# ============================================

from fastapi import HTTPException, status
from typing import List, Optional
from uuid import UUID

from Models.role import Role
from Models.tenant_user import TenantUser


# ============================================
# MODULE CONSTANTS
# ============================================

MODULES = {
    "dashboard": "Dashboard",
    "employees": "Employees",
    "attendance": "Attendance",
    "leaves": "Leave Management",
    "payroll": "Payroll",
    "recruitment": "Recruitment",
    "crm": "CRM",
    "billing": "Billing",
    "reports": "Reports & Analytics",
    "settings": "Settings",
    "projects": "Projects",
    "onboarding": "Onboarding"
}


# ============================================
# PERMISSION TYPES
# ============================================

class PermissionType:
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXPORT = "export"
    APPROVE = "approve"


# ============================================
# GET USER PERMISSIONS
# ============================================

async def get_user_permissions(user_id: UUID, tenant_id: UUID) -> dict:
    """
    Get all permissions for a user based on their role
    
    Returns:
        {
            "employees": {
                "read": True,
                "write": True,
                "delete": False,
                "export": True,
                "approve": False
            },
            ...
        }
    """
    # Find user
    user = await TenantUser.find_one(
        TenantUser.id == user_id,
        TenantUser.tenant_id == tenant_id
    )
    
    if not user:
        return {}
    
    # If user doesn't have role_id, return empty permissions
    if not hasattr(user, 'role_id') or not user.role_id:
        return {}
    
    # Find role
    role = await Role.find_one(
        Role.id == user.role_id,
        Role.tenant_id == tenant_id
    )
    
    if not role:
        return {}
    
    # Convert modules to permissions dict
    permissions = {}
    for module in role.modules:
        module_name = module.get("module_name")
        permissions[module_name] = {
            "read": module.get("read", False),
            "write": module.get("write", False),
            "delete": module.get("delete", False),
            "export": module.get("export", False),
            "approve": module.get("approve", False)
        }
    
    return permissions


# ============================================
# CHECK SINGLE PERMISSION
# ============================================

async def has_permission(
    user_id: UUID,
    tenant_id: UUID,
    module: str,
    permission_type: str
) -> bool:
    """
    Check if user has specific permission
    
    Args:
        user_id: User UUID
        tenant_id: Tenant UUID
        module: Module name (e.g., "employees", "payroll")
        permission_type: Permission type (read, write, delete, export, approve)
    
    Returns:
        True if user has permission, False otherwise
    """
    permissions = await get_user_permissions(user_id, tenant_id)
    
    if module not in permissions:
        return False
    
    return permissions[module].get(permission_type, False)


# ============================================
# REQUIRE PERMISSION DECORATOR
# ============================================

def require_permission(module: str, permission_type: str):
    """
    Decorator to check if user has required permission
    
    Usage:
        @require_permission("employees", "read")
        async def get_employees(...):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get("current_user")
            
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            user_id = UUID(current_user["sub"])
            tenant_id = UUID(current_user["tid"])
            
            # Check permission
            if not await has_permission(user_id, tenant_id, module, permission_type):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Required: {module}.{permission_type}"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# ============================================
# CHECK MULTIPLE PERMISSIONS
# ============================================

async def has_any_permission(
    user_id: UUID,
    tenant_id: UUID,
    module: str,
    permission_types: List[str]
) -> bool:
    """
    Check if user has any of the specified permissions
    """
    permissions = await get_user_permissions(user_id, tenant_id)
    
    if module not in permissions:
        return False
    
    for perm_type in permission_types:
        if permissions[module].get(perm_type, False):
            return True
    
    return False


async def has_all_permissions(
    user_id: UUID,
    tenant_id: UUID,
    module: str,
    permission_types: List[str]
) -> bool:
    """
    Check if user has all of the specified permissions
    """
    permissions = await get_user_permissions(user_id, tenant_id)
    
    if module not in permissions:
        return False
    
    for perm_type in permission_types:
        if not permissions[module].get(perm_type, False):
            return False
    
    return True


# ============================================
# GET ACCESSIBLE MODULES
# ============================================

async def get_accessible_modules(user_id: UUID, tenant_id: UUID) -> List[str]:
    """
    Get list of modules user has read access to
    (Used for sidebar filtering)
    """
    permissions = await get_user_permissions(user_id, tenant_id)
    
    accessible = []
    for module, perms in permissions.items():
        if perms.get("read", False):
            accessible.append(module)
    
    return accessible
