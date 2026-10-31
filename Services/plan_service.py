from typing import List, Optional
from uuid import UUID

from Models.plan import Plan, SupportTier
from Schema.plan import PlanCreate, PlanUpdate, PlanResponse
from Utility.helpers import PlanNotFound, DuplicateSlugError


class PlanService:
    """Service layer for Plan operations"""
    
    @staticmethod
    async def create_plan(plan_data: PlanCreate) -> Plan:
        """Create a new plan"""
        # Check for duplicate slug
        existing = await Plan.find_one(Plan.slug == plan_data.slug)
        if existing:
            raise DuplicateSlugError(f"Plan with slug '{plan_data.slug}' already exists")
        
        plan = Plan(
            name=plan_data.name,
            slug=plan_data.slug,
            description=plan_data.description,
            price_monthly_usd=plan_data.price_monthly_usd,
            price_yearly_usd=plan_data.price_yearly_usd,
            price_monthly_gbp=plan_data.price_monthly_gbp,
            price_yearly_gbp=plan_data.price_yearly_gbp,
            price_monthly_eur=plan_data.price_monthly_eur,
            price_yearly_eur=plan_data.price_yearly_eur,
            price_monthly_inr=plan_data.price_monthly_inr,
            price_yearly_inr=plan_data.price_yearly_inr,
            max_employees=plan_data.max_employees,
            max_admin_users=plan_data.max_admin_users,
            modules_json=plan_data.modules_json or {},
            api_access=plan_data.api_access,
            sso_enabled=plan_data.sso_enabled,
            white_label=plan_data.white_label,
            support_tier=SupportTier(plan_data.support_tier.value),
            has_trial=plan_data.has_trial,
            trial_days=plan_data.trial_days,
            regions_allowed=plan_data.regions_allowed or ["US"],
            is_active=True,
            sort_order=plan_data.sort_order,
        )
        
        await plan.insert()
        return plan
    
    @staticmethod
    async def get_plan_by_id(plan_id: UUID) -> Plan:
        """Get plan by ID"""
        plan = await Plan.find_one(Plan.id == plan_id)
        
        if not plan:
            raise PlanNotFound(f"Plan with ID {plan_id} not found")
        
        return plan
    
    @staticmethod
    async def get_plan_by_slug(slug: str) -> Plan:
        """Get plan by slug"""
        plan = await Plan.find_one(
            Plan.slug == slug,
            Plan.is_active == True
        )
        
        if not plan:
            raise PlanNotFound(f"Plan with slug '{slug}' not found")
        
        return plan
    
    @staticmethod
    async def list_plans(
        page: int = 1,
        per_page: int = 20,
        active_only: bool = True
    ) -> tuple[List[Plan], int]:
        """List plans with pagination"""
        # Build query
        query = Plan.find()
        if active_only:
            query = Plan.find(Plan.is_active == True)
        
        # Get total count
        total = await query.count()
        
        # Apply pagination and ordering
        plans = await query.sort(
            [(Plan.sort_order, 1), (Plan.created_at, 1)]
        ).skip((page - 1) * per_page).limit(per_page).to_list()
        
        return plans, total
    
    @staticmethod
    async def get_active_plans() -> List[Plan]:
        """Get all active plans (for pricing page)"""
        plans = await Plan.find(
            Plan.is_active == True
        ).sort(
            [(Plan.sort_order, 1), (Plan.created_at, 1)]
        ).to_list()
        
        return plans
    
    @staticmethod
    async def update_plan(
        plan_id: UUID,
        plan_data: PlanUpdate
    ) -> Plan:
        """Update a plan"""
        plan = await PlanService.get_plan_by_id(plan_id)
        
        # Update fields if provided
        update_data = plan_data.model_dump(exclude_unset=True)
        
        # Check for duplicate slug if slug is being updated
        if 'slug' in update_data and update_data['slug'] != plan.slug:
            existing = await Plan.find_one(Plan.slug == update_data['slug'])
            if existing:
                raise DuplicateSlugError(f"Plan with slug '{update_data['slug']}' already exists")
        
        # Convert support_tier if present
        if 'support_tier' in update_data:
            update_data['support_tier'] = SupportTier(update_data['support_tier'])
        
        # Apply updates
        for field, value in update_data.items():
            setattr(plan, field, value)
        
        await plan.save()
        return plan
    
    @staticmethod
    async def delete_plan(plan_id: UUID) -> Plan:
        """Soft delete a plan (set is_active=False)"""
        plan = await PlanService.get_plan_by_id(plan_id)
        plan.is_active = False
        
        await plan.save()
        return plan
    
    @staticmethod
    async def hard_delete_plan(plan_id: UUID) -> bool:
        """Permanently delete a plan"""
        plan = await PlanService.get_plan_by_id(plan_id)
        
        await plan.delete()
        return True
