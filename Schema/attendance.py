from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
from enum import Enum

# ================================
# ENUMS
# ================================

class RegionType(str, Enum):
    INDIA = "INDIA"
    US = "US"
    UK = "UK"


# ================================
# COMMON
# ================================

class LocationPoint(BaseModel):
    lat: float
    lng: float


# ================================
# COMPLIANCE RULES (CORE)
# ================================

class ComplianceRuleSchema(BaseModel):
    region: RegionType
    state: Optional[str] = None  # US specific

    # Work limits
    max_hours_per_day: Optional[float] = None
    max_hours_per_week: Optional[float] = None

    # OT Rules
    daily_ot_threshold: Optional[float] = None
    weekly_ot_threshold: Optional[float] = None

    ot_multiplier: float = 1.5
    double_ot_threshold: Optional[float] = None
    double_ot_multiplier: Optional[float] = None

    # India specific
    max_ot_hours_quarter: Optional[int] = None

    # UK specific
    max_avg_weekly_hours: Optional[float] = None
    reference_period_weeks: int = 17
    rest_hours_between_shifts: Optional[int] = None

    is_active: bool = True


# ================================
# ATTENDANCE REQUESTS
# ================================

class WebPunchRequest(BaseModel):
    action: str  # check_in, check_out, break_start, break_end
    work_mode: str = "office"
    location: Optional[LocationPoint] = None
    notes: Optional[str] = None


class BiometricPunchRequest(BaseModel):
    device_id: str
    employee_id: str
    timestamp: datetime
    punch_type: str = "auto"


class QrScanRequest(BaseModel):
    qr_token: str
    location: Optional[LocationPoint] = None


# ================================
# ADMIN UPDATE
# ================================

class AttendanceAdminUpdateRequest(BaseModel):
    check_in_time: Optional[datetime] = None
    check_out_time: Optional[datetime] = None
    status: Optional[str] = None
    working_hours: Optional[float] = None
    is_wfh: Optional[bool] = None
    source: Optional[str] = None
    admin_notes: str = Field(..., min_length=10)


# ================================
# COMPUTED ATTENDANCE (IMPORTANT)
# ================================

class AttendanceComputed(BaseModel):
    total_hours: float
    regular_hours: float
    overtime_hours: float
    double_overtime_hours: float = 0

    compliance_flags: List[str] = []
    warnings: List[str] = []


# ================================
# REGULARISATION
# ================================

class RegularisationRequest(BaseModel):
    date: date
    reason: str
    correct_check_in: str
    correct_check_out: str
    notes: str = Field(..., min_length=20)
    attachment_url: Optional[str] = None


# ================================
# SHIFT (UPDATED)
# ================================

class ShiftType(str, Enum):
    fixed = "fixed"
    flexible = "flexible"


class ShiftCreateRequest(BaseModel):
    name: str
    shift_type: ShiftType = ShiftType.fixed

    start_time: str
    end_time: str

    break_duration_mins: int
    is_break_paid: bool = False

    working_days: List[int]
    grace_period_mins: int = 10

    applicable_locations: List[UUID] = []

    # IMPORTANT
    region: RegionType


# ================================
# GEOFENCE
# ================================

class GeoFenceCreateRequest(BaseModel):
    location_id: Optional[UUID] = None
    center_lat: float
    center_lng: float
    radius_meters: int
    strict_mode: bool = False


# ================================
# GLOBAL POLICY
# ================================

class GlobalPolicyUpdateRequest(BaseModel):
    weekly_offs: List[int]
    late_marking_rule: str
    grace_period_mins: int
    default_ot_multiplier: float = 1.5


# ================================
# SHIFT ASSIGNMENT
# ================================

class ShiftAssignRequest(BaseModel):
    employee_ids: List[UUID]
    shift_id: UUID
    start_date: date
    end_date: date


# ================================
# ROSTER
# ================================

class RosterGenerateRequest(BaseModel):
    week_start: date


# ================================
# OT CALCULATION INPUT
# ================================

class OvertimeCalculationRequest(BaseModel):
    employee_id: UUID
    date: date

    total_hours: float
    weekly_hours: float

    consecutive_days: Optional[int] = 1
    quarterly_ot_hours: Optional[float] = 0


# ================================
# COMPLIANCE ALERT
# ================================

class ComplianceAlert(BaseModel):
    employee_id: UUID
    date: date
    region: RegionType

    alert_type: str
    severity: str  # INFO / WARNING / CRITICAL
    message: str


# ================================
# UK OPT-OUT
# ================================

class UKOptOut(BaseModel):
    employee_id: UUID
    has_opted_out: bool
    document_url: Optional[str] = None
    effective_from: date


# ================================
# INDIA QUARTERLY OT
# ================================

class QuarterlyOTRecord(BaseModel):
    employee_id: UUID
    quarter: str  # Q1-2026
    total_ot_hours: float
    limit: float = 50


# ================================
# OT CALCULATION ENGINE (CORE LOGIC)
# ================================

def calculate_overtime(data: OvertimeCalculationRequest, rule: ComplianceRuleSchema):

    ot = 0
    double_ot = 0
    flags = []

    # INDIA
    if rule.region == RegionType.INDIA:
        if data.total_hours > 9:
            ot = data.total_hours - 9

        if data.quarterly_ot_hours >= 40:
            flags.append("India OT nearing quarterly limit")

    # US
    elif rule.region == RegionType.US:

        if rule.state == "California":
            if data.total_hours > 12:
                double_ot = data.total_hours - 12
            elif data.total_hours > 8:
                ot = data.total_hours - 8

        if data.weekly_hours > 40:
            ot += data.weekly_hours - 40

    # UK
    elif rule.region == RegionType.UK:
        if data.weekly_hours > 48:
            ot = data.weekly_hours - 48
            flags.append("WTR weekly limit exceeded")

    return {
        "overtime_hours": ot,
        "double_overtime_hours": double_ot,
        "flags": flags
    }