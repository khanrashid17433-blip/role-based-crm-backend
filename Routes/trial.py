"""
Trial Management API Routes
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, Any
import logging

from Services.trial_service import TrialService
from Utility.auth_helpers import verify_platform_admin, get_current_user
from Utility.rate_limiter import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# ADMIN ENDPOINTS
# ============================================

@router.post(
    "/api/v1/superadmin/trials/check-expiry",
    status_code=status.HTTP_200_OK,
    summary="Manually trigger trial expiry check",
    description="Check for expired trials and update tenant status (superadmin only)"
)
@limiter.limit("5/hour")
async def trigger_trial_expiry_check(
    request: Request,
    admin_user = Depends(verify_platform_admin)
):
    """
    Manually trigger trial expiry check
    
    **Requires:** Platform superadmin role
    
    **This endpoint:**
    - Finds all tenants with expired trials
    - Converts to active if payment method exists
    - Suspends if no payment method
    - Sends notification emails
    
    **Use for:**
    - Testing trial expiry logic
    - Manual intervention
    - Debugging
    """
    try:
        logger.info(f"Manual trial expiry check triggered by admin: {admin_user['sub']}")
        
        results = await TrialService.check_expired_trials()
        
        return {
            "message": "Trial expiry check completed",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Trial expiry check failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check trial expiry: {str(e)}"
        )


@router.post(
    "/api/v1/superadmin/trials/send-reminders",
    status_code=status.HTTP_200_OK,
    summary="Send trial reminder emails",
    description="Send reminder emails to tenants with expiring trials (superadmin only)"
)
@limiter.limit("5/hour")
async def trigger_trial_reminders(
    request: Request,
    admin_user = Depends(verify_platform_admin)
):
    """
    Manually trigger trial reminder emails
    
    **Requires:** Platform superadmin role
    
    **Sends reminders to:**
    - Tenants with trials expiring in 3 days
    - Tenants with trials expiring in 1 day
    """
    try:
        logger.info(f"Manual trial reminders triggered by admin: {admin_user['sub']}")
        
        results = await TrialService.send_trial_reminders()
        
        return {
            "message": "Trial reminders sent",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Trial reminders failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send trial reminders: {str(e)}"
        )


# ============================================
# USER ENDPOINTS
# ============================================

@router.get(
    "/api/v1/trials/status",
    status_code=status.HTTP_200_OK,
    summary="Get trial status for current tenant",
    description="Get trial information for the authenticated user's tenant"
)
@limiter.limit("100/hour")
async def get_trial_status(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Get trial status for current tenant
    
    **Returns:**
    - Trial status (active/expired)
    - Days/hours remaining
    - Trial end date
    - Payment method status
    
    **Use for:**
    - Displaying trial banner in UI
    - Showing countdown timer
    - Prompting for payment
    """
    try:
        tenant_id = current_user["tid"]
        
        status_info = await TrialService.get_trial_status(tenant_id)
        
        return status_info
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Get trial status failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trial status"
        )
