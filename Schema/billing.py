"""
Billing and subscription schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID
from enum import Enum

from Models.billing import BillingCycle, SubscriptionStatus, InvoiceStatus, RefundReason

# Request Schemas
class PlanChangeRequest(BaseModel):
    new_plan_id: UUID
    change_immediately: bool = True

class DiscountRequest(BaseModel):
    discount_percentage: float = Field(..., ge=0, le=100)
    reason: str

class TrialExtensionRequest(BaseModel):
    extension_days: int = Field(..., ge=1, le=60)
    reason: str

class SubscriptionStatusRequest(BaseModel):
    status: SubscriptionStatus
    reason: Optional[str] = None

class ManualInvoiceRequest(BaseModel):
    amount: float = Field(..., gt=0)
    description: str
    due_days: int = Field(default=30, ge=1, le=365)

class RefundRequest(BaseModel):
    invoice_id: UUID
    amount: float = Field(..., gt=0)
    reason: RefundReason
    reason_description: Optional[str] = None

class ModuleUpdateRequest(BaseModel):
    use_plan_defaults: Optional[bool] = None
    core_hr_enabled: Optional[bool] = None
    payroll_enabled: Optional[bool] = None
    leave_enabled: Optional[bool] = None
    attendance_enabled: Optional[bool] = None
    recruitment_enabled: Optional[bool] = None
    performance_enabled: Optional[bool] = None
    benefits_enabled: Optional[bool] = None
    compliance_enabled: Optional[bool] = None
    api_access_enabled: Optional[bool] = None
    api_rate_limit: Optional[int] = None
    white_label_enabled: Optional[bool] = None
    sso_enabled: Optional[bool] = None
    multi_entity_enabled: Optional[bool] = None
    advanced_analytics_enabled: Optional[bool] = None

class FeatureFlagsRequest(BaseModel):
    feature_flags: Dict[str, Any]

class WhiteLabelRequest(BaseModel):
    custom_domain: Optional[str] = None
    brand_color: Optional[str] = None
    custom_logo_url: Optional[str] = None
    custom_email_from_name: Optional[str] = None

class LimitOverrideRequest(BaseModel):
    max_employees_override: Optional[int] = None
    max_admin_users_override: Optional[int] = None
    max_entities_override: Optional[int] = None

class SSOConfigurationRequest(BaseModel):
    domain: str
    sso_type: str  # saml, oidc, google, microsoft
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_certificate: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    email_attribute: str = "email"
    first_name_attribute: str = "first_name"
    last_name_attribute: str = "last_name"
    jit_provisioning_enabled: bool = False
    default_role_for_jit: Optional[str] = "employee"

# Response Schemas
class PaymentMethodResponse(BaseModel):
    stripe_payment_method_id: Optional[str]
    last4: Optional[str]
    brand: Optional[str]
    exp_month: Optional[int]
    exp_year: Optional[int]
    country: Optional[str]
    is_default: bool
    created_at: datetime

class SubscriptionResponse(BaseModel):
    id: str
    tenant_id: str
    plan_id: str
    plan_name: str
    billing_cycle: BillingCycle
    status: SubscriptionStatus
    current_period_start: datetime
    current_period_end: datetime
    trial_ends_at: Optional[datetime]
    base_price: float
    discount_percentage: float
    discount_reason: Optional[str]
    promo_code: Optional[str]
    final_price: float
    currency: str
    employee_count: int
    max_employees: int
    max_admin_users: int
    stripe_customer_id: Optional[str]
    stripe_subscription_id: Optional[str]
    payment_methods: List[PaymentMethodResponse]
    next_billing_date: Optional[datetime]
    last_billing_date: Optional[datetime]
    auto_renew: bool
    cancel_at_period_end: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class BillingEventResponse(BaseModel):
    id: str
    tenant_id: str
    subscription_id: Optional[str]
    event_type: str
    description: str
    amount: Optional[float]
    currency: str
    performed_by: Optional[str]
    performed_by_name: Optional[str]
    reason: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    
    class Config:
        from_attributes = True

class InvoiceResponse(BaseModel):
    id: str
    tenant_id: str
    subscription_id: Optional[str]
    invoice_number: str
    status: InvoiceStatus
    subtotal: float
    discount_amount: float
    tax_amount: float
    total_amount: float
    currency: str
    issue_date: date
    due_date: date
    paid_date: Optional[date]
    stripe_invoice_id: Optional[str]
    stripe_payment_intent_id: Optional[str]
    line_items: List[Dict[str, Any]]
    pdf_url: Optional[str]
    is_manual: bool
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class RefundResponse(BaseModel):
    id: str
    tenant_id: str
    invoice_id: str
    amount: float
    currency: str
    reason: RefundReason
    reason_description: Optional[str]
    stripe_refund_id: Optional[str]
    status: str
    processed_by: str
    processed_by_name: str
    created_at: datetime
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ModuleResponse(BaseModel):
    id: str
    tenant_id: str
    use_plan_defaults: bool
    core_hr_enabled: bool
    payroll_enabled: bool
    leave_enabled: bool
    attendance_enabled: bool
    recruitment_enabled: bool
    performance_enabled: bool
    benefits_enabled: bool
    compliance_enabled: bool
    api_access_enabled: bool
    api_rate_limit: int
    white_label_enabled: bool
    sso_enabled: bool
    multi_entity_enabled: bool
    advanced_analytics_enabled: bool
    custom_domain: Optional[str]
    brand_color: Optional[str]
    custom_logo_url: Optional[str]
    custom_email_from_name: Optional[str]
    feature_flags: Dict[str, Any]
    max_employees_override: Optional[int]
    max_admin_users_override: Optional[int]
    max_entities_override: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class SSOConfigurationResponse(BaseModel):
    id: str
    tenant_id: str
    domain: str
    sso_type: str
    status: str
    saml_entity_id: Optional[str]
    saml_sso_url: Optional[str]
    oidc_client_id: Optional[str]
    oidc_discovery_url: Optional[str]
    email_attribute: str
    first_name_attribute: str
    last_name_attribute: str
    jit_provisioning_enabled: bool
    default_role_for_jit: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class BillingHistoryResponse(BaseModel):
    invoices: List[InvoiceResponse]
    total: int
    page: int
    per_page: int
    has_more: bool

class BillingEventsResponse(BaseModel):
    events: List[BillingEventResponse]
    total: int
    page: int
    per_page: int
    has_more: bool

class SSOConfigurationsResponse(BaseModel):
    configurations: List[SSOConfigurationResponse]
    total: int