from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional
from Services.tenent_service import SuperAdminService
from Services.plan_service import PlanService
from Services.platform_settings_service import PlatformSettingsService
from Schema.tenents import TenantListResponse, TenantDetailResponse, TenantResponse, LeadListResponse, SuperAdminSettingsResponse, UserListResponse
from Schema.plan import PlanListResponse, PlanResponse
from Schema.platform_settings import PlatformSettingsResponse, PlatformSettingsUpdate, SettingsAuditLogResponse
from Utility.auth_helpers import verify_platform_admin

router = APIRouter(
    prefix="/api/super-admin",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"},
        404: {"description": "Not found"}
    }
)


@router.get("/plans", response_model=PlanListResponse)
async def list_plans_super_admin(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    include_inactive: bool = Query(False, description="Include inactive plans"),
    admin_user = Depends(verify_platform_admin)
):
    """
    List all plans for super admin (SuperAdmin only)
    
    Requires platform_admin role.
    Supports pagination and can include inactive plans.
    """
    try:
        plans, total = await PlanService.list_plans(
            page=page,
            per_page=per_page,
            active_only=not include_inactive
        )
        
        # Convert plans to response format
        def convert_plan_to_response(plan) -> PlanResponse:
            return PlanResponse(
                id=str(plan.id),
                name=plan.name,
                slug=plan.slug,
                description=plan.description,
                price_monthly_usd=plan.price_monthly_usd,
                price_yearly_usd=plan.price_yearly_usd,
                price_monthly_gbp=plan.price_monthly_gbp,
                price_yearly_gbp=plan.price_yearly_gbp,
                price_monthly_eur=plan.price_monthly_eur,
                price_yearly_eur=plan.price_yearly_eur,
                price_monthly_inr=plan.price_monthly_inr,
                price_yearly_inr=plan.price_yearly_inr,
                max_employees=plan.max_employees,
                max_admin_users=plan.max_admin_users,
                modules_json=plan.modules_json or {},
                api_access=plan.api_access,
                sso_enabled=plan.sso_enabled,
                white_label=plan.white_label,
                support_tier=plan.support_tier.value if plan.support_tier else "community",
                has_trial=plan.has_trial,
                trial_days=plan.trial_days,
                regions_allowed=plan.regions_allowed or [],
                is_active=plan.is_active,
                sort_order=plan.sort_order,
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
        
        return PlanListResponse(
            plans=[convert_plan_to_response(plan) for plan in plans],
            total=total,
            page=page,
            per_page=per_page
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve plans: {str(e)}"
        )


@router.get("/settings", response_model=SuperAdminSettingsResponse)
async def get_super_admin_settings(
    admin_user = Depends(verify_platform_admin)
):
    """
    Get super admin dashboard settings and statistics (SuperAdmin only)
    
    Requires platform_admin role.
    Returns platform statistics and system health information.
    """
    try:
        settings = await SuperAdminService.get_super_admin_settings()
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve settings: {str(e)}"
        )

@router.get("/platform-settings", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    admin_user = Depends(verify_platform_admin)
):
    try:
        settings = await PlatformSettingsService.get_settings()
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve platform settings: {str(e)}"
        )

@router.put("/platform-settings", response_model=PlatformSettingsResponse)
async def update_platform_settings(
    data: PlatformSettingsUpdate,
    admin_user = Depends(verify_platform_admin)
):
    try:
        settings = await PlatformSettingsService.update_settings(
            data, 
            user_email=admin_user.get("email", "admin@system.com"), 
            user_name=admin_user.get("name", "Admin")
        )
        return settings
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update platform settings: {str(e)}"
        )

@router.get("/platform-settings/audit", response_model=list[SettingsAuditLogResponse])
async def get_platform_settings_audit(
    limit: int = Query(50, ge=1, le=500),
    admin_user = Depends(verify_platform_admin)
):
    try:
        return await PlatformSettingsService.get_audit_logs(limit)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve audit logs: {str(e)}"
        )

@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by status (trial, active, suspended, cancelled, churned)"),
    admin_user = Depends(verify_platform_admin)
):
    """
    List all tenants (SuperAdmin only)
    
    Requires platform_admin role.
    Supports pagination and optional status filtering.
    """
    try:
        tenants, total = await SuperAdminService.get_all_tenants(
            page=page,
            limit=limit,
            status=status
        )
        
        has_more = (page * limit) < total
        
        return TenantListResponse(
            tenants=tenants,
            total=total,
            page=page,
            limit=limit,
            has_more=has_more
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve tenants: {str(e)}"
        )


@router.get("/leads", response_model=LeadListResponse)
async def list_leads(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    registration_status: Optional[str] = Query(None, description="Filter by status (pending_verification, verified, expired)"),
    admin_user = Depends(verify_platform_admin)
):
    """
    List all leads/unverified registrations (SuperAdmin only)
    
    Requires platform_admin role.
    Supports pagination and optional status filtering.
    """
    try:
        leads, total = await SuperAdminService.get_all_leads(
            page=page,
            limit=limit,
            status=registration_status
        )
        
        has_more = (page * limit) < total
        
        return LeadListResponse(
            leads=leads,
            total=total,
            page=page,
            limit=limit,
            has_more=has_more
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve leads: {str(e)}"
        )


@router.get("/tenants/{tenant_id}", response_model=TenantDetailResponse)
async def get_tenant_detail(
    tenant_id: str,
    admin_user = Depends(verify_platform_admin)
):
    """
    Get detailed tenant information including admin user (SuperAdmin only)
    
    Requires platform_admin role.
    """
    try:
        tenant_detail = await SuperAdminService.get_tenant_detail(
            tenant_id=tenant_id
        )
        
        if not tenant_detail:
            raise HTTPException(
                status_code=404,
                detail=f"Tenant {tenant_id} not found"
            )
        
        return tenant_detail
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve tenant details: {str(e)}"
        )


@router.put("/tenants/{tenant_id}/status", response_model=TenantResponse)
async def update_tenant_status(
    tenant_id: str,
    status: str = Query(..., description="New status (trial, active, suspended, cancelled, churned)"),
    admin_user = Depends(verify_platform_admin)
):
    """
    Update tenant status (SuperAdmin only)
    
    Requires platform_admin role.
    """
    from Models.tenant_user import TenantStatus
    
    # Validate status value
    valid_statuses = [s.value for s in TenantStatus]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    try:
        tenant = await SuperAdminService.update_tenant_status(
            tenant_id=tenant_id,
            status=status
        )
        
        if not tenant:
            raise HTTPException(
                status_code=404,
                detail=f"Tenant {tenant_id} not found"
            )
        
        return TenantResponse.model_validate(tenant)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tenant status: {str(e)}"
        )


@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    user_type: Optional[str] = Query(None, description="Filter by user type (tenant_admin, employee, platform_admin)"),
    status: Optional[str] = Query(None, description="Filter by status (active, inactive, suspended)"),
    admin_user = Depends(verify_platform_admin)
):
    """
    List all users (SuperAdmin only)
    
    Requires platform_admin role.
    Supports pagination and optional filtering by tenant, user type, and status.
    """
    try:
        users, total = await SuperAdminService.get_all_users(
            page=page,
            limit=limit,
            tenant_id=tenant_id,
            user_type=user_type,
            status=status
        )
        
        has_more = (page * limit) < total
        
        return UserListResponse(
            users=users,
            total=total,
            page=page,
            limit=limit,
            has_more=has_more
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve users: {str(e)}"
        )
