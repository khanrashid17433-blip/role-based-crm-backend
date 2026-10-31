"""
Payroll models for India (IN), US, and UK regions
"""
from beanie import Document
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID, uuid4
from enum import Enum


class PayrollRegion(str, Enum):
    IN = "IN"
    US = "US"
    UK = "UK"


class PayrollStatus(str, Enum):
    draft = "draft"
    processing = "processing"
    processed = "processed"
    failed = "failed"
    on_hold = "on_hold"


class PayslipStatus(str, Enum):
    processed = "Processed"
    pending = "Pending"
    on_hold = "On Hold"
    failed = "Failed"


# ─── India Salary Components ───────────────────────────────────────────────────
class INSalaryComponents(BaseModel):
    basic: float = 0
    hra: float = 0
    allowances: float = 0
    bonus: float = 0
    overtime: float = 0
    gross: float = 0
    pf: float = 0          # 12% of basic
    esi: float = 0         # 3.25% of gross if gross <= 21000
    prof_tax: float = 0    # slab-based
    tds: float = 0         # income tax at source
    loan: float = 0
    advance: float = 0
    other: float = 0
    deductions: float = 0
    net_pay: float = 0


# ─── US Salary Components ──────────────────────────────────────────────────────
class USSalaryComponents(BaseModel):
    gross: float = 0
    federal_tax: float = 0   # 22% simplified
    state_tax: float = 0     # by state
    social_sec: float = 0    # 6.2%
    medicare: float = 0      # 1.45%
    k401: float = 0          # employee contribution
    health_ins: float = 0    # fixed per employee
    deductions: float = 0
    net_pay: float = 0
    state: str = "CA"
    pay_type: str = "Salary"  # Salary | Hourly
    k401_rate: float = 0.05


# ─── UK Salary Components ──────────────────────────────────────────────────────
class UKSalaryComponents(BaseModel):
    gross: float = 0
    paye: float = 0       # income tax
    ni: float = 0         # national insurance
    pension: float = 0    # auto-enrolment
    deductions: float = 0
    net_pay: float = 0
    ni_code: str = "A"
    pension_rate: float = 0.05


# ─── Employee Payroll Config (per employee, per region) ───────────────────────
class EmployeePayrollConfig(Document):
    """Stores payroll configuration per employee per region"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    employee_id: UUID
    region: PayrollRegion

    # India fields
    basic: Optional[float] = None
    hra: Optional[float] = None
    allowances: Optional[float] = None
    bonus: Optional[float] = 0
    overtime: Optional[float] = 0
    loan: Optional[float] = 0
    advance: Optional[float] = 0
    other: Optional[float] = 0

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

    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "employee_payroll_configs"


# ─── Payroll Run (tracks each payroll execution) ──────────────────────────────
class PayrollRun(Document):
    """Tracks each payroll run execution"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    region: PayrollRegion
    month: int  # 1-12
    year: int
    status: PayrollStatus = PayrollStatus.draft
    employee_ids: List[UUID] = []
    total_gross: float = 0
    total_deductions: float = 0
    total_net: float = 0
    payslip_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    created_by: Optional[UUID] = None

    class Settings:
        name = "payroll_runs"


# ─── Payslip (individual employee payslip) ────────────────────────────────────
class Payslip(Document):
    """Individual employee payslip"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    employee_id: Optional[UUID] = None
    payroll_run_id: Optional[UUID] = None
    region: Optional[PayrollRegion] = None
    month: Any
    year: Optional[int] = None
    status: Any = PayslipStatus.processed
    
    # Employee info snapshot
    employee_name: str = ""
    designation: str = ""
    department: str = ""
    
    # Salary components (stored as dict for flexibility)
    components: Dict[str, Any] = {}
    
    gross: float = 0
    deductions: float = 0
    net_pay: float = 0
    
    pay_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Fields to match EmployeePayslip to prevent validation crashes
    user_id: Optional[UUID] = None
    gross_pay: Optional[float] = Field(default=0)
    pay_period: Optional[str] = Field(default="", max_length=200)

    class Settings:
        name = "payslips"
