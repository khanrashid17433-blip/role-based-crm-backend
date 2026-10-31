
from fastapi import APIRouter, Depends, HTTPException
from Services.dashboard_service import DashboardService
from Schema.dashboard import DashboardStatsResponse
from Utility.auth_helpers import verify_platform_admin

router = APIRouter(
    prefix="/api/super-admin",
    responses={
        401: {"description": "Unauthorized - Invalid or missing token"},
        403: {"description": "Forbidden - Not a platform admin"},
        500: {"description": "Internal server error"}
    }
)


@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    admin_user = Depends(verify_platform_admin)
):
    try:
        dashboard_data = await DashboardService.get_dashboard_stats()
        return dashboard_data
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve dashboard statistics: {str(e)}"
        )
