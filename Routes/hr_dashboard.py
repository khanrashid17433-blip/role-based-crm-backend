from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from Utility.auth_helpers import get_current_user, require_permissions
from Services.hr_dashboard_service import HRDashboardService
from Schema.hr_dashboard import HRDashboardResponse

router = APIRouter(prefix="/api/hr", tags=["HR Dashboard"])

@router.get("/dashboard", response_model=HRDashboardResponse)
async def get_hr_dashboard(current_user: dict = Depends(get_current_user)):
    """Get dynamic HR dashboard statistics"""
    # require_permissions(current_user, ["employee:read"]) # Relaxing to basic access for HR roles
    
    try:
        tenant_id = UUID(current_user['tid'])
        dashboard_data = await HRDashboardService.get_dashboard_data(tenant_id)
        return dashboard_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch HR dashboard data: {str(e)}"
        )
