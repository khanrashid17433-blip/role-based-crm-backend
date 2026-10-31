from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List
from datetime import date
import re


# ============================================
# STEP 1: Company Profile
# ============================================

class CompanyProfileRequest(BaseModel):
    """Step 1: Company Profile"""
    
    company_logo_url: Optional[str] = Field(None, description="URL to company logo")
    company_legal_name: str = Field(..., min_length=2, max_length=200, description="Legal company name")
    trading_name: Optional[str] = Field(None, max_length=200, description="Trading/display name")
    website: Optional[str] = Field(None, description="Company website URL")
    company_registration_no: Optional[str] = Field(None, max_length=50, description="Registration number")
    
    # Address
    address_line1: str = Field(..., min_length=2, max_length=200, description="Address line 1")
    address_line2: Optional[str] = Field(None, max_length=200, description="Address line 2")
    city: str = Field(..., min_length=2, max_length=100, description="City")
    state: str = Field(..., min_length=2, max_length=100, description="State/Province")
    postal_code: str = Field(..., min_length=2, max_length=20, description="Postal code")
    country: str = Field(..., min_length=2, max_length=100, description="Country")
    
    billing_contact_email: EmailStr = Field(..., description="Billing contact email")
    vat_gst_number: Optional[str] = Field(None, max_length=50, description="VAT/GST number")
    fiscal_year_start: int = Field(..., ge=1, le=12, description="Fiscal year start month (1-12)")
    
    @validator('website')
    def validate_website(cls, v):
        """Add https:// if missing"""
        if v and not v.startswith(('http://', 'https://')):
            return f"https://{v}"
        return v
    
    @validator('billing_contact_email')
    def validate_email(cls, v):
        return v.lower()


# ============================================
# STEP 2: First Legal Entity
# ============================================

class EntityRequest(BaseModel):
    """Step 2: First Legal Entity"""
    
    entity_legal_name: str = Field(..., min_length=2, max_length=200, description="Entity legal name")
    entity_type: str = Field(..., description="Entity type: limited_company, llc, sole_trader, plc, partnership, llp")
    country_of_incorporation: str = Field(..., min_length=2, max_length=2, description="ISO country code")
    tax_employer_id: str = Field(..., min_length=5, max_length=50, description="Tax/Employer ID")
    
    # India-specific
    pf_registration_no: Optional[str] = Field(None, max_length=50, description="PF registration number")
    esi_registration_no: Optional[str] = Field(None, max_length=50, description="ESI registration number")
    
    # Location
    state_province: Optional[str] = Field(None, max_length=100, description="State/Province")
    
    # Payroll
    pay_frequency: str = Field(..., description="Pay frequency: weekly, bi_weekly, semi_monthly, monthly")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency code (USD, GBP, INR)")
    
    # Bank details (optional)
    bank_name: Optional[str] = Field(None, max_length=200, description="Bank name")
    account_number: Optional[str] = Field(None, max_length=50, description="Account number (masked)")
    routing_number: Optional[str] = Field(None, max_length=50, description="Routing/Sort/IFSC code")


# ============================================
# STEP 3: Team Invitations
# ============================================

class TeamInviteRequest(BaseModel):
    """Single team invitation"""
    
    email: EmailStr = Field(..., description="Invitee email")
    role: str = Field(..., description="Role: hr_admin, payroll_admin, recruiter, finance_viewer, it_admin")
    first_name: Optional[str] = Field(None, max_length=100, description="First name (optional)")
    last_name: Optional[str] = Field(None, max_length=100, description="Last name (optional)")


class TeamInvitationsRequest(BaseModel):
    """Step 3: Team Invitations"""
    
    invitations: List[TeamInviteRequest] = Field(..., min_items=0, max_items=10, description="List of invitations")
    skip: bool = Field(False, description="Skip this step")
    
    @validator('invitations')
    def validate_invitations(cls, v):
        """Validate unique emails"""
        emails = [inv.email.lower() for inv in v]
        if len(emails) != len(set(emails)):
            raise ValueError('Duplicate email addresses not allowed')
        return v


# ============================================
# STEP 4: Payroll Configuration
# ============================================

class PayrollConfigRequest(BaseModel):
    """Step 4: Payroll Configuration"""
    
    next_pay_date: date = Field(..., description="Next pay date")
    salary_structure_template: str = Field(..., description="Template: us_standard, uk_paye, india_ctc, custom")
    default_working_hours: int = Field(..., ge=1, le=80, description="Default working hours per week")
    overtime_rules: str = Field(..., description="Overtime rules: flsa, wtr, factories_act, custom")


# ============================================
# STEP 5: Leave Policy
# ============================================

class LeavePolicyRequest(BaseModel):
    """Step 5: Leave Policy"""
    
    leave_policy_template: str = Field(..., description="Template: us_pto, uk_statutory, india_statutory, custom")
    annual_leave_days: int = Field(..., ge=0, le=365, description="Annual leave days")
    sick_leave_days: int = Field(..., ge=0, le=365, description="Sick leave days")
    leave_year_start: int = Field(..., ge=1, le=12, description="Leave year start month")
    carry_forward_limit: int = Field(..., ge=0, le=365, description="Carry forward limit")
    public_holidays: List[str] = Field(..., min_items=1, description="List of public holiday dates")


# ============================================
# STEP 6: Completion
# ============================================

class OnboardingCompleteRequest(BaseModel):
    """Step 6: Mark onboarding as complete"""
    pass


# ============================================
# Response Schemas
# ============================================

class OnboardingProgressResponse(BaseModel):
    """Current onboarding progress"""
    
    tenant_id: str
    current_step: int
    is_completed: bool
    step_1_completed: bool
    step_2_completed: bool
    step_3_completed: bool
    step_4_completed: bool
    step_5_completed: bool
    step_6_completed: bool


class DetailedOnboardingProgressResponse(BaseModel):
    """Detailed onboarding progress with step data"""
    
    tenant_id: str
    current_step: int
    is_completed: bool
    completed_at: Optional[str] = None
    
    # Step completion flags
    step_1_completed: bool
    step_2_completed: bool
    step_3_completed: bool
    step_4_completed: bool
    step_5_completed: bool
    step_6_completed: bool
    
    # Step data (for dashboard display)
    step_1_company_profile: Optional[dict] = None
    step_2_entity: Optional[dict] = None
    step_3_team_invites: Optional['Step3TeamInvitesResponse'] = None
    step_4_payroll_config: Optional[dict] = None
    step_5_leave_policy: Optional[dict] = None
    step_6_completion: Optional[dict] = None


class InvitationMemberResponse(BaseModel):
    """Detailed invitation with member information"""
    
    id: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    status: str  # pending, accepted, expired, rejected
    expires_at: Optional[str] = None
    accepted_at: Optional[str] = None
    resent_count: int = 0
    last_resent_at: Optional[str] = None


class Step3TeamInvitesResponse(BaseModel):
    """Step 3: Team Invitations with member details"""
    
    skipped: bool
    invitations_count: int
    pending_count: int
    accepted_count: int
    members: List[InvitationMemberResponse] = []


class InvitationResponse(BaseModel):
    """Invitation details"""
    
    id: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    role: str
    status: str
    expires_at: Optional[str]
    accepted_at: Optional[str]


class InvitationListResponse(BaseModel):
    """List of invitations"""
    
    invitations: List[InvitationResponse]
    total: int
    pending_count: int
    accepted_count: int
