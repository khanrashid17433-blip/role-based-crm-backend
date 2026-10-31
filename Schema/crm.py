from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from Models.crm import LeadSource, LeadStatus, Priority, DealStage, DealPriority, ActivityType, BillingCycle, ForecastCategory

class WebFormLeadRequest(BaseModel):
    first_name: str = Field(..., max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    company_name: str = Field(..., max_length=200)
    company_size: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    notes: Optional[str] = None

class LeadManualCreateRequest(WebFormLeadRequest):
    source: LeadSource = Field(default=LeadSource.manual)
    priority: Optional[Priority] = None
    assigned_to: Optional[UUID] = None

class LeadQualifyRequest(BaseModel):
    budget_confirmed: bool
    budget_notes: Optional[str] = None
    authority_confirmed: bool
    authority_notes: Optional[str] = None
    pain_points: List[str] = Field(default_factory=list)
    timeline: str
    estimated_headcount: int
    required_regions: List[str] = Field(default_factory=list)
    current_solution: Optional[str] = None

class DemoScheduleRequest(BaseModel):
    demo_type: str
    demo_date: datetime
    demo_duration: int
    demo_meeting_link: str
    internal_attendees: List[UUID] = Field(default_factory=list)
    demo_focus_areas: List[str] = Field(default_factory=list)

class DemoCompleteRequest(BaseModel):
    demo_notes: str
    demo_outcome: str
    follow_up_date: Optional[date] = None
    next_action: Optional[str] = None
    key_concerns: Optional[str] = None
    decision_timeline: Optional[str] = None
    competitors_mentioned: Optional[str] = None

class ProposalCreateRequest(BaseModel):
    plan_id: UUID
    employees_count: int
    contract_duration: str
    discount_pct: float = 0.0
    addons: List[str] = Field(default_factory=list)
    template_id: str

class DealWonRequest(BaseModel):
    contract_signed_date: date
    go_live_date: date
    assigned_csm: UUID
    won_reason: List[str] = Field(default_factory=list)
    auto_provision_tenant: bool = True

class DealLostRequest(BaseModel):
    lost_reason: str
    competitor_chosen: Optional[str] = None
    features_gap: Optional[str] = None
    reengage_date: Optional[date] = None
    lost_notes: str

class LeadUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None
    company_size: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    source: Optional[LeadSource] = None
    priority: Optional[Priority] = None
    assigned_to: Optional[UUID] = None
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    tags: Optional[List[str]] = None
    website: Optional[str] = None
    job_title: Optional[str] = None

class LeadAssignRequest(BaseModel):
    assigned_to: Optional[UUID] = None
    lead_ids: Optional[List[UUID]] = None

class LeadEmailRequest(BaseModel):
    subject: str
    message: str
    template: Optional[str] = None

class LeadActivityCreateRequest(BaseModel):
    activity_type: ActivityType
    subject: str
    body: Optional[str] = None
    outcome: Optional[str] = None
    direction: Optional[str] = None
    duration: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class LeadNoteCreateRequest(BaseModel):
    text: str
    is_pinned: bool = False
    mentions: Optional[List[UUID]] = None
    attachments: Optional[List[str]] = None

class LeadDemoScheduleRequest(BaseModel):
    title: Optional[str] = None
    scheduled_time: datetime
    duration_minutes: Optional[int] = 30
    focus_areas: List[str] = Field(default_factory=list)
    internal_attendees: Optional[List[UUID]] = None
    customer_emails: Optional[List[str]] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None
    follow_up_date: Optional[datetime] = None

class LeadProposalCreateRequest(BaseModel):
    title: Optional[str] = None
    tier: str
    employees_count: int
    discount_pct: float = 0.0
    plan_details: Optional[dict] = None

class LeadDocumentUploadRequest(BaseModel):
    name: str
    file_size: str
    file_type: Optional[str] = None
    file_url: Optional[str] = None

class FollowUpCreateRequest(BaseModel):
    purpose: str
    scheduled_date: datetime
    reminder_date: Optional[datetime] = None
    assigned_to: Optional[UUID] = None
    notes: Optional[str] = None

class CallLogRequest(BaseModel):
    subject: str
    duration: str
    outcome: Optional[str] = None
    notes: Optional[str] = None
    direction: str = "outbound"

class MeetingScheduleRequest(BaseModel):
    title: str
    scheduled_time: datetime
    duration_minutes: int = 30
    meeting_link: Optional[str] = None
    attendees: Optional[List[str]] = None
    notes: Optional[str] = None
    outcome: Optional[str] = None

class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Priority = Field(default=Priority.warm)
    assigned_to: Optional[UUID] = None
    reminder_at: Optional[datetime] = None

class LeadStatusChangeRequest(BaseModel):
    status: LeadStatus
    reason: Optional[str] = None

class LeadArchiveRequest(BaseModel):
    action: str = "archive"

class LeadImportRow(BaseModel):
    first_name: str = Field(..., max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    company_name: str = Field(..., max_length=200)
    company_size: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    source: Optional[str] = "manual"
    priority: Optional[str] = None
    notes: Optional[str] = None
    job_title: Optional[str] = None

class LeadImportRequest(BaseModel):
    leads: List[LeadImportRow]

# ════════════════════════════════════════════
# DEAL SCHEMAS
# ════════════════════════════════════════════

class DealCreateRequest(BaseModel):
    deal_name: str = Field(..., min_length=1, max_length=200)
    pipeline: str = Field(default="Sales Pipeline", max_length=100)
    stage: DealStage = Field(default=DealStage.new)
    deal_value: float = Field(default=0, ge=0)
    currency: str = Field(default="USD", max_length=3)
    close_date: Optional[str] = None
    probability: Optional[int] = None
    priority: DealPriority = Field(default=DealPriority.medium)
    
    # Associated Records
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    lead_id: Optional[str] = None
    
    # Assignment
    owner_id: Optional[str] = None
    sales_rep_id: Optional[str] = None
    team: Optional[str] = None
    
    # Subscription Details
    plan_id: Optional[str] = None
    employee_count: Optional[int] = None
    billing_cycle: Optional[BillingCycle] = None
    contract_duration: Optional[int] = None
    expected_mrr: Optional[float] = None
    expected_arr: Optional[float] = None
    
    # Forecasting
    forecast_category: Optional[ForecastCategory] = None
    notes: Optional[str] = None

class DealUpdateRequest(BaseModel):
    deal_name: Optional[str] = Field(None, min_length=1, max_length=200)
    pipeline: Optional[str] = None
    stage: Optional[DealStage] = None
    deal_value: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    close_date: Optional[str] = None
    probability: Optional[int] = None
    priority: Optional[DealPriority] = None
    contact_id: Optional[str] = None
    company_id: Optional[str] = None
    lead_id: Optional[str] = None
    owner_id: Optional[str] = None
    sales_rep_id: Optional[str] = None
    team: Optional[str] = None
    plan_id: Optional[str] = None
    employee_count: Optional[int] = None
    billing_cycle: Optional[BillingCycle] = None
    contract_duration: Optional[int] = None
    expected_mrr: Optional[float] = None
    expected_arr: Optional[float] = None
    forecast_category: Optional[ForecastCategory] = None
    notes: Optional[str] = None