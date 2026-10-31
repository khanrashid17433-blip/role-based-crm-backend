"""
Billing and subscription models for tenant management
"""
from beanie import Document
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from uuid import UUID, uuid4
from enum import Enum

class BillingCycle(str, Enum):
    monthly = "monthly"
    yearly = "yearly"

class SubscriptionStatus(str, Enum):
    active = "active"
    trial = "trial"
    trialing = "trialing"
    suspended = "suspended"
    cancelled = "cancelled"
    churned = "churned"
    past_due = "past_due"

class InvoiceStatus(str, Enum):
    draft = "draft"
    open = "open"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"
    partially_refunded = "partially_refunded"
    voided = "voided"

class BillingEventType(str, Enum):
    subscription_created = "subscription_created"
    subscription_updated = "subscription_updated"
    subscription_cancelled = "subscription_cancelled"
    subscription_suspended = "subscription_suspended"
    subscription_reactivated = "subscription_reactivated"
    plan_changed = "plan_changed"
    discount_applied = "discount_applied"
    trial_extended = "trial_extended"
    invoice_created = "invoice_created"
    invoice_paid = "invoice_paid"
    invoice_failed = "invoice_failed"
    refund_issued = "refund_issued"
    payment_method_updated = "payment_method_updated"
    manual_invoice_created = "manual_invoice_created"

class RefundReason(str, Enum):
    duplicate_charge = "duplicate_charge"
    fraudulent = "fraudulent"
    requested_by_customer = "requested_by_customer"
    service_not_delivered = "service_not_delivered"
    billing_error = "billing_error"
    other = "other"

class PaymentMethod(BaseModel):
    """Payment method information"""
    stripe_payment_method_id: Optional[str] = None
    last4: Optional[str] = None
    brand: Optional[str] = None  # visa, mastercard, amex, etc.
    exp_month: Optional[int] = None
    exp_year: Optional[int] = None
    country: Optional[str] = None
    is_default: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)

class TenantSubscription(Document):
    """Tenant subscription and billing information"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    
    # Plan Information
    plan_id: UUID
    plan_name: str
    billing_cycle: BillingCycle
    
    # Subscription Status
    status: SubscriptionStatus = SubscriptionStatus.active
    current_period_start: datetime
    current_period_end: datetime
    trial_start: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancel_reason: Optional[str] = None
    
    # Pricing
    base_price: float  # Base plan price
    discount_percentage: float = 0.0
    discount_reason: Optional[str] = None
    promo_code: Optional[str] = None
    final_price: float  # After discount
    currency: str = "USD"
    
    # Usage & Limits
    employee_count: int = 0
    max_employees: int
    overage_employees: int = 0
    max_admin_users: int = 5
    
    # Stripe Integration
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    payment_methods: List[PaymentMethod] = []
    
    # Billing Dates
    next_billing_date: Optional[datetime] = None
    last_billing_date: Optional[datetime] = None
    
    # Flags
    auto_renew: bool = True
    cancel_at_period_end: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    
    class Settings:
        name = "subscriptions"

class BillingEvent(Document):
    """Audit trail for all billing-related events"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    subscription_id: Optional[UUID] = None
    
    # Event Details
    event_type: BillingEventType
    description: str
    
    # Financial Impact
    amount: Optional[float] = None
    currency: str = "USD"
    
    # References
    stripe_event_id: Optional[str] = None
    invoice_id: Optional[UUID] = None
    
    # Actor Information
    performed_by: Optional[UUID] = None  # Super admin or system
    performed_by_name: Optional[str] = None
    reason: Optional[str] = None
    
    # Metadata
    metadata_json: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "billing_events"

class Invoice(Document):
    """Invoice records for billing"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    subscription_id: Optional[UUID] = None
    
    # Invoice Details
    invoice_number: str
    status: InvoiceStatus = InvoiceStatus.draft
    
    # Amounts
    subtotal: float
    discount_amount: float = 0.0
    tax_amount: float = 0.0
    total_amount: float
    currency: str = "USD"
    
    # Dates
    issue_date: date
    due_date: date
    paid_date: Optional[date] = None
    
    # Stripe Integration
    stripe_invoice_id: Optional[str] = None
    stripe_payment_intent_id: Optional[str] = None
    
    # Line Items
    line_items: List[Dict[str, Any]] = []
    
    # Files
    pdf_url: Optional[str] = None
    
    # Metadata
    is_manual: bool = False  # Manual invoice vs automated
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "invoices"

class Refund(Document):
    """Refund records"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    invoice_id: UUID
    
    # Refund Details
    amount: float
    currency: str = "USD"
    reason: RefundReason
    reason_description: Optional[str] = None
    
    # Stripe Integration
    stripe_refund_id: Optional[str] = None
    
    # Status
    status: str = "pending"  # pending, succeeded, failed
    
    # Actor
    processed_by: UUID
    processed_by_name: str
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    
    class Settings:
        name = "refunds"

class TenantModule(Document):
    """Module and feature flag configuration per tenant"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    
    # Module Configuration
    use_plan_defaults: bool = True
    
    # Core Modules
    core_hr_enabled: bool = True
    payroll_enabled: bool = False
    leave_enabled: bool = True
    attendance_enabled: bool = True
    recruitment_enabled: bool = False
    performance_enabled: bool = False
    benefits_enabled: bool = False
    compliance_enabled: bool = False
    
    # Advanced Features
    api_access_enabled: bool = False
    api_rate_limit: int = 100  # requests per minute
    white_label_enabled: bool = False
    sso_enabled: bool = False
    multi_entity_enabled: bool = False
    advanced_analytics_enabled: bool = False
    
    # White-label Settings
    custom_domain: Optional[str] = None
    brand_color: Optional[str] = None
    custom_logo_url: Optional[str] = None
    custom_email_from_name: Optional[str] = None
    
    # Feature Flags (Key-Value store for experimental features)
    feature_flags: Dict[str, Any] = {}
    
    # Limit Overrides
    max_employees_override: Optional[int] = None
    max_admin_users_override: Optional[int] = None
    max_entities_override: Optional[int] = None
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: Optional[UUID] = None
    
    class Settings:
        name = "tenant_modules"

class SSOConfiguration(Document):
    """SSO configuration for tenants"""
    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    
    # Basic Configuration
    domain: str  # Company domain for SSO
    sso_type: str  # saml, oidc, google, microsoft
    status: str = "active"  # active, inactive
    
    # SAML Configuration
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_certificate: Optional[str] = None  # PEM format
    
    # OIDC Configuration
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_discovery_url: Optional[str] = None
    
    # Attribute Mapping
    email_attribute: str = "email"
    first_name_attribute: str = "first_name"
    last_name_attribute: str = "last_name"
    
    # JIT Provisioning
    jit_provisioning_enabled: bool = False
    default_role_for_jit: Optional[str] = "employee"
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: UUID
    
    class Settings:
        name = "sso_configurations"