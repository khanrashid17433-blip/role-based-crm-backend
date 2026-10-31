"""
Module and feature flag management service
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from Models.billing import TenantModule, SSOConfiguration
from Models.tenant_user import Tenant
from Models.plan import Plan
from Utility.exceptions import ValidationError, NotFoundError

class ModuleService:
    """Service for managing tenant modules and feature flags"""
    
    @staticmethod
    async def get_tenant_modules(tenant_id: UUID) -> TenantModule:
        """Get module configuration for tenant"""
        modules = await TenantModule.find_one(TenantModule.tenant_id == tenant_id)
        
        if not modules:
            # Create default module configuration based on plan
            modules = await ModuleService._create_default_modules(tenant_id)
        
        return modules
    
    @staticmethod
    async def update_tenant_modules(
        tenant_id: UUID,
        module_data: Dict[str, Any],
        updated_by: UUID
    ) -> TenantModule:
        """Update tenant module configuration"""
        
        modules = await ModuleService.get_tenant_modules(tenant_id)
        
        # Update module settings
        for key, value in module_data.items():
            if hasattr(modules, key):
                setattr(modules, key, value)
        
        modules.updated_at = datetime.utcnow()
        modules.updated_by = updated_by
        
        await modules.save()
        return modules
    
    @staticmethod
    async def toggle_plan_defaults(
        tenant_id: UUID,
        use_plan_defaults: bool,
        updated_by: UUID
    ) -> TenantModule:
        """Toggle between plan defaults and custom overrides"""
        
        modules = await ModuleService.get_tenant_modules(tenant_id)
        modules.use_plan_defaults = use_plan_defaults
        
        if use_plan_defaults:
            # Reset to plan defaults
            await ModuleService._apply_plan_defaults(modules, tenant_id)
        
        modules.updated_at = datetime.utcnow()
        modules.updated_by = updated_by
        
        await modules.save()
        return modules
    
    @staticmethod
    async def update_feature_flags(
        tenant_id: UUID,
        feature_flags: Dict[str, Any],
        updated_by: UUID
    ) -> TenantModule:
        """Update feature flags for tenant"""
        
        modules = await ModuleService.get_tenant_modules(tenant_id)
        modules.feature_flags.update(feature_flags)
        modules.updated_at = datetime.utcnow()
        modules.updated_by = updated_by
        
        await modules.save()
        return modules
    
    @staticmethod
    async def update_api_settings(
        tenant_id: UUID,
        api_access_enabled: bool,
        updated_by: UUID,
        api_rate_limit: Optional[int] = None
    ) -> TenantModule:
        """Update API access settings"""
        
        modules = await ModuleService.get_tenant_modules(tenant_id)
        modules.api_access_enabled = api_access_enabled
        
        if api_rate_limit is not None:
            if api_rate_limit < 1 or api_rate_limit > 10000:
                raise ValidationError("API rate limit must be between 1 and 10000 requests per minute")
            modules.api_rate_limit = api_rate_limit
        
        modules.updated_at = datetime.utcnow()
        modules.updated_by = updated_by
        
        await modules.save()
        return modules
    
    @staticmethod
    async def update_white_label_settings(
        tenant_id: UUID,
        white_label_data: Dict[str, Any],
        updated_by: UUID
    ) -> TenantModule:
        """Update white-label settings"""
        
        modules = await ModuleService.get_tenant_modules(tenant_id)
        
        # Validate white-label eligibility
        if not modules.white_label_enabled:
            raise ValidationError("White-label features not enabled for this tenant")
        
        # Update white-label settings
        if 'custom_domain' in white_label_data:
            modules.custom_domain = white_label_data['custom_domain']
        if 'brand_color' in white_label_data:
            modules.brand_color = white_label_data['brand_color']
        if 'custom_logo_url' in white_label_data:
            modules.custom_logo_url = white_label_data['custom_logo_url']
        if 'custom_email_from_name' in white_label_data:
            modules.custom_email_from_name = white_label_data['custom_email_from_name']
        
        modules.updated_at = datetime.utcnow()
        modules.updated_by = updated_by
        
        await modules.save()
        return modules
    
    @staticmethod
    async def update_limit_overrides(
        tenant_id: UUID,
        updated_by: UUID,
        max_employees: Optional[int] = None,
        max_admin_users: Optional[int] = None,
        max_entities: Optional[int] = None
    ) -> TenantModule:
        """Update plan limit overrides"""
        
        modules = await ModuleService.get_tenant_modules(tenant_id)
        
        if max_employees is not None:
            if max_employees < 1:
                raise ValidationError("Max employees must be at least 1")
            modules.max_employees_override = max_employees
        
        if max_admin_users is not None:
            if max_admin_users < 1:
                raise ValidationError("Max admin users must be at least 1")
            modules.max_admin_users_override = max_admin_users
        
        if max_entities is not None:
            if max_entities < 1:
                raise ValidationError("Max entities must be at least 1")
            modules.max_entities_override = max_entities
        
        modules.updated_at = datetime.utcnow()
        modules.updated_by = updated_by
        
        await modules.save()
        return modules
    
    @staticmethod
    async def _create_default_modules(tenant_id: UUID) -> TenantModule:
        """Create default module configuration based on tenant's plan"""
        
        # Get tenant and plan information
        from Services.billing_service import BillingService
        subscription = await BillingService.get_tenant_subscription(tenant_id)
        
        modules = TenantModule(
            tenant_id=tenant_id,
            use_plan_defaults=True
        )
        
        if subscription:
            plan = await Plan.find_one(Plan.id == subscription.plan_id)
            if plan:
                await ModuleService._apply_plan_defaults(modules, tenant_id, plan)
        
        await modules.insert()
        return modules
    
    @staticmethod
    async def _apply_plan_defaults(
        modules: TenantModule,
        tenant_id: UUID,
        plan: Optional[Plan] = None
    ):
        """Apply plan defaults to module configuration"""
        
        if not plan:
            from Services.billing_service import BillingService
            subscription = await BillingService.get_tenant_subscription(tenant_id)
            if subscription:
                plan = await Plan.find_one(Plan.id == subscription.plan_id)
        
        if plan:
            # Apply plan-based module settings
            modules_config = plan.modules_json or {}
            
            modules.core_hr_enabled = modules_config.get('core_hr', True)
            modules.payroll_enabled = modules_config.get('payroll', False)
            modules.leave_enabled = modules_config.get('leave', True)
            modules.attendance_enabled = modules_config.get('attendance', True)
            modules.recruitment_enabled = modules_config.get('recruitment', False)
            modules.performance_enabled = modules_config.get('performance', False)
            modules.benefits_enabled = modules_config.get('benefits', False)
            modules.compliance_enabled = modules_config.get('compliance', False)
            
            modules.api_access_enabled = plan.api_access
            modules.white_label_enabled = plan.white_label
            modules.sso_enabled = plan.sso_enabled

