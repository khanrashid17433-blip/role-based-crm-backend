"""
Payroll routes for India, US, and UK regions
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from Schema.payroll import (
    EmployeePayrollConfigCreate,
    EmployeePayrollConfigResponse,
    RunPayrollRequest,
    PayrollRunResponse,
    PayslipResponse,
    DashboardResponse
)
from Services.payroll_service import PayrollService
from Utility.auth_helpers import get_current_user
from pydantic import BaseModel

router = APIRouter(prefix="/api/payroll", tags=["Payroll Management"])


# ─── Employee Payroll Config ───────────────────────────────────────────────────
@router.post("/config", response_model=EmployeePayrollConfigResponse)
async def create_or_update_employee_config(
    data: EmployeePayrollConfigCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create or update employee payroll configuration"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        config_data = data.model_dump(exclude={"employee_id", "region"}, exclude_none=True)
        config = await PayrollService.upsert_employee_config(
            tenant_id=tenant_id,
            employee_id=data.employee_id,
            region=data.region,
            data=config_data
        )
        return EmployeePayrollConfigResponse(
            id=config.id,
            tenant_id=config.tenant_id,
            employee_id=config.employee_id,
            region=config.region,
            basic=config.basic,
            hra=config.hra,
            allowances=config.allowances,
            gross_salary=config.gross_salary,
            state=config.state,
            pay_type=config.pay_type,
            k401_rate=config.k401_rate,
            health_ins=config.health_ins,
            gross_monthly=config.gross_monthly,
            ni_code=config.ni_code,
            pension_rate=config.pension_rate,
            is_active=config.is_active,
            created_at=config.created_at,
            updated_at=config.updated_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save payroll config: {str(e)}"
        )


@router.get("/config/{region}", response_model=List[EmployeePayrollConfigResponse])
async def get_employee_configs(
    region: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all employee payroll configs for a region"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        configs = await PayrollService.get_employee_configs(
            tenant_id=tenant_id,
            region=region
        )
        return [
            EmployeePayrollConfigResponse(
                id=c.id,
                tenant_id=c.tenant_id,
                employee_id=c.employee_id,
                region=c.region,
                basic=c.basic,
                hra=c.hra,
                allowances=c.allowances,
                gross_salary=c.gross_salary,
                state=c.state,
                pay_type=c.pay_type,
                k401_rate=c.k401_rate,
                health_ins=c.health_ins,
                gross_monthly=c.gross_monthly,
                ni_code=c.ni_code,
                pension_rate=c.pension_rate,
                is_active=c.is_active,
                created_at=c.created_at,
                updated_at=c.updated_at
            )
            for c in configs
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch configs: {str(e)}"
        )


# ─── Dashboard ─────────────────────────────────────────────────────────────────
@router.get("/dashboard/{region}", response_model=DashboardResponse)
async def get_payroll_dashboard(
    region: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    current_user: dict = Depends(get_current_user)
):
    """Get payroll dashboard with employee list, summary, and dept breakdown"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        dashboard = await PayrollService.get_dashboard(
            tenant_id=tenant_id,
            region=region,
            month=month,
            year=year
        )
        return DashboardResponse(**dashboard)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch dashboard: {str(e)}"
        )


# ─── Preview Payroll ───────────────────────────────────────────────────────────
@router.get("/preview/{region}")
async def preview_payroll(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    employee_ids: Optional[str] = Query(None, description="Comma-separated employee IDs"),
    current_user: dict = Depends(get_current_user)
):
    """Preview payroll calculations before running"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        emp_ids = None
        if employee_ids:
            emp_ids = [UUID(eid.strip()) for eid in employee_ids.split(",")]
        
        preview = await PayrollService.preview_payroll(
            tenant_id=tenant_id,
            region=region,
            month=month,
            year=year,
            employee_ids=emp_ids
        )
        return preview
    except Exception as e:
        import traceback
        traceback.print_exc()
        with open("preview_error.log", "w") as f:
            f.write(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview payroll: {str(e)}"
        )


# ─── Attendance Sync ───────────────────────────────────────────────────────────
class AttendanceSyncRequest(BaseModel):
    employee_ids: Optional[List[UUID]] = None

@router.post("/attendance-sync/{region}")
async def sync_attendance_for_payroll(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    data: AttendanceSyncRequest = Body(default=AttendanceSyncRequest()),
    current_user: dict = Depends(get_current_user)
):
    """Sync attendance data for payroll (Present, Absent, Leave, Overtime)"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        result = await PayrollService.sync_attendance(
            tenant_id=tenant_id,
            region=region,
            month=month,
            year=year,
            employee_ids=data.employee_ids
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync attendance: {str(e)}"
        )


# ─── Lock Period ──────────────────────────────────────────────────────────────
class LockPeriodRequest(BaseModel):
    employee_ids: List[UUID]

