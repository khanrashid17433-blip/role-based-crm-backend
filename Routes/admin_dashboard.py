from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from Utility.auth_helpers import get_current_user
from Services.admin_dashboard_service import AdminDashboardService
from Schema.admin_dashboard import AdminDashboardResponse

router = APIRouter(prefix="/api/admin-dashboard", tags=["Admin Dashboard"])

@router.get("/stats", response_model=AdminDashboardResponse)
async def get_admin_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Get dynamic Admin Dashboard statistics"""
    try:
        tenant_id = UUID(current_user['tid'])
        dashboard_data = await AdminDashboardService.get_dashboard_stats(tenant_id)
        return dashboard_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch admin dashboard data: {str(e)}"
        )
