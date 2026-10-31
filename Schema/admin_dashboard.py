from pydantic import BaseModel
from typing import List, Optional

class AttendanceStats(BaseModel):
    present: int
    absent: int
    late: int
    onLeave: int
    total: int
    rate: float

class DepartmentStat(BaseModel):
    name: str
    headcount: int
    onLeave: int
    avgLeave: float
    trend: str

class ScheduleEvent(BaseModel):
    id: str
    title: str
    time: str
    highlight: bool

class ComplianceAlert(BaseModel):
    id: str
    subject: str
    time: str
    start: str
    end: str
    priority: str
    audience: str
    dot: str

class AbsentEmployee(BaseModel):
    id: str
    name: str
    role: str
    dept: str
    initials: str
    color: str

class ActivityStat(BaseModel):
    id: str
    user: str
    action: str
    time: str
    avatar: str
    color: str
    icon: str

class ChecklistItem(BaseModel):
    task: str
    completed: bool

class CRMStats(BaseModel):
    totalRevenue: str
    revenueGrowth: float
    pendingRevenue: str
    collectedRevenue: str
    totalLeads: int
    newLeadsToday: int
    leadConversionRate: float
    winRateData: List[int]

class AdminDashboardResponse(BaseModel):
    attendance: AttendanceStats
    departments: List[DepartmentStat]
    schedule: List[ScheduleEvent]
    compliance: List[ComplianceAlert]
    absentEmployees: List[AbsentEmployee]
    activities: List[ActivityStat]
    checklist: List[ChecklistItem]
    crm_stats: Optional[CRMStats]
