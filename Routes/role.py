
from fastapi import APIRouter, Depends, HTTPException
from beanie import PydanticObjectId
from typing import Optional
from uuid import UUID
from datetime import datetime

from Utility.auth_helpers import get_current_user

from Models.role import Role, ModulePermission

from Schema.role import (
    RoleCreate,
    RoleUpdate,
    PermissionToggle
)

router = APIRouter(
    prefix="/api/roles",
    tags=["Roles & Permissions"]
)

# =========================================================
# CREATE ROLE
# =========================================================

@router.post("/")
async def create_role(
    data: RoleCreate,
    current_user=Depends(get_current_user)
):

    tenant_id = UUID(current_user["tid"])
    created_by = UUID(current_user["sub"])

    # =========================================
    # CHECK EXISTING ROLE
    # =========================================

    existing_role = await Role.find_one(
        Role.role_name == data.role_name,
        Role.tenant_id == tenant_id
    )

    if existing_role:
        raise HTTPException(
            status_code=400,
            detail="Role already exists"
        )

    # =========================================
    # COUNT PERMISSIONS
    # =========================================

    permission_count = 0

    for module in data.modules:

        permission_count += sum([
        module.read,
        module.write,
        module.delete,
        module.export,
        module.approve
])

    # =========================================
    # CREATE ROLE
    # =========================================

    role = Role(

        tenant_id=tenant_id,

        role_name=data.role_name,

        is_system_role=data.is_system_role,

        default_for_new_employees=data.default_for_new_employees,

        modules=[
            module.dict()
            for module in data.modules
        ],

        total_permissions=permission_count,

        status="Active",

        created_by=created_by,

        created_at=datetime.utcnow()
    )

    await role.insert()

    return {
        "message": "Role created successfully",
        "data": role
    }


# =========================================================
# GET ALL ROLES
# =========================================================

@router.get("/")
async def get_roles(
    search: Optional[str] = None,
    current_user=Depends(get_current_user)
):

    tenant_id = UUID(current_user["tid"])

    roles = await Role.find(
        Role.tenant_id == tenant_id
    ).sort("-created_at").to_list()

    response = []

    for role in roles:

        if search:
            if search.lower() not in role.role_name.lower():
                continue

        response.append({

            "id": str(role.id),

            "role_name": role.role_name,

            "is_system_role": role.is_system_role,

            "default_for_new_employees":
                role.default_for_new_employees,

            "total_permissions":
                role.total_permissions,

            "status": role.status,

            "modules": role.modules,

            "created_at": role.created_at
        })

    return {
        "total_records": len(response),
        "data": response
    }


# =========================================================
# GET SINGLE ROLE
# =========================================================

@router.get("/{role_id}")
async def get_single_role(
    role_id: PydanticObjectId,
    current_user=Depends(get_current_user)
):

    tenant_id = UUID(current_user["tid"])

    role = await Role.find_one(
        Role.id == role_id,
        Role.tenant_id == tenant_id
    )

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role not found"
        )

    return role


# =========================================================
# UPDATE ROLE
# =========================================================

@router.put("/{role_id}")
async def update_role(
    role_id: PydanticObjectId,
    data: RoleUpdate,
    current_user=Depends(get_current_user)
):
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info(f"Updating role {role_id} with data: {data}")

    tenant_id = UUID(current_user["tid"])

    role = await Role.find_one(
        Role.id == role_id,
        Role.tenant_id == tenant_id
    )

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role not found"
        )

    # =========================================
    # UPDATE FIELDS
    # =========================================

    if data.role_name:
        role.role_name = data.role_name

    if data.is_system_role is not None:
        role.is_system_role = data.is_system_role

    if data.default_for_new_employees is not None:
        role.default_for_new_employees = (
            data.default_for_new_employees
        )

    # =========================================
    # UPDATE MODULES
    # =========================================

    if data.modules:
        logger.info(f"Updating modules: {data.modules}")
        
        role.modules = [
            module.dict()
            for module in data.modules
        ]

        permission_count = 0

        for module in data.modules:
            # Handle both nested and flat permission structures
            if hasattr(module, 'permissions'):
                # Nested structure: module.permissions.read
                permission_count += sum([
                    module.permissions.read,
                    module.permissions.write,
                    module.permissions.delete,
                    module.permissions.export,
                    module.permissions.approve
                ])
            else:
                # Flat structure: module.read
                permission_count += sum([
                    module.read,
                    module.write,
                    module.delete,
                    module.export,
                    module.approve
                ])

        role.total_permissions = permission_count
        logger.info(f"Total permissions calculated: {permission_count}")

    role.updated_at = datetime.utcnow()

    await role.save()
    
    logger.info(f"Role {role_id} updated successfully")

    return {
        "message": "Role updated successfully",
        "data": role
    }


