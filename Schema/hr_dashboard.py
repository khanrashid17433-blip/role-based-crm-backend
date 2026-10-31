from pydantic import BaseModel
from typing import List, Optional

class DashboardStats(BaseModel):
    totalEmployees: int
    activeToday: int
    newThisMonth: int
    onLeaveToday: int
    avgTenureYears: float
    attritionPct: float

class DepartmentStat(BaseModel):
    name: str
    count: int
    color: str

class PipelineStat(BaseModel):
    stage: str
    count: int
    color: str

class ApprovalStat(BaseModel):
    id: str
    type: str
    who: str
    desc: str
    time: str

class NewHireStat(BaseModel):
    id: str
    name: str
    role: str
    dept: str
    joined: str
    initials: str
    color: str

class BirthdayStat(BaseModel):
    id: str
    name: str
    when: str
    initials: str
    color: str

class ComplianceStat(BaseModel):
    id: str
    label: str
    due: str
    tone: str

class HRDashboardResponse(BaseModel):
    stats: DashboardStats
    departments: List[DepartmentStat]
    pipeline: List[PipelineStat]
    approvals: List[ApprovalStat]
    newHires: List[NewHireStat]
    birthdays: List[BirthdayStat]
    compliance: List[ComplianceStat]