@router.post("/lock-period/{region}")
async def lock_payroll_period(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    lock: bool = Query(...),
    data: LockPeriodRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Lock or unlock payroll period"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        
        run = await PayrollService.lock_period(
            tenant_id=tenant_id,
            region=region,
            month=month,
            year=year,
            lock=lock,
            employee_ids=data.employee_ids,
            admin_id=user_id
        )
        
        return {
            "success": True,
            "locked": lock,
            "run_id": str(run.id) if run else None,
            "timestamp": datetime.utcnow().isoformat() if lock else None
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to lock period: {str(e)}"
        )


# ─── Update Earnings ───────────────────────────────────────────────────────────
@router.put("/earnings/{employee_id}")
async def update_employee_earnings(
    employee_id: UUID,
    data: dict,
    current_user: dict = Depends(get_current_user)
):
    """Update employee earnings for payroll"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        await PayrollService.update_earnings(tenant_id, employee_id, data)
        return {"success": True, "employee_id": str(employee_id), "data": data}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update earnings: {str(e)}"
        )


# ─── Approve Payroll ───────────────────────────────────────────────────────────
@router.post("/approve/{region}")
async def approve_payroll(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    current_user: dict = Depends(get_current_user)
):
    """Approve payroll for processing"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        await PayrollService.approve_payroll(tenant_id, region, month, year)
        return {"success": True, "approved": True}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve payroll: {str(e)}"
        )


# ─── Generate Payslips ─────────────────────────────────────────────────────────
@router.post("/generate-payslips/{region}")
async def generate_payslips(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    current_user: dict = Depends(get_current_user)
):
    """Generate PDF payslips for all employees"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        # PDF generation can be added here or in the run_payroll
        return {"success": True, "count": 0}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate payslips: {str(e)}"
        )


# ─── Download Bank File ────────────────────────────────────────────────────────
@router.get("/bank-file/{region}")
async def download_bank_file(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    current_user: dict = Depends(get_current_user)
):
    """Download bank transfer file (NEFT/RTGS)"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        # Generate bank file (e.g., CSV format)
        return {"success": True, "file_url": ""}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate bank file: {str(e)}"
        )


# ─── Mark as Paid ──────────────────────────────────────────────────────────────
@router.get("/payslips/{region}")
async def get_payslips(
    region: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    employee_id: Optional[UUID] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get all payslips with filters"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        payslips = await PayrollService.get_payslips(
            tenant_id, region, month, year, employee_id
        )
        return payslips
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch payslips: {str(e)}"
        )


@router.get("/payslips/{region}/{payslip_id}/download")
async def download_payslip_pdf(
    region: str,
    payslip_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Download individual payslip PDF"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        # Generate dummy PDF or real PDF here
        return {"success": True, "message": "Payslip downloaded successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate payslip: {str(e)}"
        )


# ─── Send Notifications ────────────────────────────────────────────────────────
@router.post("/send-notifications/{region}")
async def send_payslip_notifications(
    region: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2020, le=2100),
    current_user: dict = Depends(get_current_user)
):
    """Send payslip notifications to employees"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        # TODO: Send email notifications
        return {"success": True, "sent": 0}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send notifications: {str(e)}"
        )


# ─── Run Payroll ───────────────────────────────────────────────────────────────
@router.post("/run", response_model=PayrollRunResponse)
async def run_payroll(
    data: RunPayrollRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute payroll run and generate payslips"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        run = await PayrollService.run_payroll(
            tenant_id=tenant_id,
            region=data.region,
            month=data.month,
            year=data.year,
            employee_ids=data.employee_ids,
            created_by=user_id
        )
        return PayrollRunResponse(
            run_id=run.id,
            region=run.region,
            month=run.month,
            year=run.year,
            status=run.status,
            payslip_count=run.payslip_count,
            total_gross=run.total_gross,
            total_deductions=run.total_deductions,
            total_net=run.total_net,
            created_at=run.created_at,
            processed_at=run.processed_at
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run payroll: {str(e)}"
        )


# ─── Get Payslips ──────────────────────────────────────────────────────────────
@router.get("/payslips/{region}", response_model=List[PayslipResponse])
async def get_payslips(
    region: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2100),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """Get payslips with filters"""
    try:
        tenant_id = UUID(current_user.get('tid'))
        payslips = await PayrollService.get_payslips(
            tenant_id=tenant_id,
            region=region,
            month=month,
            year=year,
            status=status,
            search=search
        )
        return [
            PayslipResponse(
                id=p.id,
                employee_id=p.employee_id,
                employee_name=p.employee_name,
                designation=p.designation,
                department=p.department,
                region=p.region,
                month=p.month,
                year=p.year,
                status=p.status.value if hasattr(p.status, "value") else p.status,
                components=p.components,
                gross=p.gross,
                deductions=p.deductions,
                net_pay=p.net_pay,
                pay_date=p.pay_date,
                created_at=p.created_at
            )
            for p in payslips
        ]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch payslips: {str(e)}"
        )
