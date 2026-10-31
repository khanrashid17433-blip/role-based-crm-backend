"""
Billing and subscription management routes for super admin
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from uuid import UUID

from Services.billing_service import BillingService
from Services.module_service import ModuleService, SSOService
from Schema.billing import (
    PlanChangeRequest, DiscountRequest, TrialExtensionRequest, SubscriptionStatusRequest,
    ManualInvoiceRequest, RefundRequest, ModuleUpdateRequest, FeatureFlagsRequest,
    WhiteLabelRequest, LimitOverrideRequest, SSOConfigurationRequest,
    SubscriptionResponse, BillingEventResponse, InvoiceResponse, RefundResponse,
    ModuleResponse, SSOConfigurationResponse, BillingHistoryResponse, BillingEventsResponse,
    SSOConfigurationsResponse
)
from Utility.auth_helpers import verify_platform_admin, verify_tenant_admin
from Utility.exceptions import ValidationError, NotFoundError

router = APIRouter()

# ============================================
# SUBSCRIPTION & BILLING TAB ENDPOINTS
# ============================================

@router.get("/api/super-admin/tenants/{tenant_id}/subscription", response_model=SubscriptionResponse)
async def get_tenant_subscription(
    tenant_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Get current subscription details for tenant
    
    Returns complete subscription information including:
    - Current plan, billing cycle, pricing
    - Employee count vs plan limits
    - Payment methods and Stripe integration
    - Trial information and billing dates
    """
    try:
        subscription = await BillingService.get_tenant_subscription(tenant_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        return SubscriptionResponse(
            id=str(subscription.id),
            tenant_id=str(subscription.tenant_id),
            plan_id=str(subscription.plan_id),
            plan_name=subscription.plan_name,
            billing_cycle=subscription.billing_cycle,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            trial_ends_at=subscription.trial_ends_at,
            base_price=subscription.base_price,
            discount_percentage=subscription.discount_percentage,
            discount_reason=subscription.discount_reason,
            promo_code=subscription.promo_code,
            final_price=subscription.final_price,
            currency=subscription.currency,
            employee_count=subscription.employee_count,
            max_employees=subscription.max_employees,
            max_admin_users=subscription.max_admin_users,
            stripe_customer_id=subscription.stripe_customer_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            payment_methods=[],  # TODO: Implement payment method retrieval
            next_billing_date=subscription.next_billing_date,
            last_billing_date=subscription.last_billing_date,
            auto_renew=subscription.auto_renew,
            cancel_at_period_end=subscription.cancel_at_period_end,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve subscription: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/subscription/change-plan")
async def change_tenant_plan(
    tenant_id: UUID,
    request: PlanChangeRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Change subscription plan
    
    Options:
    - Immediate change (prorated)
    - Change at period end
    
    Shows revenue impact preview in response
    """
    try:
        subscription = await BillingService.change_plan(
            tenant_id=tenant_id,
            new_plan_id=request.new_plan_id,
            change_immediately=request.change_immediately,
            performed_by=admin_user.id
        )
        
        return {
            "message": "Plan change successful" if request.change_immediately else "Plan change scheduled",
            "subscription": SubscriptionResponse.model_validate(subscription),
            "effective_date": subscription.updated_at if request.change_immediately else subscription.current_period_end
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to change plan: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/subscription/apply-discount")
async def apply_discount(
    tenant_id: UUID,
    request: DiscountRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Apply discount to subscription
    
    Supports 0-100% discount with reason tracking
    Approval gate for discounts > 30% (logged for review)
    """
    try:
        # Check if discount requires approval
        if request.discount_percentage > 30:
            # Log high-value discount for approval tracking
            pass  # TODO: Implement approval workflow
        
        subscription = await BillingService.apply_discount(
            tenant_id=tenant_id,
            discount_percentage=request.discount_percentage,
            reason=request.reason,
            performed_by=admin_user.id
        )
        
        return {
            "message": "Discount applied successfully",
            "subscription": SubscriptionResponse.model_validate(subscription),
            "requires_approval": request.discount_percentage > 30
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply discount: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/subscription/extend-trial")
async def extend_trial(
    tenant_id: UUID,
    request: TrialExtensionRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Extend trial period
    
    Max extension: 60 days per instance
    Requires reason and is logged
    """
    try:
        subscription = await BillingService.extend_trial(
            tenant_id=tenant_id,
            extension_days=request.extension_days,
            reason=request.reason,
            performed_by=admin_user.id
        )
        
        return {
            "message": f"Trial extended by {request.extension_days} days",
            "subscription": SubscriptionResponse.model_validate(subscription),
            "new_trial_end": subscription.trial_ends_at
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extend trial: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/subscription/status")
async def update_subscription_status(
    tenant_id: UUID,
    request: SubscriptionStatusRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Update subscription status
    
    Actions:
    - Suspend (immediate read-only lockout)
    - Unsuspend
    - Cancel (at period end)
    - Cancel Immediately
    - Mark as Churned
    - Reactivate
    """
    try:
        subscription = await BillingService.update_subscription_status(
            tenant_id=tenant_id,
            new_status=request.status,
            reason=request.reason,
            performed_by=admin_user.id
        )
        
        return {
            "message": f"Subscription status updated to {request.status}",
            "subscription": SubscriptionResponse.model_validate(subscription)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update status: {str(e)}")

@router.get("/api/super-admin/tenants/{tenant_id}/billing-history", response_model=BillingHistoryResponse)
async def get_billing_history(
    tenant_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    admin_user = Depends(verify_platform_admin)
):
    """
    Get billing history for tenant
    
    Returns table with:
    - Date, Invoice #, Amount, Status
    - Stripe Invoice ID, PDF download link
    """
    try:
        invoices, total = await BillingService.get_billing_history(
            tenant_id=tenant_id,
            page=page,
            per_page=per_page
        )
        
        invoice_responses = [
            InvoiceResponse(
                id=str(invoice.id),
                tenant_id=str(invoice.tenant_id),
                subscription_id=str(invoice.subscription_id) if invoice.subscription_id else None,
                invoice_number=invoice.invoice_number,
                status=invoice.status,
                subtotal=invoice.subtotal,
                discount_amount=invoice.discount_amount,
                tax_amount=invoice.tax_amount,
                total_amount=invoice.total_amount,
                currency=invoice.currency,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                paid_date=invoice.paid_date,
                stripe_invoice_id=invoice.stripe_invoice_id,
                stripe_payment_intent_id=invoice.stripe_payment_intent_id,
                line_items=invoice.line_items,
                pdf_url=invoice.pdf_url,
                is_manual=invoice.is_manual,
                notes=invoice.notes,
                created_at=invoice.created_at,
                updated_at=invoice.updated_at
            )
            for invoice in invoices
        ]
        
        return BillingHistoryResponse(
            invoices=invoice_responses,
            total=total,
            page=page,
            per_page=per_page,
            has_more=(page * per_page) < total
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve billing history: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/manual-invoice")
async def create_manual_invoice(
    tenant_id: UUID,
    request: ManualInvoiceRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Generate manual invoice
    
    For custom amounts (e.g., implementation fees)
    PDF generated automatically
    """
    try:
        invoice = await BillingService.create_manual_invoice(
            tenant_id=tenant_id,
            amount=request.amount,
            description=request.description,
            due_days=request.due_days,
            created_by=admin_user.id
        )
        
        return {
            "message": "Manual invoice created successfully",
            "invoice": InvoiceResponse.model_validate(invoice)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create manual invoice: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/refund")
async def issue_refund(
    tenant_id: UUID,
    request: RefundRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Issue full or partial refund
    
    Requires amount, reason, and confirmation
    Creates billing_event: refund_issued
    """
    try:
        refund = await BillingService.issue_refund(
            tenant_id=tenant_id,
            invoice_id=request.invoice_id,
            amount=request.amount,
            reason=request.reason,
            reason_description=request.reason_description,
            processed_by=admin_user.id
        )
        
        return {
            "message": "Refund issued successfully",
            "refund": RefundResponse.model_validate(refund)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to issue refund: {str(e)}")

@router.get("/api/super-admin/tenants/{tenant_id}/billing-events", response_model=BillingEventsResponse)
async def get_billing_events(
    tenant_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin_user = Depends(verify_platform_admin)
):
    """
    Get billing events audit trail for tenant
    """
    try:
        events, total = await BillingService.get_billing_events(
            tenant_id=tenant_id,
            page=page,
            per_page=per_page
        )
        
        event_responses = [
            BillingEventResponse(
                id=str(event.id),
                tenant_id=str(event.tenant_id),
                subscription_id=str(event.subscription_id) if event.subscription_id else None,
                event_type=event.event_type.value,
                description=event.description,
                amount=event.amount,
                currency=event.currency,
                performed_by=str(event.performed_by) if event.performed_by else None,
                performed_by_name=event.performed_by_name,
                reason=event.reason,
                metadata=event.metadata,
                created_at=event.created_at
            )
            for event in events
        ]
        
        return BillingEventsResponse(
            events=event_responses,
            total=total,
            page=page,
            per_page=per_page,
            has_more=(page * per_page) < total
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve billing events: {str(e)}")

# ============================================
# MODULES & FEATURE FLAGS TAB ENDPOINTS
# ============================================

@router.get("/api/super-admin/tenants/{tenant_id}/modules", response_model=ModuleResponse)
async def get_tenant_modules(
    tenant_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Get module configuration for tenant
    
    Shows which modules and features are enabled
    """
    try:
        modules = await ModuleService.get_tenant_modules(tenant_id)
        
        return ModuleResponse(
            id=str(modules.id),
            tenant_id=str(modules.tenant_id),
            use_plan_defaults=modules.use_plan_defaults,
            core_hr_enabled=modules.core_hr_enabled,
            payroll_enabled=modules.payroll_enabled,
            leave_enabled=modules.leave_enabled,
            attendance_enabled=modules.attendance_enabled,
            recruitment_enabled=modules.recruitment_enabled,
            performance_enabled=modules.performance_enabled,
            benefits_enabled=modules.benefits_enabled,
            compliance_enabled=modules.compliance_enabled,
            api_access_enabled=modules.api_access_enabled,
            api_rate_limit=modules.api_rate_limit,
            white_label_enabled=modules.white_label_enabled,
            sso_enabled=modules.sso_enabled,
            multi_entity_enabled=modules.multi_entity_enabled,
            advanced_analytics_enabled=modules.advanced_analytics_enabled,
            custom_domain=modules.custom_domain,
            brand_color=modules.brand_color,
            custom_logo_url=modules.custom_logo_url,
            custom_email_from_name=modules.custom_email_from_name,
            feature_flags=modules.feature_flags,
            max_employees_override=modules.max_employees_override,
            max_admin_users_override=modules.max_admin_users_override,
            max_entities_override=modules.max_entities_override,
            created_at=modules.created_at,
            updated_at=modules.updated_at
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve modules: {str(e)}")

@router.put("/api/super-admin/tenants/{tenant_id}/modules")
async def update_tenant_modules(
    tenant_id: UUID,
    request: ModuleUpdateRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Update tenant module configuration
    
    Control which modules and features are enabled
    Override plan defaults if needed
    """
    try:
        modules = await ModuleService.update_tenant_modules(
            tenant_id=tenant_id,
            module_data=request.dict(exclude_unset=True),
            updated_by=admin_user.id
        )
        
        return {
            "message": "Modules updated successfully",
            "modules": ModuleResponse.model_validate(modules)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update modules: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/modules/feature-flags")
async def update_feature_flags(
    tenant_id: UUID,
    request: FeatureFlagsRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Update feature flags for tenant
    
    Key-value feature flag editor for experimental features
    Changes take effect within 60 seconds (Redis cache TTL)
    """
    try:
        modules = await ModuleService.update_feature_flags(
            tenant_id=tenant_id,
            feature_flags=request.feature_flags,
            updated_by=admin_user.id
        )
        
        return {
            "message": "Feature flags updated successfully",
            "feature_flags": modules.feature_flags
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update feature flags: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/modules/white-label")
async def update_white_label_settings(
    tenant_id: UUID,
    request: WhiteLabelRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Update white-label settings
    
    Only for Enterprise or manually granted tenants:
    - Custom domain (CNAME setup)
    - Brand color picker
    - Custom logo upload
    - Custom email from-name
    """
    try:
        modules = await ModuleService.update_white_label_settings(
            tenant_id=tenant_id,
            white_label_data=request.dict(exclude_unset=True),
            updated_by=admin_user.id
        )
        
        return {
            "message": "White-label settings updated successfully",
            "white_label": {
                "custom_domain": modules.custom_domain,
                "brand_color": modules.brand_color,
                "custom_logo_url": modules.custom_logo_url,
                "custom_email_from_name": modules.custom_email_from_name
            }
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update white-label settings: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/modules/limits")
async def update_limit_overrides(
    tenant_id: UUID,
    request: LimitOverrideRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Override plan limits
    
    Useful for Enterprise custom contracts:
    - max_employees
    - max_admin_users  
    - max_entities
    """
    try:
        modules = await ModuleService.update_limit_overrides(
            tenant_id=tenant_id,
            max_employees=request.max_employees_override,
            max_admin_users=request.max_admin_users_override,
            max_entities=request.max_entities_override,
            updated_by=admin_user.id
        )
        
        return {
            "message": "Limit overrides updated successfully",
            "limits": {
                "max_employees_override": modules.max_employees_override,
                "max_admin_users_override": modules.max_admin_users_override,
                "max_entities_override": modules.max_entities_override
            }
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update limits: {str(e)}")

# ============================================
# SSO CONFIGURATION TAB ENDPOINTS
# ============================================

@router.get("/api/super-admin/tenants/{tenant_id}/sso", response_model=SSOConfigurationsResponse)
async def get_sso_configurations(
    tenant_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Get all SSO configurations for tenant
    
    Shows table of all configured SSO providers:
    - Domain, SSO Type, Status, Created At
    """
    try:
        configurations = await SSOService.get_sso_configurations(tenant_id)
        
        config_responses = [
            SSOConfigurationResponse(
                id=str(config.id),
                tenant_id=str(config.tenant_id),
                domain=config.domain,
                sso_type=config.sso_type,
                status=config.status,
                saml_entity_id=config.saml_entity_id,
                saml_sso_url=config.saml_sso_url,
                oidc_client_id=config.oidc_client_id,
                oidc_discovery_url=config.oidc_discovery_url,
                email_attribute=config.email_attribute,
                first_name_attribute=config.first_name_attribute,
                last_name_attribute=config.last_name_attribute,
                jit_provisioning_enabled=config.jit_provisioning_enabled,
                default_role_for_jit=config.default_role_for_jit,
                created_at=config.created_at,
                updated_at=config.updated_at
            )
            for config in configurations
        ]
        
        return SSOConfigurationsResponse(
            configurations=config_responses,
            total=len(config_responses)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve SSO configurations: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/sso")
async def create_sso_configuration(
    tenant_id: UUID,
    request: SSOConfigurationRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Add SSO configuration
    
    Form supports:
    - Domain, SSO Type (SAML/OIDC/Google/Microsoft)
    - SAML: Entity ID, SSO URL, Certificate (PEM upload)
    - OIDC: Client ID, Secret, Discovery URL
    - Attribute mapping, JIT Provisioning, Default Role
    """
    try:
        sso_config = await SSOService.create_sso_configuration(
            tenant_id=tenant_id,
            sso_data=request.dict(exclude_unset=True),
            created_by=admin_user.id
        )
        
        return {
            "message": "SSO configuration created successfully",
            "configuration": SSOConfigurationResponse.model_validate(sso_config)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create SSO configuration: {str(e)}")

@router.put("/api/super-admin/tenants/{tenant_id}/sso/{sso_id}")
async def update_sso_configuration(
    tenant_id: UUID,
    sso_id: UUID,
    request: SSOConfigurationRequest,
    admin_user = Depends(verify_platform_admin)
):
    """
    Update SSO configuration
    """
    try:
        sso_config = await SSOService.update_sso_configuration(
            sso_id=sso_id,
            tenant_id=tenant_id,
            sso_data=request.dict(exclude_unset=True)
        )
        
        return {
            "message": "SSO configuration updated successfully",
            "configuration": SSOConfigurationResponse.model_validate(sso_config)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update SSO configuration: {str(e)}")

@router.delete("/api/super-admin/tenants/{tenant_id}/sso/{sso_id}")
async def delete_sso_configuration(
    tenant_id: UUID,
    sso_id: UUID,
    admin_user = Depends(verify_platform_admin)
):
    """
    Revoke/Delete SSO configuration
    
    Disables SSO configuration
    Existing users can still log in via password or will be locked out
    """
    try:
        await SSOService.delete_sso_configuration(sso_id, tenant_id)
        
        return {"message": "SSO configuration deleted successfully"}
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete SSO configuration: {str(e)}")

@router.post("/api/super-admin/tenants/{tenant_id}/sso/{sso_id}/toggle")
async def toggle_sso_status(
    tenant_id: UUID,
    sso_id: UUID,
    status: str = Query(..., pattern="^(active|inactive)$"),
    admin_user = Depends(verify_platform_admin)
):
    """
    Toggle SSO configuration status (active/inactive)
    """
    try:
        sso_config = await SSOService.toggle_sso_status(sso_id, tenant_id, status)
        
        return {
            "message": f"SSO configuration {status}",
            "configuration": SSOConfigurationResponse.model_validate(sso_config)
        }
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle SSO status: {str(e)}")

# ============================================
# TENANT ADMIN BILLING ENDPOINTS
# ============================================

@router.get("/api/admin/subscription", response_model=SubscriptionResponse)
async def get_my_subscription(
    current_user: dict = Depends(verify_tenant_admin)
):
    """Get current subscription details for the logged-in tenant"""
    try:
        tenant_id = UUID(current_user['tid'])
        subscription = await BillingService.get_tenant_subscription(tenant_id)
        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")
        
        return SubscriptionResponse(
            id=str(subscription.id),
            tenant_id=str(subscription.tenant_id),
            plan_id=str(subscription.plan_id),
            plan_name=subscription.plan_name,
            billing_cycle=subscription.billing_cycle,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            trial_ends_at=subscription.trial_ends_at,
            base_price=subscription.base_price,
            discount_percentage=subscription.discount_percentage,
            discount_reason=subscription.discount_reason,
            promo_code=subscription.promo_code,
            final_price=subscription.final_price,
            currency=subscription.currency,
            employee_count=subscription.employee_count,
            max_employees=subscription.max_employees,
            max_admin_users=subscription.max_admin_users,
            stripe_customer_id=subscription.stripe_customer_id,
            stripe_subscription_id=subscription.stripe_subscription_id,
            payment_methods=[],
            next_billing_date=subscription.next_billing_date,
            last_billing_date=subscription.last_billing_date,
            auto_renew=subscription.auto_renew,
            cancel_at_period_end=subscription.cancel_at_period_end,
            created_at=subscription.created_at,
            updated_at=subscription.updated_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve subscription: {str(e)}")

@router.get("/api/admin/billing-history", response_model=BillingHistoryResponse)
async def get_my_billing_history(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(verify_tenant_admin)
):
    """Get billing history for the logged-in tenant"""
    try:
        tenant_id = UUID(current_user['tid'])
        invoices, total = await BillingService.get_billing_history(
            tenant_id=tenant_id,
            page=page,
            per_page=per_page
        )
        
        invoice_responses = [
            InvoiceResponse(
                id=str(invoice.id),
                tenant_id=str(invoice.tenant_id),
                subscription_id=str(invoice.subscription_id) if invoice.subscription_id else None,
                invoice_number=invoice.invoice_number,
                status=invoice.status,
                subtotal=invoice.subtotal,
                discount_amount=invoice.discount_amount,
                tax_amount=invoice.tax_amount,
                total_amount=invoice.total_amount,
                currency=invoice.currency,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                paid_date=invoice.paid_date,
                stripe_invoice_id=invoice.stripe_invoice_id,
                stripe_payment_intent_id=invoice.stripe_payment_intent_id,
                line_items=invoice.line_items,
                pdf_url=invoice.pdf_url,
                is_manual=invoice.is_manual,
                notes=invoice.notes,
                created_at=invoice.created_at,
                updated_at=invoice.updated_at
            )
            for invoice in invoices
        ]
        
        return BillingHistoryResponse(
            invoices=invoice_responses,
            total=total,
            page=page,
            per_page=per_page,
            has_more=(page * per_page) < total
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve billing history: {str(e)}")


@router.post("/api/admin/change-plan")
async def change_my_plan(
    plan_data: PlanChangeRequest,
    current_user: dict = Depends(verify_tenant_admin)
):
    """Change subscription plan for the logged-in tenant"""
    try:
        tenant_id = UUID(current_user['tid'])
        subscription = await BillingService.change_plan(
            tenant_id=tenant_id,
            new_plan_id=plan_data.new_plan_id,
            change_immediately=plan_data.change_immediately,
            performed_by=UUID(current_user['sub']) if current_user.get('sub') else None
        )
        return {"message": "Plan changed successfully", "plan_name": subscription.plan_name}
    except (ValidationError, NotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to change plan: {str(e)}")