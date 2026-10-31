from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

from Utility.auth_helpers import get_current_user, require_permissions
from Models.employee import Employee
from Models.tenant_user import User, Tenant, UserType
from Models.plan import Plan
from Services.auth_service import AuthService

router = APIRouter(prefix="/api/users")


# ── Request schema for profile update ─────────────────────────────────────────
class UpdateProfileRequest(BaseModel):
    first_name: Optional[str] = Field(None, max_length=100)
    last_name:  Optional[str] = Field(None, max_length=100)
    display_name: Optional[str] = Field(None, max_length=200)
    phone:      Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    timezone:   Optional[str] = Field(None, max_length=50)
    locale:     Optional[str] = Field(None, max_length=20)


class UpdateEmployeeRoleRequest(BaseModel):
    role: str = Field(..., max_length=50)
    user_type: Optional[str] = Field(None, max_length=50)


ADMIN_ROLES = {"admin", "tenant_admin", "hr_admin", "payroll_admin", "manager", "it_admin"}
ALLOWED_ROLES = {
    "employee",
    "manager",
    "hr_admin",
    "payroll_admin",
    "recruiter",
    "finance_viewer",
    "it_admin",
    "admin",
    "tenant_admin",
}


def _serialize_user(user: User) -> Dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": user.display_name,
        "user_type": user.user_type.value if user.user_type else None,
        "role": user.role,
        "status": user.status.value if user.status else None,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


async def _find_employee_user(employee_id: UUID, tenant_id: UUID) -> tuple[Employee, Optional[User]]:
    employee = await Employee.find_one(
        Employee.id == employee_id,
        Employee.tenant_id == tenant_id,
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )

    user = None
    if employee.user_id:
        user = await User.find_one(
            User.id == employee.user_id,
            User.tenant_id == tenant_id,
            User.deleted_at == None,
        )

    if not user and employee.email_work:
        user = await User.find_one(
            User.email == employee.email_work.lower().strip(),
            User.tenant_id == tenant_id,
            User.deleted_at == None,
        )

    return employee, user


