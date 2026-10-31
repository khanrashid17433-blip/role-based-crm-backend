from beanie import Document
from pydantic import Field
from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import enum

# ==========================================
# ENUMS
# ==========================================

class PunchType(str, enum.Enum):
    check_in = "check_in"
    check_out = "check_out"
    break_start = "break_start"
    break_end = "break_end"

class AttendanceSource(str, enum.Enum):
    biometric = "biometric"
    mobile_gps = "mobile_gps"
    web = "web"
    qr = "qr"
    manual = "manual"
    system = "system"
    bulk_action = "bulk_action"

class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    late = "late"
    half_day = "half_day"
    on_leave = "on_leave"
    holiday = "holiday"
    wfh = "wfh"

class ShiftType(str, enum.Enum):
    fixed = "fixed"
    rotational = "rotational"
    flexible = "flexible"
    split = "split"
    on_call = "on_call"
    zero_hours = "zero_hours"

class RegularisationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

# ==========================================
# MODELS
# ==========================================

class Shift(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    name: str = Field(..., max_length=100)
    shift_type: ShiftType = Field(default=ShiftType.fixed)
    
    start_time: str
    end_time: str
    break_duration_mins: int = 0
    is_break_paid: bool = False
    
    overtime_after_hrs: float = 8.0
    ot_rate_multiplier: float = 1.5
    
    working_days: List[int] = Field(default_factory=list) # 0=Monday, 6=Sunday
    grace_period_mins: int = 10
    
    applicable_locations: List[UUID] = Field(default_factory=list) # Optional location restrictions
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "shifts"
        indexes = ["tenant_id"]

class AttendanceRawLog(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    employee_id: UUID
    device_id: Optional[UUID] = None
    
    raw_timestamp: datetime
    punch_type: Optional[PunchType] = None
    source: AttendanceSource
    
    raw_payload_json: Dict[str, Any] = Field(default_factory=dict)
    
    processed: bool = False
    processed_at: Optional[datetime] = None
    
    class Settings:
        name = "attendance_raw_logs"
        indexes = ["tenant_id", "employee_id", "processed"]

class AttendanceLog(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    employee_id: UUID
    date: datetime
    shift_id: Optional[UUID] = None
    
    check_in_at: Optional[datetime] = None
    check_out_at: Optional[datetime] = None
    source: AttendanceSource
    
    check_in_location_json: Optional[Dict[str, Any]] = None
    check_out_location_json: Optional[Dict[str, Any]] = None
    
    is_wfh: bool = False
    working_hours: float = 0.0
    break_duration_mins: int = 0
    overtime_hours: float = 0.0
    
    status: AttendanceStatus = Field(default=AttendanceStatus.present)
    
    is_regularised: bool = False
    regularised_by: Optional[UUID] = None
    regularised_at: Optional[datetime] = None
    notes: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "attendance_logs"
        indexes = ["tenant_id", "employee_id", "date"]

class AttendanceDevice(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    location_id: Optional[UUID] = None
    device_name: str
    device_type: str
    endpoint_url: Optional[str] = None
    auth_token_encrypted: Optional[str] = None
    
    last_sync_at: Optional[datetime] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "attendance_devices"

class AttendanceGeoFence(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    location_id: Optional[UUID] = None
    
    center_lat: float
    center_lng: float
    radius_meters: int
    strict_mode: bool = False # deny vs flag
    
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "attendance_geo_fences"

class AttendanceRegularisation(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    employee_id: UUID
    attendance_log_id: UUID
    date: datetime
    
    reason: str
    correct_check_in: str
    correct_check_out: str
    notes: str
    attachment_url: Optional[str] = None
    
    status: RegularisationStatus = Field(default=RegularisationStatus.pending)
    approver_id: UUID
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "attendance_regularisations"
        indexes = ["tenant_id", "employee_id"]

class AttendanceQrSession(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    location_id: UUID
    token_hash: str
    generated_at: datetime
    expires_at: datetime
    scans_count: int = 0
    
    class Settings:
        name = "attendance_qr_sessions"
        indexes = ["tenant_id"]

class OvertimeApproval(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    employee_id: UUID
    date: datetime
    overtime_hours: float
    reason: str
    
    status: str = "pending"
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    payroll_entry_id: Optional[UUID] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "overtime_approvals"
        indexes = ["tenant_id", "employee_id"]

class ShiftSwap(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    requester_id: UUID
    target_employee_id: UUID
    date: datetime
    
    requester_shift_id: UUID
    target_shift_id: UUID
    reason: str
    
    status: str = "pending"
    approved_by: Optional[UUID] = None
    approved_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "shift_swaps"
        indexes = ["tenant_id", "requester_id"]

class WtrOptOut(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    employee_id: UUID
    signed_date: datetime
    document_url: str
    opted_in_again_date: Optional[datetime] = None
    
    class Settings:
        name = "wtr_opt_outs"
        indexes = ["tenant_id", "employee_id"]

class RosterDraft(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    entity_id: Optional[UUID] = None
    week_start: datetime
    published: bool = False
    published_at: Optional[datetime] = None
    created_by: UUID
    
    class Settings:
        name = "roster_drafts"

class RosterAssignment(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    roster_id: UUID
    employee_id: UUID
    date: datetime
    shift_id: UUID
    
    is_holiday: bool = False
    is_leave: bool = False
    notes: Optional[str] = None
    
    class Settings:
        name = "roster_assignments"
        indexes = ["tenant_id", "roster_id", "employee_id"]

class GlobalAttendancePolicy(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    weekly_offs: List[int] = Field(default_factory=list) # 0=Monday, 6=Sunday
    late_marking_rule: str = "3 Lates = 1 Half Day"
    grace_period_mins: int = 15
    ot_multiplier: float = 1.5
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "global_attendance_policies"
        indexes = ["tenant_id"]
