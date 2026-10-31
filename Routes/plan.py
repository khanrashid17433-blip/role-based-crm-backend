from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List
from uuid import UUID

from Services.plan_service import PlanService
from Schema.plan import (
    PlanCreate,
    PlanUpdate,
    PlanResponse,
    PlanListResponse
)
from Utility.helpers import PlanNotFound, DuplicateSlugError
from Utility.auth_helpers import verify_platform_admin

router = APIRouter(prefix="/api/plans")


def convert_plan_to_response(plan) -> PlanResponse:
    """Convert Plan model to PlanResponse schema"""
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


# ============================================
# PUBLIC ROUTES (No Authentication Required)
# ============================================

@router.get("", response_model=PlanListResponse, summary="List all active plans")
async def list_active_plans(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page")
):
    """
    Get all active plans for the pricing page.
    Returns paginated list of active plans sorted by sort_order.
    """
    try:
        plans, total = await PlanService.list_plans(
            page=page,
            per_page=per_page,
            active_only=True
        )
        
        return PlanListResponse(
            plans=[convert_plan_to_response(plan) for plan in plans],
            total=total,
            page=page,
            per_page=per_page
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching plans: {str(e)}"
        )


@router.get("/{slug}", response_model=PlanResponse, summary="Get plan by slug")
async def get_plan_by_slug(slug: str):
    """
    Get detailed information about a specific plan by its slug.
    Only returns active plans.
    """
    try:
        plan = await PlanService.get_plan_by_slug(slug=slug)
        return convert_plan_to_response(plan)
    except PlanNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching plan: {str(e)}"
        )


# ============================================
# ADMIN ROUTES (Authentication Required - Future)
# ============================================

@router.post(
    "/api/v1/superadmin/plans",
    response_model=PlanResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create new plan",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"}
    }
)
async def create_plan(
    plan_data: PlanCreate,
    admin_user = Depends(verify_platform_admin)
):
    """
    Create a new pricing plan.
    
    **Requires:** Platform superadmin role
    
    This endpoint allows superadmins to create new subscription plans with
    pricing, features, and limits configuration.
    """
    try:
        plan = await PlanService.create_plan(plan_data=plan_data)
        return convert_plan_to_response(plan)
    except DuplicateSlugError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating plan: {str(e)}"
        )


@router.get(
    "/api/v1/superadmin/plans",
    response_model=PlanListResponse,
    summary="List all plans (superadmin)",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"}
    }
)
async def list_all_plans(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    include_inactive: bool = Query(False, description="Include inactive plans"),
    admin_user = Depends(verify_platform_admin)
):
    """
    List all plans including inactive ones.
    
    **Requires:** Platform superadmin role
    
    Superadmins can view all plans (active and inactive) with pagination support.
    """
    try:
        plans, total = await PlanService.list_plans(
            page=page,
            per_page=per_page,
            active_only=not include_inactive
        )
        
        return PlanListResponse(
            plans=[convert_plan_to_response(plan) for plan in plans],
            total=total,
            page=page,
            per_page=per_page
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching plans: {str(e)}"
        )


@router.get(
    "/api/v1/superadmin/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Get plan by ID (superadmin)",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"},
        404: {"description": "Plan not found"}
    }
)
async def get_plan_by_id(
    plan_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Get plan details by ID (includes inactive plans).
    
    **Requires:** Platform superadmin role
    
    Returns detailed plan information including pricing, features, and configuration.
    """
    try:
        plan = await PlanService.get_plan_by_id(plan_id=plan_id)
        return convert_plan_to_response(plan)
    except PlanNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching plan: {str(e)}"
        )


@router.put(
    "/api/v1/superadmin/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Update plan",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"},
        404: {"description": "Plan not found"},
        409: {"description": "Duplicate slug error"}
    }
)
async def update_plan(
    plan_id: UUID,
    plan_data: PlanUpdate,
    admin_user = Depends(verify_platform_admin)
):
    """
    Update an existing plan.
    
    **Requires:** Platform superadmin role
    
    Superadmins can modify pricing, features, limits, and other plan configurations.
    """
    try:
        plan = await PlanService.update_plan(plan_id=plan_id, plan_data=plan_data)
        return convert_plan_to_response(plan)
    except PlanNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except DuplicateSlugError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating plan: {str(e)}"
        )


@router.delete(
    "/api/v1/superadmin/plans/{plan_id}",
    response_model=PlanResponse,
    summary="Soft delete plan",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"},
        404: {"description": "Plan not found"}
    }
)
async def delete_plan(
    plan_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Soft delete a plan (sets is_active=False).
    
    **Requires:** Platform superadmin role
    
    The plan is marked as inactive but remains in the database. 
    Existing tenants on this plan won't be affected.
    """
    try:
        plan = await PlanService.delete_plan(plan_id=plan_id)
        return convert_plan_to_response(plan)
    except PlanNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting plan: {str(e)}"
        )


@router.delete(
    "/api/v1/superadmin/plans/{plan_id}/hard",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hard delete plan",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"},
        404: {"description": "Plan not found"}
    }
)
async def hard_delete_plan(
    plan_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Permanently delete a plan from the database.
    
    **Requires:** Platform superadmin role
    
    ⚠️ **CAUTION** - This action is permanent and cannot be undone.
    The plan will be completely removed from the system including all historical records.
    Use only in exceptional circumstances.
    """
    try:
        await PlanService.hard_delete_plan(plan_id=plan_id)
        return None
    except PlanNotFound as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting plan: {str(e)}"
        )
