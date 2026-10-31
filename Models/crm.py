from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import enum

# ==========================================
# ENUMS
# ==========================================

class LeadSource(str, enum.Enum):
    email = "email"
    ppc_google = "ppc_google"
    meta_ads = "meta_ads"
    local_listing = "local_listing"
    web_form = "web_form"
    referral = "referral"
    linkedin = "linkedin"
    manual = "manual"

class LeadStatus(str, enum.Enum):
    new = "new"
    contacted = "contacted"
    qualified = "qualified"
    demo_scheduled = "demo_scheduled"
    demo_done = "demo_done"
    proposal_sent = "proposal_sent"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"
    dormant = "dormant"
    converted = "converted"

class Priority(str, enum.Enum):
    hot = "hot"
    warm = "warm"
    cold = "cold"

class DealStage(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    demo_scheduled = "demo_scheduled"
    demo_completed = "demo_completed"
    proposal_sent = "proposal_sent"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"
    qualified_to_buy = "qualified_to_buy"
    presentation_scheduled = "presentation_scheduled"
    appointment_scheduled = "appointment_scheduled"

class DealPriority(str, enum.Enum):
    hot = "hot"
    medium = "medium"
    low = "low"

class BillingCycle(str, enum.Enum):
    monthly = "monthly"
    annual = "annual"

class ForecastCategory(str, enum.Enum):
    pipeline = "pipeline"
    best_case = "best_case"
    commit = "commit"
    closed = "closed"

class ActivityType(str, enum.Enum):
    call = "call"
    email = "email"
    meeting = "meeting"
    demo = "demo"
    note = "note"
    task = "task"

class TimelineActivityType(str, enum.Enum):
    deal_created = "deal_created"
    deal_updated = "deal_updated"
    stage_changed = "stage_changed"
    owner_changed = "owner_changed"
    contact_associated = "contact_associated"
    proposal_sent = "proposal_sent"
    negotiation_started = "negotiation_started"
    deal_won = "deal_won"
    deal_lost = "deal_lost"
    note_added = "note_added"
    email_sent = "email_sent"
    call_logged = "call_logged"
    meeting_scheduled = "meeting_scheduled"
    task_created = "task_created"
    document_uploaded = "document_uploaded"
    custom = "custom"

# ==========================================
# MODELS
# ==========================================

class CrmLead(Document):
    """Lead captured for the B2B HRMS platform"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    
    # Contact Details
    first_name: str = Field(..., max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    job_title: Optional[str] = Field(None, max_length=100)
    
    # Company Details
    company_name: str = Field(..., max_length=200)
    company_size: Optional[str] = Field(None, max_length=50)
    industry: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    
    # Source & Attribution
    source: LeadSource = Field(default=LeadSource.manual)
    source_detail: Optional[str] = Field(None, max_length=200)
    campaign_id: Optional[str] = None
    ad_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    gclid: Optional[str] = None
    fb_lead_id: Optional[str] = None
    li_lead_id: Optional[str] = None
    
    # UTM
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    
    referrer_tenant_id: Optional[UUID] = None
    
    # Status & Assignment
    status: LeadStatus = Field(default=LeadStatus.new)
    assigned_to: Optional[UUID] = None
    priority: Optional[Priority] = None
    notes: Optional[str] = None
    
    # Qualification (BANT)
    budget_confirmed: bool = False
    budget_notes: Optional[str] = None
    authority_confirmed: bool = False
    authority_notes: Optional[str] = None
    pain_points: List[str] = Field(default_factory=list)
    timeline: Optional[str] = None
    estimated_headcount: Optional[int] = None
    current_solution: Optional[str] = None
    required_regions: List[str] = Field(default_factory=list)
    qualification_score: int = Field(default=0)
    
    # HubSpot CRM detail fields
    website: Optional[str] = Field(None, max_length=200)
    tags: List[str] = Field(default_factory=list)
    company_logo: Optional[str] = None
    lifecycle_stage: str = Field(default="lead")
    last_activity: Optional[datetime] = None
    notes_list: List[Dict[str, Any]] = Field(default_factory=list)
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    proposals: List[Dict[str, Any]] = Field(default_factory=list)
    demos: List[Dict[str, Any]] = Field(default_factory=list)
    audit_logs: List[Dict[str, Any]] = Field(default_factory=list)
    
    # ---- Demo Management flat fields (source of truth for calendar) ----
    demo_date: Optional[datetime] = None
    demo_duration: Optional[int] = Field(None, description="Duration in minutes")
    demo_meeting_link: Optional[str] = None
    demo_focus_areas: List[str] = Field(default_factory=list)
    demo_outcome: Optional[str] = None
    demo_notes: Optional[str] = None
    
    # Conversion Tracking
    is_converted: bool = Field(default=False)
    converted_contact_id: Optional[UUID] = None
    converted_at: Optional[datetime] = None
    converted_by: Optional[UUID] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_leads"
        indexes = ["tenant_id", "email", "status", "assigned_to", "source"]

class CrmDeal(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    deal_name: str = Field(..., max_length=200)
    pipeline: str = Field(default="Sales Pipeline", max_length=100)
    stage: DealStage = Field(default=DealStage.new)
    deal_value: float = Field(default=0)
    currency: str = Field(default="USD", max_length=3)
    close_date: Optional[date] = None
    probability: int = Field(default=10, ge=0, le=100)
    priority: DealPriority = Field(default=DealPriority.medium)
    
    # Associated Records
    contact_id: Optional[UUID] = None
    company_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    
    # Assignment
    owner_id: Optional[UUID] = None
    sales_rep_id: Optional[UUID] = None
    team: Optional[str] = None
    
    # Subscription Details
    plan_id: Optional[UUID] = None
    employee_count: Optional[int] = None
    billing_cycle: Optional[BillingCycle] = None
    contract_duration: Optional[int] = None  # months
    expected_mrr: Optional[float] = None
    expected_arr: Optional[float] = None
    
    # Forecasting
    forecast_category: Optional[ForecastCategory] = None
    notes: Optional[str] = None
    
    # Legacy / Additional fields preserved
    headcount_estimate: Optional[int] = None
    assigned_to: Optional[UUID] = None
    demo_type: Optional[str] = None
    demo_date: Optional[datetime] = None
    demo_duration: Optional[int] = None
    demo_meeting_link: Optional[str] = None
    demo_focus_areas: List[str] = Field(default_factory=list)
    demo_notes: Optional[str] = None
    demo_outcome: Optional[str] = None
    contract_signed_date: Optional[date] = None
    go_live_date: Optional[date] = None
    assigned_csm: Optional[UUID] = None
    won_reason: List[str] = Field(default_factory=list)
    lost_reason: Optional[str] = None
    competitor_chosen: Optional[str] = None
    lost_notes: Optional[str] = None
    reengage_date: Optional[date] = None
    contract_status: Optional[str] = None
    contract_sent_date: Optional[date] = None
    contract_file: Optional[str] = None
    contract_version: Optional[str] = None
    base_price: int = 0
    discount_pct: float = 0.0
    final_price: int = 0
    pricing_breakdown: List[Dict[str, Any]] = Field(default_factory=list)
    payment_type: Optional[str] = None
    payment_schedule: List[Dict[str, Any]] = Field(default_factory=list)
    legal_review_status: Optional[str] = None
    legal_reviewer: Optional[str] = None
    legal_notes: Optional[str] = None
    legal_reviewed_date: Optional[date] = None
    approval_status: Optional[str] = None
    approvers: List[Dict[str, Any]] = Field(default_factory=list)
    days_in_stage: int = 0
    source: Optional[str] = None
    
    # Timestamps & Soft Delete
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None

    @property
    def name(self) -> str:
        return self.deal_name

    @name.setter
    def name(self, value: str):
        self.deal_name = value

    @property
    def probability_pct(self) -> int:
        return self.probability

    @probability_pct.setter
    def probability_pct(self, value: int):
        self.probability = value

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }

    class Settings:
        name = "crm_deals"
        indexes = ["tenant_id", "stage", "owner_id", "contact_id", "lead_id", "deleted_at"]

class CrmActivity(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    lead_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    
    activity_type: ActivityType
    subject: str = Field(..., max_length=200)
    body: Optional[str] = None
    outcome: Optional[str] = None
    direction: Optional[str] = None
    duration: Optional[str] = None
    
    scheduled_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_by: UUID
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_activities"
        indexes = ["tenant_id", "lead_id", "deal_id", "contact_id"]

class CrmTimelineActivity(Document):
    """Stores human-readable timeline entries for deals"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    deal_id: UUID
    activity_type: TimelineActivityType
    title: str = Field(..., max_length=300)
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_by: UUID
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_timeline_activities"
        indexes = ["tenant_id", "deal_id", "activity_type"]

# CrmTask has been moved to Models/crm_task.py for enhanced HubSpot-style features

class CrmProposal(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    deal_id: UUID
    
    template_id: Optional[str] = None
    status: str = Field(default="draft")
    
    value: int
    currency: str = Field(..., max_length=3)
    terms_months: int = 12
    discount_pct: float = 0.0
    
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    signed_at: Optional[datetime] = None
    
    file_url: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_proposals"
        indexes = ["tenant_id", "deal_id"]

class CrmClient(Document):
    """Client created from won deal"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    
    company_name: str = Field(..., max_length=200)
    industry: Optional[str] = Field(None, max_length=100)
    region: Optional[str] = Field(None, max_length=100)
    
    contact_name: str = Field(..., max_length=100)
    email: EmailStr
    phone: Optional[str] = Field(None, max_length=20)
    location: Optional[str] = Field(None, max_length=100)
    
    deal_value: int = 0
    currency: str = Field(default="USD", max_length=3)
    deal_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    
    assigned_csm: Optional[UUID] = None
    account_status: str = Field(default="active")
    
    contract_signed_date: Optional[date] = None
    go_live_date: Optional[date] = None
    renewal_date: Optional[date] = None
    
    notes: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_clients"
        indexes = ["tenant_id", "email", "deal_id", "lead_id", "account_status"]

class CrmPipeline(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    name: str = "Sales Pipeline"
    stages: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_pipeline"
        indexes = ["tenant_id"]

class CrmDealStageHistory(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    deal_id: UUID
    old_stage: str
    new_stage: str
    changed_by: UUID
    changed_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_deal_stage_history"
        indexes = ["tenant_id", "deal_id"]

class CrmDealAuditLog(Document):
    id: UUID = Field(default_factory=uuid4, alias="_id")
    tenant_id: UUID
    deal_id: UUID
    user_id: UUID
    action: str
    details: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "crm_deal_audit_logs"
        indexes = ["tenant_id", "deal_id", "timestamp"]