# ── GET /api/users/me ─────────────────────────────────────────────────────────
@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user_profile(
    token_payload: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get current authenticated user's profile.
    Reads identity from the JWT token and enriches with DB data when available.
    """
    try:
        user_id_str   = token_payload.get("sub") or token_payload.get("user_id")
        tenant_id_str = token_payload.get("tid") or token_payload.get("tenant_id")

        # Try DB lookup
        db_user: User | None = None
        if user_id_str:
            try:
                db_user = await User.find_one(User.id == UUID(user_id_str))
            except Exception:
                pass

        db_tenant: Tenant | None = None
        plan_modules = {}
        plan_limits = {}
        plan_usage = {}
        if tenant_id_str:
            try:
                db_tenant = await Tenant.find_one(Tenant.id == UUID(tenant_id_str))
                if db_tenant and db_tenant.plan_id:
                    db_plan = await Plan.find_one(Plan.id == db_tenant.plan_id)
                    if db_plan:
                        plan_modules = db_plan.modules_json
                        plan_limits = {
                            "max_employees": db_plan.max_employees,
                            "max_admin_users": db_plan.max_admin_users
                        }
                        # Count active employees
                        from Models.employee import Employee, EmploymentStatus
                        active_employees = await Employee.find(
                            Employee.tenant_id == db_tenant.id,
                            Employee.employment_status != EmploymentStatus.TERMINATED
                        ).count()
                        
                        # Count admin users
                        from Models.tenant_user import UserType
                        admin_users = await User.find(
                            User.tenant_id == db_tenant.id,
                            {"$or": [{"user_type": UserType.admin_user}, {"user_type": UserType.tenant_admin}, {"role": "admin"}]}
                        ).count()
                        
                        # Count pending admin invitations
                        from Models.onboarding import UserInvitation
                        pending_admin_invites = await UserInvitation.find(
                            UserInvitation.tenant_id == db_tenant.id,
                            UserInvitation.status == "pending",
                            {"$or": [{"user_type": UserType.admin_user.value}, {"user_type": UserType.tenant_admin.value}, {"role": "admin"}]}
                        ).count()
                        
                        plan_usage = {
                            "employees": active_employees,
                            "admin_users": admin_users + pending_admin_invites
                        }
            except Exception:
                pass

        # Build user_data (DB wins; token is fallback)
        if db_user:
            # Resolve dynamic role name
            resolved_role_name = db_user.role
            try:
                from Models.role import Role
                if getattr(db_user, 'role_id', None):
                    db_role = await Role.get(db_user.role_id)
                    if db_role:
                        resolved_role_name = db_role.role_name
                        if db_user.role != db_role.role_name:
                            db_user.role = db_role.role_name
                            await db_user.save()
                elif db_user.role and getattr(db_user, 'tenant_id', None):
                    exact_role = db_user.role.strip()
                    db_roles = await Role.find(Role.tenant_id == db_user.tenant_id).to_list()
                    matched_role = None
                    for r in db_roles:
                        rn = (r.role_name or '').strip().lower()
                        en = exact_role.lower()
                        if rn == en or rn.replace(' ', '_') == en or rn.replace(' ', '_') == exact_role.replace(' ', '_').lower():
                            matched_role = r
                            break
                    if matched_role:
                        db_user.role_id = matched_role.id
                        db_user.role = matched_role.role_name
                        await db_user.save()
                        resolved_role_name = matched_role.role_name
            except Exception:
                pass

            user_data = {
                "id": str(db_user.id),
                "email": db_user.email,
                "first_name": db_user.first_name,
                "last_name": db_user.last_name,
                "display_name": db_user.display_name,
                "phone": db_user.phone,
                "avatar_url": db_user.avatar_url,
                "user_type": db_user.user_type.value if db_user.user_type else token_payload.get("user_type"),
                "role": resolved_role_name or token_payload.get("role"),
                "status": db_user.status.value if db_user.status else None,
                "email_verified": db_user.email_verified,
                "mfa_enabled": db_user.mfa_enabled,
                "timezone": db_user.timezone,
                "locale": db_user.locale,
                "tenant_id": str(db_user.tenant_id) if db_user.tenant_id else tenant_id_str,
                "last_login_at": db_user.last_login_at.isoformat() if db_user.last_login_at else None,
                "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
            }
        else:
            user_data = {
                "id": user_id_str,
                "email": token_payload.get("email"),
                "first_name": token_payload.get("first_name"),
                "last_name": token_payload.get("last_name"),
                "display_name": token_payload.get("display_name"),
                "phone": None,
                "avatar_url": None,
                "user_type": token_payload.get("user_type"),
                "role": token_payload.get("role"),
                "status": token_payload.get("status"),
                "email_verified": token_payload.get("email_verified", False),
                "mfa_enabled": token_payload.get("mfa_enabled", False),
                "timezone": token_payload.get("timezone"),
                "locale": token_payload.get("locale"),
                "tenant_id": tenant_id_str,
                "last_login_at": None,
                "created_at": None,
            }

        # Build tenant_data
        tenant_data = None
        if db_tenant:
            tenant_data = {
                "id": str(db_tenant.id),
                "name": db_tenant.name,
                "slug": db_tenant.slug,
                "subdomain": db_tenant.subdomain,
                "status": db_tenant.status.value if db_tenant.status else None,
                "primary_region": db_tenant.primary_region.value if db_tenant.primary_region else None,
                "primary_currency": db_tenant.primary_currency,
                "logo_url": db_tenant.logo_url,
                "brand_color": db_tenant.brand_color,
                "timezone": db_tenant.timezone,
                "date_format": db_tenant.date_format,
                "trial_ends_at": db_tenant.trial_ends_at.isoformat() if db_tenant.trial_ends_at else None,
                "onboarding_completed": db_tenant.onboarding_completed,
                "plan_id": str(db_tenant.plan_id) if db_tenant.plan_id else None,
                "modules": plan_modules,
                "plan_limits": plan_limits,
                "plan_usage": plan_usage,
            }

        return {"user": user_data, "tenant": tenant_data}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch user profile: {str(e)}"
        )


# ── PATCH /api/users/me ───────────────────────────────────────────────────────
@router.patch("/me", status_code=status.HTTP_200_OK)
async def update_current_user_profile(
    update_data: UpdateProfileRequest,
    token_payload: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        user_id_str = token_payload.get("sub") or token_payload.get("user_id")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cannot determine user identity from token."
            )

        db_user = await User.find_one(User.id == UUID(user_id_str))
        if not db_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found."
            )

        # Apply only the provided (non-None) fields
        changed = False
        update_dict = update_data.model_dump(exclude_none=True)

        for field, value in update_dict.items():
            if hasattr(db_user, field) and getattr(db_user, field) != value:
                setattr(db_user, field, value)
                changed = True

        if changed:
            db_user.updated_at = datetime.utcnow()
            await db_user.save()

        return {
            "message": "Profile updated successfully." if changed else "No changes detected.",
            "user": {
                "id": str(db_user.id),
                "email": db_user.email,
                "first_name": db_user.first_name,
                "last_name": db_user.last_name,
                "display_name": db_user.display_name,
                "phone": db_user.phone,
                "avatar_url": db_user.avatar_url,
                "user_type": db_user.user_type.value if db_user.user_type else None,
                "role": db_user.role,
                "status": db_user.status.value if db_user.status else None,
                "email_verified": db_user.email_verified,
                "mfa_enabled": db_user.mfa_enabled,
                "timezone": db_user.timezone,
                "locale": db_user.locale,
                "tenant_id": str(db_user.tenant_id) if db_user.tenant_id else None,
                "updated_at": db_user.updated_at.isoformat() if db_user.updated_at else None,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}"
        )


@router.patch("/employees/{employee_id}/role", status_code=status.HTTP_200_OK)
async def update_employee_user_role(
    employee_id: UUID,
    update_data: UpdateEmployeeRoleRequest,
    token_payload: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        require_permissions(token_payload, ["employee:update"])

        tenant_id_str = token_payload.get("tid") or token_payload.get("tenant_id")
        if not tenant_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cannot determine tenant from token.",
            )

        role = (update_data.role or "").strip().lower()
        if role not in ALLOWED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported role '{update_data.role}'.",
            )

        _, user = await _find_employee_user(employee_id, UUID(tenant_id_str))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No linked user account found for this employee. Send an invitation or create a user account first.",
            )

        user.role = role
        if update_data.user_type:
            try:
                user.user_type = UserType(update_data.user_type)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported user type '{update_data.user_type}'.",
                )
        else:
            user.user_type = UserType.admin_user if role in ADMIN_ROLES else UserType.employee

        user.updated_at = datetime.utcnow()
        await user.save()

        return {
            "message": "User role updated successfully.",
            "user": _serialize_user(user),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update employee role: {str(e)}",
        )


@router.post("/employees/{employee_id}/password-reset", status_code=status.HTTP_200_OK)
async def send_employee_password_reset(
    employee_id: UUID,
    request: Request,
    token_payload: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        require_permissions(token_payload, ["employee:update"])

        tenant_id_str = token_payload.get("tid") or token_payload.get("tenant_id")
        if not tenant_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Cannot determine tenant from token.",
            )

        _, user = await _find_employee_user(employee_id, UUID(tenant_id_str))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No linked user account found for this employee. Send an invitation first so they can create a login.",
            )

        ip_address = request.client.host if request.client else None
        await AuthService.request_password_reset(user.email, ip_address=ip_address)

        return {
            "message": f"Password reset link sent to {user.email}.",
            "email": user.email,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send password reset link: {str(e)}",
        )

@router.get("/")
async def get_all_users():

    try:
        users = await User.find_all().to_list()

        response = []

        for user in users:

            response.append({
                "id": str(user.id),
                "tenant_id": str(user.tenant_id),

                # Personal Info
                "first_name": user.first_name,
                "last_name": user.last_name,

                # Full Name
                "name": f"{user.first_name} {user.last_name}",

                # Display Name
                "display_name": user.display_name,

                # Email
                "email": user.email,

                # Phone
                "phone": user.phone,

                # Role & Type
                "role": user.role,
                "user_type": user.user_type,

                # Status
                "status": user.status,

                # Verification
                "email_verified": user.email_verified,
                "phone_verified": user.phone_verified,

                # Auth
                "auth_provider": user.auth_provider,

                # Login Info
                "last_login_at": user.last_login_at,

                # Dates
                "created_at": user.created_at,
                "updated_at": user.updated_at,
            })

        return {
            "success": True,
            "count": len(response),
            "data": response
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )