"""
Payroll schemas for API requests and responses
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


# ─── Employee Payroll Config Schemas ───────────────────────────────────────────
class EmployeePayrollConfigCreate(BaseModel):
    """Request to create/update employee payroll config"""
    employee_id: UUID
    region: str  # IN, US, UK
    
    # India fields
    basic: Optional[float] = None
    hra: Optional[float] = None
    allowances: Optional[float] = None
    
    # US fields
    gross_salary: Optional[float] = None
    state: Optional[str] = None
    pay_type: Optional[str] = "Salary"
    k401_rate: Optional[float] = 0.05
    health_ins: Optional[float] = 250.0
    
    # UK fields
    gross_monthly: Optional[float] = None
    ni_code: Optional[str] = "A"
    pension_rate: Optional[float] = 0.05


class EmployeePayrollConfigResponse(BaseModel):
    """Response for employee payroll config"""
    id: UUID
    tenant_id: UUID
    employee_id: UUID
    region: str
    basic: Optional[float] = None
    hra: Optional[float] = None
    allowances: Optional[float] = None
    gross_salary: Optional[float] = None
    state: Optional[str] = None
    pay_type: Optional[str] = None
    k401_rate: Optional[float] = None
    health_ins: Optional[float] = None
    gross_monthly: Optional[float] = None
    ni_code: Optional[str] = None
    pension_rate: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ─── Payroll Run Schemas ───────────────────────────────────────────────────────
class RunPayrollRequest(BaseModel):
    """Request to run payroll"""
    region: str  # IN, US, UK
    month: int  # 1-12
    year: int
    employee_ids: Optional[List[UUID]] = None  # If None, run for all employees


class PayrollRunResponse(BaseModel):
    """Response after running payroll"""
    run_id: UUID
    region: str
    month: int
    year: int
    status: str
    payslip_count: int
    total_gross: float
    total_deductions: float
    total_net: float
    created_at: datetime
    processed_at: Optional[datetime] = None


# ─── Payslip Schemas ───────────────────────────────────────────────────────────
class PayslipFilter(BaseModel):
    """Filter params for payslips"""
    month: Optional[int] = None
    year: Optional[int] = None
    status: Optional[str] = None
    search: Optional[str] = None  # Search by employee name


class PayslipResponse(BaseModel):
    """Response for individual payslip"""
    id: UUID
    employee_id: UUID
    employee_name: str
    designation: str
    department: str
    region: str
    month: int
    year: int
    status: str
    components: Dict[str, Any]
    gross: float
    deductions: float
    net_pay: float
    pay_date: Optional[datetime] = None
    created_at: datetime


# ─── Dashboard Schemas ─────────────────────────────────────────────────────────
class DashboardResponse(BaseModel):
    """Dashboard summary response"""
    region: str
    employees: List[Dict[str, Any]]
    summary: Dict[str, Any]
    dept_breakdown: List[Dict[str, Any]]
