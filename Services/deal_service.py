from typing import Dict, Any, List, Optional
from datetime import datetime, date
import logging
from uuid import UUID

from Models.crm import (
    CrmDeal, CrmLead, CrmActivity, CrmTimelineActivity, CrmDealStageHistory,
    CrmDealAuditLog, DealStage, DealPriority, ActivityType,
    TimelineActivityType, BillingCycle, ForecastCategory
)
from Models.crm_contacts import CrmContact
from Schema.crm import DealCreateRequest, DealUpdateRequest
from Models.tenant_user import User

logger = logging.getLogger(__name__)

STAGE_PROBABILITY_MAP = {
    DealStage.new: 10,
    DealStage.qualified: 25,
    DealStage.demo_scheduled: 40,
    DealStage.demo_completed: 60,
    DealStage.proposal_sent: 75,
    DealStage.negotiation: 90,
    DealStage.won: 100,
    DealStage.lost: 0,
}

STAGE_DISPLAY_MAP = {
    "new": "New",
    "qualified": "Qualified",
    "demo_scheduled": "Demo Scheduled",
    "demo_completed": "Demo Completed",
    "proposal_sent": "Proposal Sent",
    "negotiation": "Negotiation",
    "won": "Won",
    "lost": "Lost",
}


class DealService:

    @staticmethod
    async def create_timeline_activity(
        deal_id: UUID,
        tenant_id: UUID,
        activity_type: TimelineActivityType,
        title: str,
        description: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_by: Optional[UUID] = None,
    ) -> CrmTimelineActivity:
        """Create a timeline activity entry for a deal"""
        activity = CrmTimelineActivity(
            tenant_id=tenant_id,
            deal_id=deal_id,
            activity_type=activity_type,
            title=title,
            description=description,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata or {},
            created_by=created_by if created_by else UUID(int=0),
        )
        await activity.insert()
        return activity

    @staticmethod
    async def create_deal(data: DealCreateRequest, user_id: UUID, tenant_id: UUID) -> CrmDeal:
        """Create a new deal with full HubSpot-style workflow"""
        
        # Auto-suggest name if company name + product logic is needed
        deal_name = data.deal_name
        
        # Resolve probability from stage or use provided
        stage_enum = data.stage
        probability = data.probability if data.probability is not None else STAGE_PROBABILITY_MAP.get(stage_enum, 10)
        
        # Parse close_date
        close_date_val = None
        if data.close_date:
            try:
                close_date_val = datetime.strptime(data.close_date[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                close_date_val = None
        
        # Auto-calculate MRR and ARR
        mrr = data.expected_mrr
        arr = data.expected_arr
        if mrr is None and data.deal_value > 0 and data.billing_cycle:
            if data.billing_cycle == BillingCycle.monthly:
                mrr = data.deal_value
                arr = data.deal_value * 12
            elif data.billing_cycle == BillingCycle.annual:
                mrr = data.deal_value / 12
                arr = data.deal_value
        
        # Resolve owner_id - fallback to current user
        owner_id = UUID(data.owner_id) if data.owner_id else user_id
        
        deal = CrmDeal(
            tenant_id=tenant_id,
            deal_name=deal_name,
            pipeline=data.pipeline,
            stage=stage_enum,
            deal_value=data.deal_value,
            currency=data.currency,
            close_date=close_date_val,
            probability=probability,
            priority=data.priority,
            contact_id=UUID(data.contact_id) if data.contact_id else None,
            company_id=UUID(data.company_id) if data.company_id else None,
            lead_id=UUID(data.lead_id) if data.lead_id else None,
            owner_id=owner_id,
            sales_rep_id=UUID(data.sales_rep_id) if data.sales_rep_id else None,
            team=data.team,
            plan_id=UUID(data.plan_id) if data.plan_id else None,
            employee_count=data.employee_count,
            billing_cycle=data.billing_cycle,
            contract_duration=data.contract_duration,
            expected_mrr=mrr,
            expected_arr=arr,
            forecast_category=data.forecast_category,
            notes=data.notes,
        )
        
        await deal.insert()
        
        # Create timeline activity: Deal Created
        await DealService.create_timeline_activity(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type=TimelineActivityType.deal_created,
            title="Deal Created",
            description=f"Deal '{deal_name}' was created in stage '{STAGE_DISPLAY_MAP.get(deal.stage.value, deal.stage.value)}' with value {data.currency} {data.deal_value:,.2f}.",
            new_value=deal.stage.value,
            metadata={"stage": deal.stage.value, "deal_value": data.deal_value, "currency": data.currency},
            created_by=user_id,
        )
        
        # Create audit log
        audit = CrmDealAuditLog(
            tenant_id=tenant_id,
            deal_id=deal.id,
            user_id=user_id,
            action="creation",
            details=f"Deal '{deal_name}' created. Stage: {STAGE_DISPLAY_MAP.get(deal.stage.value, deal.stage.value)}. Value: {data.currency} {data.deal_value:,.2f}.",
        )
        await audit.insert()
        
        logger.info(f"New deal created: {deal_name} (ID: {deal.id})")
        return deal

    @staticmethod
    async def get_deals(
        tenant_id: UUID,
        grouped: bool = False,
        stage: Optional[str] = None,
        priority: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: Optional[str] = "created_at",
        sort_order: Optional[str] = "desc",
        page: int = 1,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Get deals with filtering, sorting, pagination. Soft-delete aware."""
        base_filter = {"tenant_id": tenant_id, "deleted_at": None}
        
        if stage and stage != "all":
            base_filter["stage"] = stage
        if priority and priority != "all":
            base_filter["priority"] = priority
        
        if search:
            import re
            search_regex = {"$regex": search, "$options": "i"}
            base_filter["$or"] = [
                {"deal_name": search_regex},
                {"pipeline": search_regex},
                {"team": search_regex},
            ]
        
        if grouped:
            deals = await CrmDeal.find(base_filter).sort(-CrmDeal.created_at).to_list()
            result = {s.value: [] for s in DealStage}
            
            for deal in deals:
                owner_name = None
                if deal.owner_id:
                    owner = await User.find_one(User.id == deal.owner_id)
                    if owner:
                        owner_name = f"{owner.first_name} {owner.last_name}"
                
                contact_name = None
                if deal.contact_id:
                    from Models.crm_contacts import CrmContact
                    contact = await CrmContact.find_one(CrmContact.id == deal.contact_id)
                    if contact:
                        contact_name = contact.full_name if hasattr(contact, 'full_name') else f"{contact.first_name} {contact.last_name}"
                
                deal_data = {
                    "id": str(deal.id),
                    "deal_name": deal.deal_name,
                    "pipeline": deal.pipeline,
                    "stage": deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage),
                    "deal_value": deal.deal_value,
                    "currency": deal.currency,
                    "close_date": deal.close_date.isoformat() if deal.close_date else None,
                    "probability": deal.probability,
                    "priority": deal.priority.value if hasattr(deal.priority, 'value') else str(deal.priority),
                    "contact_name": contact_name,
                    "owner_name": owner_name,
                    "owner_id": str(deal.owner_id) if deal.owner_id else None,
                    "created_at": deal.created_at.isoformat(),
                    "updated_at": deal.updated_at.isoformat(),
                }
                
                stage_key = deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage)
                if stage_key in result:
                    result[stage_key].append(deal_data)
            
            return result
        else:
            total_count = await CrmDeal.find(base_filter).count()
            
            sort_field_map = {
                "created_at": CrmDeal.created_at,
                "deal_value": CrmDeal.deal_value,
                "deal_name": CrmDeal.deal_name,
                "close_date": CrmDeal.close_date,
                "stage": CrmDeal.stage,
                "probability": CrmDeal.probability,
            }
            sort_field = sort_field_map.get(sort_by, CrmDeal.created_at)
            sort_order_sign = -sort_field if sort_order == "desc" else +sort_field
            
            skip = (page - 1) * limit
            deals = await CrmDeal.find(base_filter).sort(sort_order_sign).skip(skip).limit(limit).to_list()
            
            flat_deals = []
            for deal in deals:
                owner_name = None
                if deal.owner_id:
                    owner = await User.find_one(User.id == deal.owner_id)
                    if owner:
                        owner_name = f"{owner.first_name} {owner.last_name}"
                
                flat_deals.append({
                    "id": str(deal.id),
                    "deal_name": deal.deal_name,
                    "pipeline": deal.pipeline,
                    "stage": deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage),
                    "deal_value": deal.deal_value,
                    "currency": deal.currency,
                    "close_date": deal.close_date.isoformat() if deal.close_date else None,
                    "probability": deal.probability,
                    "priority": deal.priority.value if hasattr(deal.priority, 'value') else str(deal.priority),
                    "owner_name": owner_name,
                    "owner_id": str(deal.owner_id) if deal.owner_id else None,
                    "created_at": deal.created_at.isoformat(),
                    "updated_at": deal.updated_at.isoformat(),
                })
            
            return {
                "deals": flat_deals,
                "total": total_count,
                "page": page,
                "limit": limit,
                "pages": (total_count + limit - 1) // limit if limit > 0 else 1,
            }

    @staticmethod
    async def get_deal_by_id(deal_id: UUID, tenant_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a single deal with full details"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id, CrmDeal.deleted_at == None)
        if not deal:
            return None
        
        owner_name = None
        if deal.owner_id:
            owner = await User.find_one(User.id == deal.owner_id)
            if owner:
                owner_name = f"{owner.first_name} {owner.last_name}"
        
        contact_name = None
        contact_email = None
        contact_phone = None
        
        # Fetch associated contact
        if deal.contact_id:
            from Models.crm_contacts import CrmContact
            contact = await CrmContact.find_one(CrmContact.id == deal.contact_id)
            if contact:
                contact_name = contact.full_name if hasattr(contact, 'full_name') else f"{getattr(contact, 'first_name', '')} {getattr(contact, 'last_name', '')}".strip()
                contact_email = contact.email if hasattr(contact, 'email') else None
                contact_phone = contact.phone if hasattr(contact, 'phone') else None
        
        # Fetch lead
        lead_name = None
        lead_company = None
        if deal.lead_id:
            lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
            if lead:
                lead_name = f"{lead.first_name} {lead.last_name}".strip()
                lead_company = lead.company_name
        
        # Get timeline activities
        timeline = await CrmTimelineActivity.find(
            CrmTimelineActivity.deal_id == deal.id,
            CrmTimelineActivity.tenant_id == tenant_id
        ).sort(-CrmTimelineActivity.created_at).to_list()
        
        timeline_data = []
        for t in timeline:
            user_name = "System"
            try:
                if t.created_by and str(t.created_by) != "00000000-0000-0000-0000-000000000000":
                    u = await User.find_one(User.id == t.created_by)
                    if u:
                        user_name = f"{u.first_name} {u.last_name}".strip()
            except Exception:
                pass
            
            timeline_data.append({
                "id": str(t.id),
                "activity_type": t.activity_type.value if hasattr(t.activity_type, 'value') else str(t.activity_type),
                "title": t.title,
                "description": t.description,
                "old_value": t.old_value,
                "new_value": t.new_value,
                "metadata": t.metadata,
                "created_by_name": user_name,
                "created_at": t.created_at.isoformat(),
            })
        
        return {
            "id": str(deal.id),
            "deal_name": deal.deal_name,
            "pipeline": deal.pipeline,
            "stage": deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage),
            "deal_value": deal.deal_value,
            "currency": deal.currency,
            "close_date": deal.close_date.isoformat() if deal.close_date else None,
            "probability": deal.probability,
            "priority": deal.priority.value if hasattr(deal.priority, 'value') else str(deal.priority),
            "contact_id": str(deal.contact_id) if deal.contact_id else None,
            "contact_name": contact_name,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "company_id": str(deal.company_id) if deal.company_id else None,
            "lead_id": str(deal.lead_id) if deal.lead_id else None,
            "lead_name": lead_name,
            "lead_company": lead_company,
            "owner_id": str(deal.owner_id) if deal.owner_id else None,
            "owner_name": owner_name,
            "sales_rep_id": str(deal.sales_rep_id) if deal.sales_rep_id else None,
            "team": deal.team,
            "plan_id": str(deal.plan_id) if deal.plan_id else None,
            "employee_count": deal.employee_count,
            "billing_cycle": deal.billing_cycle.value if deal.billing_cycle else None,
            "contract_duration": deal.contract_duration,
            "expected_mrr": deal.expected_mrr,
            "expected_arr": deal.expected_arr,
            "forecast_category": deal.forecast_category.value if deal.forecast_category else None,
            "notes": deal.notes,
            "created_at": deal.created_at.isoformat(),
            "updated_at": deal.updated_at.isoformat(),
            "timeline": timeline_data,
        }

    @staticmethod
    async def update_deal(deal_id: UUID, data: DealUpdateRequest, user_id: UUID, tenant_id: UUID) -> CrmDeal:
        """Update an existing deal with timeline activity tracking"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id, CrmDeal.deleted_at == None)
        if not deal:
            raise ValueError("Deal not found")
        
        changes = []
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)
        
        # Track significant changes for timeline
        if "stage" in update_data:
            old_stage = deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage)
            new_stage = update_data["stage"]
            if old_stage != new_stage:
                new_probability = STAGE_PROBABILITY_MAP.get(DealStage(new_stage), 10)
                deal.probability = new_probability
                deal.days_in_stage = 0
                
                changes.append(f"Stage: {STAGE_DISPLAY_MAP.get(old_stage, old_stage)} -> {STAGE_DISPLAY_MAP.get(new_stage, new_stage)}")
                
                # Create timeline activity for stage change
                await DealService.create_timeline_activity(
                    deal_id=deal.id,
                    tenant_id=tenant_id,
                    activity_type=TimelineActivityType.stage_changed,
                    title=f"Stage changed to {STAGE_DISPLAY_MAP.get(new_stage, new_stage)}",
                    description=f"Deal moved from '{STAGE_DISPLAY_MAP.get(old_stage, old_stage)}' to '{STAGE_DISPLAY_MAP.get(new_stage, new_stage)}' (Probability: {new_probability}%).",
                    old_value=old_stage,
                    new_value=new_stage,
                    metadata={"old_stage": old_stage, "new_stage": new_stage, "probability": new_probability},
                    created_by=user_id,
                )
                
                # Create stage history
                history = CrmDealStageHistory(
                    tenant_id=tenant_id,
                    deal_id=deal.id,
                    old_stage=old_stage,
                    new_stage=new_stage,
                    changed_by=user_id,
                )
                await history.insert()
        
        if "deal_name" in update_data and update_data["deal_name"] != deal.deal_name:
            changes.append(f"Name: {deal.deal_name} -> {update_data['deal_name']}")
        
        if "deal_value" in update_data and update_data["deal_value"] != deal.deal_value:
            changes.append(f"Value: {deal.currency} {deal.deal_value:,.2f} -> {deal.currency} {update_data['deal_value']:,.2f}")
        
        if "owner_id" in update_data and update_data["owner_id"] != (str(deal.owner_id) if deal.owner_id else None):
            changes.append("Owner changed")
            await DealService.create_timeline_activity(
                deal_id=deal.id,
                tenant_id=tenant_id,
                activity_type=TimelineActivityType.owner_changed,
                title="Owner Changed",
                description="Deal owner was updated.",
                metadata={"new_owner_id": update_data["owner_id"]},
                created_by=user_id,
            )
        
        if "probability" in update_data:
            deal.probability = update_data["probability"]
        
        # Apply regular updates
        for key, val in update_data.items():
            if key == "stage":
                try:
                    deal.stage = DealStage(val)
                except ValueError:
                    pass
            elif key == "priority":
                try:
                    deal.priority = DealPriority(val)
                except ValueError:
                    pass
            elif key == "billing_cycle":
                try:
                    deal.billing_cycle = BillingCycle(val)
                except ValueError:
                    pass
            elif key == "forecast_category":
                try:
                    deal.forecast_category = ForecastCategory(val)
                except ValueError:
                    pass
            elif key in ("contact_id", "company_id", "lead_id", "owner_id", "sales_rep_id", "plan_id"):
                if val:
                    setattr(deal, key, UUID(str(val)))
                else:
                    setattr(deal, key, None)
            elif key == "close_date":
                if val:
                    try:
                        deal.close_date = datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
                    except (ValueError, TypeError):
                        pass
                else:
                    deal.close_date = None
            elif key in ("deal_name", "pipeline", "team", "notes", "contract_duration", "employee_count", "expected_mrr", "expected_arr"):
                setattr(deal, key, val)
            elif key == "deal_value":
                deal.deal_value = float(val)
            elif key == "currency":
                deal.currency = str(val)
        
        # Auto-recalculate MRR/ARR if billing cycle or value changed
        if deal.deal_value > 0 and deal.billing_cycle:
            if deal.billing_cycle == BillingCycle.monthly:
                deal.expected_mrr = deal.deal_value
                deal.expected_arr = deal.deal_value * 12
            elif deal.billing_cycle == BillingCycle.annual:
                deal.expected_mrr = deal.deal_value / 12
                deal.expected_arr = deal.deal_value
        
        deal.updated_at = datetime.utcnow()
        await deal.save()
        
        # Create general update timeline activity if no specific one was created
        if changes:
            await DealService.create_timeline_activity(
                deal_id=deal.id,
                tenant_id=tenant_id,
                activity_type=TimelineActivityType.deal_updated,
                title="Deal Updated",
                description="; ".join(changes),
                metadata={"changes": changes},
                created_by=user_id,
            )
        
        # Create audit log
        audit = CrmDealAuditLog(
            tenant_id=tenant_id,
            deal_id=deal.id,
            user_id=user_id,
            action="update",
            details="; ".join(changes) if changes else "Deal updated",
        )
        await audit.insert()
        
        logger.info(f"Deal updated: {deal.deal_name}")
        return deal

    @staticmethod
    async def soft_delete_deal(deal_id: UUID, tenant_id: UUID) -> bool:
        """Soft delete a deal"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id, CrmDeal.deleted_at == None)
        if not deal:
            raise ValueError("Deal not found")
        
        deal.deleted_at = datetime.utcnow()
        await deal.save()
        return True

    @staticmethod
    async def get_deal_timeline(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        """Get the full timeline for a deal"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id, CrmDeal.deleted_at == None)
        if not deal:
            raise ValueError("Deal not found")
        
        timeline = await CrmTimelineActivity.find(
            CrmTimelineActivity.deal_id == deal.id,
            CrmTimelineActivity.tenant_id == tenant_id
        ).sort(-CrmTimelineActivity.created_at).to_list()
        
        result = []
        for t in timeline:
            user_name = "System"
            try:
                if t.created_by and str(t.created_by) != "00000000-0000-0000-0000-000000000000":
                    u = await User.find_one(User.id == t.created_by)
                    if u:
                        user_name = f"{u.first_name} {u.last_name}".strip()
            except Exception:
                pass
            
            result.append({
                "id": str(t.id),
                "activity_type": t.activity_type.value if hasattr(t.activity_type, 'value') else str(t.activity_type),
                "title": t.title,
                "description": t.description,
                "old_value": t.old_value,
                "new_value": t.new_value,
                "metadata": t.metadata,
                "created_by_name": user_name,
                "created_at": t.created_at.isoformat(),
            })
        
        return result