# =========================================================
# DELETE ROLE
# =========================================================

@router.delete("/{role_id}")
async def delete_role(
    role_id: PydanticObjectId,
    current_user=Depends(get_current_user)
):

    tenant_id = UUID(current_user["tid"])

    role = await Role.find_one(
        Role.id == role_id,
        Role.tenant_id == tenant_id
    )

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role not found"
        )

    await role.delete()

    return {
        "message": "Role deleted successfully"
    }


# =========================================================
# UPDATE PERMISSION (TOGGLE)
# =========================================================

@router.patch("/{role_id}/permissions")
async def update_permission(
    role_id: PydanticObjectId,
    data: PermissionToggle,
    current_user=Depends(get_current_user)
):
    """
    Toggle a specific permission for a role.
    Used for single toggle updates from UI.
    """

    tenant_id = UUID(current_user["tid"])

    role = await Role.find_one(
        Role.id == role_id,
        Role.tenant_id == tenant_id
    )

    if not role:
        raise HTTPException(
            status_code=404,
            detail="Role not found"
        )

    # =========================================
    # UPDATE SPECIFIC PERMISSION
    # =========================================

    updated = False

    for module in role.modules:
        if module["module_name"] == data.module:
            # Update the specific permission
            if data.permission in ["read", "write", "delete", "export", "approve"]:
                module[data.permission] = data.value
                updated = True
            break

    # If module doesn't exist, add it
    if not updated:
        new_module = {
            "module_name": data.module,
            "read": data.permission == "read" and data.value,
            "write": data.permission == "write" and data.value,
            "delete": data.permission == "delete" and data.value,
            "export": data.permission == "export" and data.value,
            "approve": data.permission == "approve" and data.value
        }
        role.modules.append(new_module)

    # =========================================
    # RECALCULATE TOTAL PERMISSIONS
    # =========================================

    permission_count = 0
    for module in role.modules:
        permission_count += sum([
            module.get("read", False),
            module.get("write", False),
            module.get("delete", False),
            module.get("export", False),
            module.get("approve", False)
        ])

    role.total_permissions = permission_count
    role.updated_at = datetime.utcnow()

    await role.save()

    return {
        "message": "Permission updated successfully",
        "data": {
            "id": str(role.id),
            "role_name": role.role_name,
            "total_permissions": role.total_permissions,
            "modules": role.modules
        }
    }


# =========================================================
# GET USER PERMISSIONS
# =========================================================

@router.get("/user/permissions")
async def get_user_permissions(
    current_user=Depends(get_current_user)
):
    """
    Get the current user's role and permissions.
    Used for frontend permission checks.
    """

    from Models.tenant_user import TenantUser

    tenant_id = UUID(current_user["tid"])
    user_id = UUID(current_user["sub"])

    # Find user
    user = await TenantUser.find_one(
        TenantUser.id == user_id,
        TenantUser.tenant_id == tenant_id
    )

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    # If user doesn't have role_id, return default permissions
    if not hasattr(user, 'role_id') or not user.role_id:
        return {
            "user": {
                "id": str(user.id),
                "name": f"{user.first_name} {user.last_name}",
                "email": user.email,
                "role": user.role
            },
            "role": None,
            "permissions": {}
        }

    # Find role
    role = await Role.find_one(
        Role.id == user.role_id,
        Role.tenant_id == tenant_id
    )

    if not role:
        return {
            "user": {
                "id": str(user.id),
                "name": f"{user.first_name} {user.last_name}",
                "email": user.email,
                "role": user.role
            },
            "role": None,
            "permissions": {}
        }

    # Convert modules to permissions dict
    permissions = {}
    for module in role.modules:
        if isinstance(module, dict):
            module_name = module.get("module_name")
            permissions[module_name] = {
                "read": module.get("read", False),
                "write": module.get("write", False),
                "delete": module.get("delete", False),
                "export": module.get("export", False),
                "approve": module.get("approve", False)
            }
        else:
            module_name = getattr(module, "module_name", None)
            if module_name:
                permissions[module_name] = {
                    "read": getattr(module, "read", False),
                    "write": getattr(module, "write", False),
                    "delete": getattr(module, "delete", False),
                    "export": getattr(module, "export", False),
                    "approve": getattr(module, "approve", False)
                }

    return {
        "user": {
            "id": str(user.id),
            "name": f"{user.first_name} {user.last_name}",
            "email": user.email,
            "role": user.role
        },
        "role": {
            "id": str(role.id),
            "name": role.role_name,
            "is_system": role.is_system_role
        },
        "permissions": permissions
    }