class SSOService:
    """Service for managing SSO configurations"""
    
    @staticmethod
    async def get_sso_configurations(tenant_id: UUID) -> list[SSOConfiguration]:
        """Get all SSO configurations for tenant"""
        return await SSOConfiguration.find(
            SSOConfiguration.tenant_id == tenant_id,
            sort=[("created_at", -1)]
        ).to_list()
    
    @staticmethod
    async def create_sso_configuration(
        tenant_id: UUID,
        sso_data: Dict[str, Any],
        created_by: UUID
    ) -> SSOConfiguration:
        """Create new SSO configuration"""
        
        # Validate required fields
        required_fields = ['domain', 'sso_type']
        for field in required_fields:
            if field not in sso_data:
                raise ValidationError(f"Missing required field: {field}")
        
        # Check if domain already exists
        existing = await SSOConfiguration.find_one(
            SSOConfiguration.tenant_id == tenant_id,
            SSOConfiguration.domain == sso_data['domain']
        )
        if existing:
            raise ValidationError("SSO configuration already exists for this domain")
        
        sso_config = SSOConfiguration(
            tenant_id=tenant_id,
            created_by=created_by,
            **sso_data
        )
        
        await sso_config.insert()
        return sso_config
    
    @staticmethod
    async def update_sso_configuration(
        sso_id: UUID,
        tenant_id: UUID,
        sso_data: Dict[str, Any]
    ) -> SSOConfiguration:
        """Update SSO configuration"""
        
        sso_config = await SSOConfiguration.find_one(
            SSOConfiguration.id == sso_id,
            SSOConfiguration.tenant_id == tenant_id
        )
        if not sso_config:
            raise NotFoundError("SSO configuration not found")
        
        # Update fields
        for key, value in sso_data.items():
            if hasattr(sso_config, key):
                setattr(sso_config, key, value)
        
        sso_config.updated_at = datetime.utcnow()
        await sso_config.save()
        
        return sso_config
    
    @staticmethod
    async def delete_sso_configuration(
        sso_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """Delete SSO configuration"""
        
        sso_config = await SSOConfiguration.find_one(
            SSOConfiguration.id == sso_id,
            SSOConfiguration.tenant_id == tenant_id
        )
        if not sso_config:
            raise NotFoundError("SSO configuration not found")
        
        await sso_config.delete()
        return True
    
    @staticmethod
    async def toggle_sso_status(
        sso_id: UUID,
        tenant_id: UUID,
        status: str
    ) -> SSOConfiguration:
        """Toggle SSO configuration status"""
        
        if status not in ['active', 'inactive']:
            raise ValidationError("Status must be 'active' or 'inactive'")
        
        sso_config = await SSOConfiguration.find_one(
            SSOConfiguration.id == sso_id,
            SSOConfiguration.tenant_id == tenant_id
        )
        if not sso_config:
            raise NotFoundError("SSO configuration not found")
        
        sso_config.status = status
        sso_config.updated_at = datetime.utcnow()
        await sso_config.save()
        
        return sso_config