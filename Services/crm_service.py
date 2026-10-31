from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, date
import logging
from uuid import UUID, uuid4

from Models.crm import (
    CrmLead, CrmDeal, CrmActivity, CrmProposal, CrmClient,
    CrmPipeline, CrmDealStageHistory, CrmDealAuditLog,
    LeadStatus, LeadSource, DealStage, Priority, ActivityType
)
from Models.crm_task import CrmTask  # Import the new centralized task model
from Schema.crm import (
    WebFormLeadRequest, LeadManualCreateRequest, LeadQualifyRequest,
    DemoScheduleRequest, DemoCompleteRequest, ProposalCreateRequest,
    DealWonRequest, DealLostRequest, LeadUpdateRequest
)
from Models.tenant_user import Tenant, User, TenantStatus, UserType
from Services.registration_service import RegistrationService

logger = logging.getLogger(__name__)

class CrmService:
    
    @staticmethod
    async def capture_web_lead(data: WebFormLeadRequest, tenant_id: UUID) -> CrmLead:
        """Capture lead from website form"""
        lead = CrmLead(
            tenant_id=tenant_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email.lower(),
            phone=data.phone,
            company_name=data.company_name,
            company_size=data.company_size,
            industry=data.industry,
            region=data.region,
            source=LeadSource.web_form,
            utm_source=data.utm_source,
            utm_medium=data.utm_medium,
            utm_campaign=data.utm_campaign,
            notes=data.notes,
            status=LeadStatus.new
        )
        await lead.insert()
        logger.info(f"New web lead captured: {lead.email}")
        return lead
        
    @staticmethod
    async def create_manual_lead(data: LeadManualCreateRequest, created_by: UUID, tenant_id: UUID) -> CrmLead:
        lead = CrmLead(
            tenant_id=tenant_id,
            first_name=data.first_name,
            last_name=data.last_name,
            email=data.email.lower(),
            phone=data.phone,
            company_name=data.company_name,
            company_size=data.company_size,
            industry=data.industry,
            region=data.region,
            source=data.source,
            priority=data.priority,
            assigned_to=data.assigned_to,
            notes=data.notes,
            status=LeadStatus.new
        )
        await lead.insert()
        return lead

    @staticmethod
    async def import_leads_bulk(leads_data: List, created_by: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Bulk import leads from CSV data"""
        created = 0
        failed = 0
        errors = []

        for idx, row in enumerate(leads_data):
            try:
                # Map source string to LeadSource enum safely
                try:
                    source = LeadSource(row.source) if row.source else LeadSource.manual
                except ValueError:
                    source = LeadSource.manual

                # Map priority string to Priority enum safely
                priority = None
                if row.priority:
                    try:
                        priority = Priority(row.priority)
                    except ValueError:
                        priority = None

                lead = CrmLead(
                    tenant_id=tenant_id,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    email=row.email.lower(),
                    phone=row.phone,
                    company_name=row.company_name,
                    company_size=row.company_size,
                    industry=row.industry,
                    region=row.region,
                    source=source,
                    priority=priority,
                    notes=row.notes,
                    job_title=row.job_title,
                    status=LeadStatus.new
                )
                await lead.insert()
                created += 1
            except Exception as e:
                failed += 1
                errors.append({"row": idx + 1, "email": getattr(row, 'email', 'unknown'), "error": str(e)})

        return {"created": created, "failed": failed, "errors": errors}


    @staticmethod
    async def qualify_lead(lead_id: UUID, data: LeadQualifyRequest, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Qualify a lead and optionally create an opportunity"""
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
            
        # Calculate BANT score
        score = 0
        if data.budget_confirmed: score += 25
        if data.authority_confirmed: score += 25
        if data.timeline in ["Immediate (<1 month)", "Short-term (1-3M)"]: score += 25
        elif data.timeline: score += 10
        if len(data.pain_points) > 0: score += 25
        
        lead.budget_confirmed = data.budget_confirmed
        lead.budget_notes = data.budget_notes
        lead.authority_confirmed = data.authority_confirmed
        lead.authority_notes = data.authority_notes
        lead.pain_points = data.pain_points
        lead.timeline = data.timeline
        lead.estimated_headcount = data.estimated_headcount
        lead.current_solution = data.current_solution
        lead.required_regions = data.required_regions
        lead.qualification_score = score
        
        deal = None
        if score >= 60:
            lead.status = LeadStatus.qualified
            # Create Deal
            deal = CrmDeal(
                tenant_id=tenant_id,
                lead_id=lead.id,
                deal_name=f"{lead.company_name} - HRMS Deal",
                stage=DealStage.qualified_to_buy,
                headcount_estimate=data.estimated_headcount,
                assigned_to=lead.assigned_to or user_id,
                probability=20
            )
            await deal.insert()
            
            # Log creation in activity feed & audit log
            activity = CrmActivity(
                tenant_id=tenant_id,
                deal_id=deal.id,
                lead_id=lead.id,
                activity_type=ActivityType.note,
                subject="Deal Created via Lead Qualification",
                body=f"Deal '{deal.name}' created automatically after qualifying lead with BANT score of {score}.",
                completed_at=datetime.utcnow(),
                created_by=user_id
            )
            await activity.insert()
            
            audit = CrmDealAuditLog(
                tenant_id=tenant_id,
                deal_id=deal.id,
                user_id=user_id,
                action="creation",
                details=f"Deal qualified and created from lead. Stage set to {deal.stage.value}."
            )
            await audit.insert()
        else:
            lead.status = LeadStatus.contacted
            
        lead.updated_at = datetime.utcnow()
        await lead.save()
        
        return {
            "lead": lead,
            "opportunity": deal,
            "score": score,
            "qualified": score >= 60
        }
        
    @staticmethod
    async def schedule_demo(deal_id: UUID, data: DemoScheduleRequest, tenant_id: UUID) -> CrmDeal:
        opp = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not opp:
            raise ValueError("Deal not found")
            
        opp.demo_type = data.demo_type
        opp.demo_date = data.demo_date
        opp.demo_duration = data.demo_duration
        opp.demo_meeting_link = data.demo_meeting_link
        opp.demo_focus_areas = data.demo_focus_areas
        opp.stage = DealStage.presentation_scheduled
        opp.probability_pct = 40
        
        # Also update lead status AND flat demo fields on the lead
        lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
        if lead:
            lead.status = LeadStatus.demo_scheduled
            lead.demo_date = data.demo_date
            lead.demo_duration = data.demo_duration
            lead.demo_meeting_link = data.demo_meeting_link
            lead.demo_focus_areas = data.demo_focus_areas
            lead.demo_outcome = "scheduled"
            await lead.save()
            
        opp.updated_at = datetime.utcnow()
        await opp.save()
        return opp

    @staticmethod
    async def complete_demo(deal_id: UUID, data: DemoCompleteRequest, tenant_id: UUID) -> CrmDeal:
        opp = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not opp:
            raise ValueError("Deal not found")
        
        logger.info(f"Completing demo for deal {deal_id}")
        logger.info(f"Demo outcome: {data.demo_outcome}")
        logger.info(f"Current stage before update: {opp.stage}")
            
        opp.demo_notes = data.demo_notes
        opp.demo_outcome = data.demo_outcome
        
        opp.stage = DealStage.presentation_scheduled
        opp.probability_pct = 40
        
        if data.follow_up_date:
            # Create a task for follow up
            task = CrmTask(
                tenant_id=tenant_id,
                deal_id=opp.id,
                lead_id=opp.lead_id,
                title="Demo Follow-up",
                due_date=datetime.combine(data.follow_up_date, datetime.min.time()),
                assigned_to=opp.assigned_to
            )
            await task.insert()
            
        # Update lead
        lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
        if lead:
            lead.status = LeadStatus.demo_done
            await lead.save()
            
        opp.updated_at = datetime.utcnow()
        await opp.save()
        return opp
        
    @staticmethod
    async def create_proposal(deal_id: UUID, data: ProposalCreateRequest, tenant_id: UUID) -> CrmProposal:
        opp = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not opp:
            raise ValueError("Deal not found")
            
        opp.plan_id = data.plan_id
        opp.stage = DealStage.proposal_sent
        opp.probability_pct = 70
        await opp.save()
        
        # Update lead
        lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
        if lead:
            lead.status = LeadStatus.proposal_sent
            await lead.save()
            
        # Base pricing calculation mock
        value = data.employees_count * 10 * 100 # $10 per employee mock
        if data.contract_duration == "annual":
            value *= 12
        
        proposal = CrmProposal(
            tenant_id=tenant_id,
            deal_id=opp.id,
            template_id=data.template_id,
            value=value,
            currency="USD",
            terms_months=12 if data.contract_duration == "annual" else 1,
            discount_pct=data.discount_pct,
            sent_at=datetime.utcnow()
        )
        await proposal.insert()
        return proposal

    @staticmethod
    async def mark_won(deal_id: UUID, data: DealWonRequest, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        opp = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not opp:
            raise ValueError("Deal not found")
            
        opp.contract_signed_date = data.contract_signed_date
        opp.go_live_date = data.go_live_date
        opp.assigned_csm = data.assigned_csm
        opp.won_reason = data.won_reason
        opp.stage = DealStage.won
        opp.probability_pct = 100
        opp.updated_at = datetime.utcnow()
        await opp.save()
        
        lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
        if lead:
            lead.status = LeadStatus.won
            await lead.save()
            
        tenant = None
        if data.auto_provision_tenant and lead:
            # Mock tenant auto provisioning
            tenant_slug = RegistrationService._generate_tenant_slug(lead.company_name)
            tenant = Tenant(
                name=lead.company_name,
                slug=tenant_slug,
                subdomain=tenant_slug,
                status=TenantStatus.active,
                plan_id=opp.plan_id,
                primary_region="US",
                primary_currency="USD",
                billing_cycle="yearly",
                company_size=lead.company_size,
                industry=lead.industry
            )
            await tenant.insert()
            
        return {
            "opportunity": opp,
            "tenant_provisioned": tenant is not None,
            "tenant_id": str(tenant.id) if tenant else None
        }

    @staticmethod
    async def mark_lost(deal_id: UUID, data: DealLostRequest, tenant_id: UUID) -> CrmDeal:
        opp = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not opp:
            raise ValueError("Deal not found")
            
        opp.lost_reason = data.lost_reason
        opp.competitor_chosen = data.competitor_chosen
        opp.lost_notes = data.lost_notes
        opp.reengage_date = data.reengage_date
        opp.stage = DealStage.lost
        opp.probability_pct = 0
        opp.updated_at = datetime.utcnow()
        await opp.save()
        
        lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
        if lead:
            lead.status = LeadStatus.lost
            await lead.save()
            
        return opp

    @staticmethod
    async def get_leads(tenant_id: UUID, status: Optional[str] = None, source: Optional[str] = None, search: Optional[str] = None) -> List[CrmLead]:
        find_query = {"tenant_id": tenant_id}
        if status and status != "all":
            find_query["status"] = status
        if source and source != "all":
            find_query["source"] = source
        
        if search:
            search_regex = {"$regex": search, "$options": "i"}
            find_query["$or"] = [
                {"company_name": search_regex},
                {"first_name": search_regex},
                {"last_name": search_regex},
                {"email": search_regex},
                {"phone": search_regex}
            ]
        
        return await CrmLead.find(find_query).sort(-CrmLead.created_at).to_list()

    @staticmethod
    async def get_lead_by_id(lead_id: UUID, tenant_id: UUID) -> Optional[CrmLead]:
        return await CrmLead.find_one(CrmLead.id == lead_id)

    @staticmethod
    async def update_lead(lead_id: UUID, data: LeadUpdateRequest, tenant_id: UUID, user_id: Optional[UUID] = None) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        update_data = data.model_dump(exclude_unset=True)
        changes = []
        for key, val in update_data.items():
            old_val = getattr(lead, key, None)
            if old_val != val:
                changes.append(f"{key}: {old_val} -> {val}")
                setattr(lead, key, val)
        
        timestamp = datetime.utcnow()
        if changes and user_id:
            from uuid import uuid4
            if lead.audit_logs is None:
                lead.audit_logs = []
            lead.audit_logs.append({
                "id": str(uuid4()),
                "user_id": str(user_id),
                "action": "update",
                "details": f"Updated: {', '.join(changes)}",
                "timestamp": timestamp.isoformat()
            })
            lead.last_activity = timestamp
            
            # If status or priority changed, log as timeline activity too
            if "status" in update_data or "priority" in update_data:
                activity = CrmActivity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    activity_type=ActivityType.note,
                    subject="Lead Status/Priority Updated",
                    body=f"Updated properties:\n" + "\n".join(changes),
                    completed_at=timestamp,
                    created_by=user_id
                )
                await activity.insert()
        
        lead.updated_at = timestamp
        await lead.save()
        return lead

    @staticmethod
    async def log_lead_audit_and_activity(
        lead: CrmLead,
        action: str,
        details: str,
        user_id: UUID,
        activity_subject: Optional[str] = None,
        activity_body: Optional[str] = None,
        activity_type: ActivityType = ActivityType.note
    ):
        from uuid import uuid4
        timestamp = datetime.utcnow()
        if lead.audit_logs is None:
            lead.audit_logs = []
        lead.audit_logs.append({
            "id": str(uuid4()),
            "user_id": str(user_id),
            "action": action,
            "details": details,
            "timestamp": timestamp.isoformat()
        })
        lead.last_activity = timestamp
        
        if activity_subject:
            activity = CrmActivity(
                tenant_id=lead.tenant_id,
                lead_id=lead.id,
                activity_type=activity_type,
                subject=activity_subject,
                body=activity_body,
                completed_at=timestamp,
                created_by=user_id
            )
            await activity.insert()

    @staticmethod
    async def add_lead_note(lead_id: UUID, text: str, is_pinned: bool, user_id: UUID, tenant_id: UUID, mentions: Optional[List[UUID]] = None, attachments: Optional[List[str]] = None) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        from uuid import uuid4
        timestamp = datetime.utcnow()
        note = {
            "id": str(uuid4()),
            "text": text,
            "is_pinned": is_pinned,
            "created_by": str(user_id),
            "created_at": timestamp.isoformat(),
            "mentions": [str(m) for m in mentions] if mentions else [],
            "attachments": attachments or []
        }
        if lead.notes_list is None:
            lead.notes_list = []
        lead.notes_list.append(note)
        
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="add_note",
            details=f"Added note: {text[:60]}...",
            user_id=user_id,
            activity_subject="Note Added",
            activity_body=text,
            activity_type=ActivityType.note
        )
        
        lead.updated_at = timestamp
        await lead.save()
        return lead

    @staticmethod
    async def edit_lead_note(lead_id: UUID, note_id: str, text: str, is_pinned: bool, user_id: UUID, tenant_id: UUID, mentions: Optional[List[UUID]] = None, attachments: Optional[List[str]] = None) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        found = False
        for note in lead.notes_list:
            if note.get("id") == note_id:
                note["text"] = text
                note["is_pinned"] = is_pinned
                note["mentions"] = [str(m) for m in mentions] if mentions else []
                note["attachments"] = attachments or []
                note["updated_at"] = datetime.utcnow().isoformat()
                found = True
                break
        
        if not found:
            raise ValueError("Note not found")
            
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="edit_note",
            details=f"Edited note: {text[:60]}...",
            user_id=user_id
        )
        lead.updated_at = datetime.utcnow()
        await lead.save()
        return lead

    @staticmethod
    async def toggle_lead_note_pin(lead_id: UUID, note_id: str, user_id: UUID, tenant_id: UUID) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        found = False
        for note in lead.notes_list:
            if note.get("id") == note_id:
                note["is_pinned"] = not note.get("is_pinned", False)
                found = True
                action = "pin_note" if note["is_pinned"] else "unpin_note"
                details = f"Toggled pin status for note."
                await CrmService.log_lead_audit_and_activity(
                    lead=lead,
                    action=action,
                    details=details,
                    user_id=user_id
                )
                break
        if not found:
            raise ValueError("Note not found")
            
        lead.updated_at = datetime.utcnow()
        await lead.save()
        return lead

    @staticmethod
    async def delete_lead_note(lead_id: UUID, note_id: str, user_id: UUID, tenant_id: UUID) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        original_len = len(lead.notes_list)
        lead.notes_list = [n for n in lead.notes_list if n.get("id") != note_id]
        if len(lead.notes_list) == original_len:
            raise ValueError("Note not found")
            
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="delete_note",
            details="Deleted note",
            user_id=user_id
        )
        lead.updated_at = datetime.utcnow()
        await lead.save()
        return lead

    @staticmethod
    async def schedule_lead_demo(lead_id: UUID, demo_data: Dict[str, Any], user_id: UUID, tenant_id: UUID) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
            
        from uuid import uuid4
        timestamp = datetime.utcnow()
        meet_link = demo_data.get("meeting_link") or f"https://meet.google.com/{uuid4().hex[:3]}-{uuid4().hex[:4]}-{uuid4().hex[:3]}"
        
        scheduled_time = demo_data.get("scheduled_time")
        duration_minutes = demo_data.get("duration_minutes", 30)
        focus_areas = demo_data.get("focus_areas", [])
        title = demo_data.get("title", f"Demo with {lead.company_name}")
        
        # Store in nested demos array for audit/history
        demo = {
            "id": str(uuid4()),
            "title": title,
            "scheduled_time": scheduled_time.isoformat() if hasattr(scheduled_time, 'isoformat') else scheduled_time,
            "duration_minutes": duration_minutes,
            "focus_areas": focus_areas,
            "meeting_link": meet_link,
            "created_by": str(user_id),
            "created_at": timestamp.isoformat(),
            "status": "scheduled"
        }
        
        if lead.demos is None:
            lead.demos = []
        lead.demos.append(demo)
        
        # ---- Set flat fields (source of truth for Demo Management calendar) ----
        lead.status = LeadStatus.demo_scheduled
        lead.demo_date = scheduled_time
        lead.demo_duration = duration_minutes
        lead.demo_meeting_link = meet_link
        lead.demo_focus_areas = focus_areas
        lead.demo_outcome = "scheduled"
        
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="schedule_demo",
            details=f"Scheduled demo: '{title}' for {scheduled_time}.",
            user_id=user_id,
            activity_subject="Demo Scheduled",
            activity_body=f"Meeting Link: {meet_link}\nFocus Areas: {', '.join(focus_areas) if focus_areas else 'None'}",
            activity_type=ActivityType.meeting
        )
        
        lead.updated_at = timestamp
        await lead.save()
        return lead

    @staticmethod
    async def generate_lead_proposal(lead_id: UUID, proposal_data: Dict[str, Any], user_id: UUID, tenant_id: UUID) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
            
        from uuid import uuid4
        timestamp = datetime.utcnow()
        base_price_map = {"basic": 5, "standard": 10, "enterprise": 20}
        tier = proposal_data.get("tier", "standard").lower()
        price_per_employee = base_price_map.get(tier, 10)
        
        emp_count = int(proposal_data.get("employees_count") or 50)
        total_monthly = emp_count * price_per_employee
        
        discount = float(proposal_data.get("discount_pct") or 0.0)
        total_monthly_discounted = total_monthly * (1.0 - discount / 100.0)
        
        proposal = {
            "id": str(uuid4()),
            "title": proposal_data.get("title", f"HRMS Proposal for {lead.company_name}"),
            "tier": tier,
            "employees_count": emp_count,
            "discount_pct": discount,
            "monthly_value": total_monthly_discounted,
            "created_by": str(user_id),
            "created_at": timestamp.isoformat(),
            "status": "draft"
        }
        
        if lead.proposals is None:
            lead.proposals = []
        lead.proposals.append(proposal)
        
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="generate_proposal",
            details=f"Generated proposal: '{proposal['title']}' - Tier: {tier.upper()}, Value: ${total_monthly_discounted}/mo",
            user_id=user_id,
            activity_subject="Proposal Generated",
            activity_body=f"Monthly Value: ${total_monthly_discounted}\nEmployees: {emp_count}\nDiscount: {discount}%",
            activity_type=ActivityType.note
        )
        
        lead.updated_at = timestamp
        await lead.save()
        return lead

    @staticmethod
    async def upload_lead_document(lead_id: UUID, name: str, file_size: str, user_id: UUID, tenant_id: UUID, file_type: Optional[str] = None, file_url: Optional[str] = None) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
            
        from uuid import uuid4
        timestamp = datetime.utcnow()
        doc = {
            "id": str(uuid4()),
            "name": name,
            "file_size": file_size,
            "file_type": file_type,
            "file_url": file_url,
            "uploaded_by": str(user_id),
            "uploaded_at": timestamp.isoformat()
        }
        
        if lead.documents is None:
            lead.documents = []
        lead.documents.append(doc)
        
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="upload_document",
            details=f"Uploaded document: {name} ({file_size})",
            user_id=user_id,
            activity_subject="Document Uploaded",
            activity_body=f"File Name: {name}\nSize: {file_size}",
            activity_type=ActivityType.note
        )
        
        lead.updated_at = timestamp
        await lead.save()
        return lead

    @staticmethod
    async def delete_lead_document(lead_id: UUID, doc_id: str, user_id: UUID, tenant_id: UUID) -> CrmLead:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
            
        original_len = len(lead.documents)
        lead.documents = [d for d in lead.documents if d.get("id") != doc_id]
        if len(lead.documents) == original_len:
            raise ValueError("Document not found")
            
        await CrmService.log_lead_audit_and_activity(
            lead=lead,
            action="delete_document",
            details="Deleted document",
            user_id=user_id
        )
        lead.updated_at = datetime.utcnow()
        await lead.save()
        return lead

    @staticmethod
    async def get_lead_timeline(lead_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
            
        activities = await CrmActivity.find(CrmActivity.lead_id == lead_id, CrmActivity.tenant_id == tenant_id).to_list()
        
        timeline_events = []
        
        for a in activities:
            timeline_events.append({
                "id": str(a.id),
                "type": "activity",
                "activity_type": a.activity_type.value,
                "title": a.subject,
                "content": a.body,
                "outcome": a.outcome,
                "direction": a.direction,
                "duration": a.duration,
                "timestamp": a.completed_at or a.created_at,
                "created_by": str(a.created_by)
            })
            
        if lead.audit_logs:
            for log in lead.audit_logs:
                timeline_events.append({
                    "id": log.get("id") or str(uuid4()),
                    "type": "audit",
                    "action": log.get("action"),
                    "title": log.get("action", "").replace("_", " ").title(),
                    "content": log.get("details"),
                    "timestamp": datetime.fromisoformat(log.get("timestamp")) if isinstance(log.get("timestamp"), str) else log.get("timestamp"),
                    "created_by": log.get("user_id")
                })
                
        timeline_events.append({
            "id": f"created-{lead.id}",
            "type": "audit",
            "action": "created",
            "title": "Lead Created",
            "content": f"Lead record initialized for {lead.first_name} {lead.last_name} ({lead.company_name}).",
            "timestamp": lead.created_at,
            "created_by": None
        })
        
        timeline_events.sort(key=lambda x: x["timestamp"] if x["timestamp"] else datetime.min, reverse=True)
        
        for event in timeline_events:
            if isinstance(event["timestamp"], datetime):
                event["timestamp"] = event["timestamp"].isoformat()
                
        return timeline_events


    @staticmethod
    async def delete_lead(lead_id: UUID, tenant_id: UUID) -> bool:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        await lead.delete()
        return True

    @staticmethod
    async def assign_leads(lead_ids: List[UUID], assigned_to: Optional[UUID], tenant_id: UUID) -> List[CrmLead]:
        updated_leads = []
        for lead_id in lead_ids:
            lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
            if lead:
                lead.assigned_to = assigned_to
                lead.updated_at = datetime.utcnow()
                await lead.save()
                updated_leads.append(lead)
        return updated_leads

    @staticmethod
    async def get_sales_agents(tenant_id: UUID) -> List[User]:
        # Return all platform admins or all system users who can be agents
        # Here we'll return all platform_admin users
        return await User.find(User.tenant_id == tenant_id).to_list()

    @staticmethod
    async def get_opportunities(tenant_id: UUID) -> List[Dict[str, Any]]:
        opps = await CrmDeal.find(CrmDeal.tenant_id == tenant_id).sort(-CrmDeal.created_at).to_list()
        res = []
        for opp in opps:
            lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
            agent_name = None
            if opp.assigned_to:
                agent = await User.find_one(User.id == opp.assigned_to)
                if agent:
                    agent_name = f"{agent.first_name} {agent.last_name}"
            
            res.append({
                "opportunity": opp,
                "lead": lead,
                "agent_name": agent_name
            })
        return res

    @staticmethod
    async def update_opportunity_stage(opportunity_id: UUID, stage: DealStage, tenant_id: UUID) -> CrmDeal:
        opp = await CrmDeal.find_one(CrmDeal.id == opportunity_id, CrmDeal.tenant_id == tenant_id)
        if not opp:
            raise ValueError("Opportunity not found")
        opp.stage = stage
        opp.updated_at = datetime.utcnow()
        await opp.save()
        
        lead = await CrmLead.find_one(CrmLead.id == opp.lead_id)
        if lead:
            stage_map = {
                DealStage.qualified_to_buy: LeadStatus.qualified,
                DealStage.presentation_scheduled: LeadStatus.demo_scheduled,
                DealStage.proposal_sent: LeadStatus.proposal_sent,
                DealStage.negotiation: LeadStatus.negotiation,
                DealStage.won: LeadStatus.won,
                DealStage.lost: LeadStatus.lost,
            }
            if stage in stage_map:
                lead.status = stage_map[stage]
                await lead.save()
        return opp

    @staticmethod
    async def send_lead_email(lead_id: UUID, subject: str, message: str, template: Optional[str], user_id: UUID, tenant_id: UUID) -> CrmActivity:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        # Trigger real email sending via SMTP Utility
        try:
            from Utility.email_service import EmailService
            EmailService.send_custom_email(lead.email, subject, message)
            logger.info(f"Real SMTP email successfully sent to {lead.email}")
        except Exception as smtp_err:
            logger.error(f"SMTP execution failed to send real email to {lead.email}: {smtp_err}", exc_info=True)

        activity = CrmActivity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            activity_type=ActivityType.email,
            subject=subject,
            body=f"Template: {template or 'Custom'}\n\n{message}",
            direction="outbound",
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        
        if lead.status == LeadStatus.new:
            lead.status = LeadStatus.contacted
            lead.updated_at = datetime.utcnow()
            await lead.save()
            
        logger.info(f"Email activity logged successfully to lead: {lead.email} with subject: {subject}")
        return activity

    @staticmethod
    async def get_lead_activities(lead_id: UUID, tenant_id: UUID) -> List[CrmActivity]:
        activities = await CrmActivity.find(CrmActivity.lead_id == lead_id, CrmActivity.tenant_id == tenant_id).sort(-CrmActivity.completed_at).to_list()
        return activities

    @staticmethod
    async def log_lead_activity(lead_id: UUID, req, user_id: UUID, tenant_id: UUID) -> CrmActivity:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        activity = CrmActivity(
            tenant_id=tenant_id,
            lead_id=lead.id,
            activity_type=req.activity_type,
            subject=req.subject,
            body=req.body,
            outcome=req.outcome,
            direction=req.direction or "inbound",
            duration=req.duration,
            scheduled_at=req.scheduled_at,
            completed_at=req.completed_at or datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        
        if lead.status == LeadStatus.new:
            lead.status = LeadStatus.contacted
            lead.updated_at = datetime.utcnow()
            await lead.save()
            
        logger.info(f"Activity of type {req.activity_type} manually logged for lead {lead.id}")
        return activity

    @staticmethod
    async def create_client(data: Dict[str, Any], tenant_id: UUID) -> CrmClient:
        """Create a new client from a won deal"""
        deal_id_val = data.get('deal_id') or data.get('opportunity_id')
        client = CrmClient(
            tenant_id=tenant_id,
            company_name=data.get('company_name', ''),
            industry=data.get('industry'),
            region=data.get('location'),
            contact_name=data.get('contact_name', ''),
            email=data.get('email', ''),
            phone=data.get('phone'),
            location=data.get('location'),
            deal_value=data.get('deal_value', 0),
            currency=data.get('currency', 'USD'),
            deal_id=UUID(deal_id_val) if isinstance(deal_id_val, str) else deal_id_val,
            lead_id=UUID(data['lead_id']) if isinstance(data.get('lead_id'), str) else data.get('lead_id'),
            assigned_csm=UUID(data['assigned_csm']) if isinstance(data.get('assigned_csm'), str) else data.get('assigned_csm'),
            contract_signed_date=data.get('contract_signed_date'),
            go_live_date=data.get('go_live_date'),
            account_status=data.get('status', 'active'),
            notes=data.get('notes'),
            custom_fields=data.get('custom_fields', {})
        )
        await client.insert()
        logger.info(f"New client created from deal: {client.company_name}")
        return client

    @staticmethod
    async def get_clients(tenant_id: UUID) -> List[Dict[str, Any]]:
        """Get all clients"""
        clients = await CrmClient.find(CrmClient.tenant_id == tenant_id).sort(-CrmClient.created_at).to_list()
        result = []
        for client in clients:
            result.append({
                "id": str(client.id),
                "company_name": client.company_name,
                "industry": client.industry,
                "region": client.region,
                "contact_name": client.contact_name,
                "email": client.email,
                "phone": client.phone,
                "location": client.location,
                "deal_value": client.deal_value,
                "currency": client.currency,
                "assigned_csm": str(client.assigned_csm) if client.assigned_csm else None,
                "account_status": client.account_status,
                "notes": client.notes,
                "custom_fields": client.custom_fields or {},
                "contract_signed_date": client.contract_signed_date.isoformat() if hasattr(client.contract_signed_date, "isoformat") else str(client.contract_signed_date) if client.contract_signed_date else None,
                "go_live_date": client.go_live_date.isoformat() if hasattr(client.go_live_date, "isoformat") else str(client.go_live_date) if client.go_live_date else None,
                "created_at": client.created_at.isoformat() if hasattr(client.created_at, "isoformat") else str(client.created_at) if client.created_at else None,
                "updated_at": client.updated_at.isoformat() if hasattr(client.updated_at, "isoformat") else str(client.updated_at) if client.updated_at else None,
            })
        return result

    @staticmethod
    async def get_client_by_id(client_id: UUID, tenant_id: UUID) -> Optional[Dict[str, Any]]:
        """Get client details by ID"""
        client = await CrmClient.find_one(CrmClient.id == client_id, CrmClient.tenant_id == tenant_id)
        if not client:
            return None
        return {
            "id": str(client.id),
            "company_name": client.company_name,
            "industry": client.industry,
            "region": client.region,
            "contact_name": client.contact_name,
            "email": client.email,
            "phone": client.phone,
            "location": client.location,
            "deal_value": client.deal_value,
            "currency": client.currency,
            "assigned_csm": str(client.assigned_csm) if client.assigned_csm else None,
            "account_status": client.account_status,
            "notes": client.notes,
            "custom_fields": client.custom_fields or {},
            "contract_signed_date": client.contract_signed_date.isoformat() if hasattr(client.contract_signed_date, "isoformat") else str(client.contract_signed_date) if client.contract_signed_date else None,
            "go_live_date": client.go_live_date.isoformat() if hasattr(client.go_live_date, "isoformat") else str(client.go_live_date) if client.go_live_date else None,
            "created_at": client.created_at.isoformat() if hasattr(client.created_at, "isoformat") else str(client.created_at) if client.created_at else None,
            "updated_at": client.updated_at.isoformat() if hasattr(client.updated_at, "isoformat") else str(client.updated_at) if client.updated_at else None,
        }

    @staticmethod
    async def update_client(client_id: UUID, data: Dict[str, Any], tenant_id: UUID) -> Dict[str, Any]:
        """Update an existing client details and merge custom fields"""
        client = await CrmClient.find_one(CrmClient.id == client_id, CrmClient.tenant_id == tenant_id)
        if not client:
            raise ValueError("Client not found")
        
        # Core fields updates
        if 'company_name' in data: client.company_name = data['company_name']
        if 'industry' in data: client.industry = data['industry']
        if 'region' in data: client.region = data['region']
        if 'contact_name' in data: client.contact_name = data['contact_name']
        if 'email' in data: client.email = data['email']
        if 'phone' in data: client.phone = data['phone']
        if 'location' in data: client.location = data['location']
        if 'deal_value' in data: client.deal_value = data['deal_value']
        if 'currency' in data: client.currency = data['currency']
        if 'account_status' in data: client.account_status = data['account_status']
        if 'notes' in data: client.notes = data['notes']
        
        # Dates
        if 'contract_signed_date' in data:
            if isinstance(data['contract_signed_date'], str):
                client.contract_signed_date = datetime.strptime(data['contract_signed_date'][:10], "%Y-%m-%d").date()
            else:
                client.contract_signed_date = data['contract_signed_date']
        if 'go_live_date' in data:
            if isinstance(data['go_live_date'], str):
                client.go_live_date = datetime.strptime(data['go_live_date'][:10], "%Y-%m-%d").date()
            else:
                client.go_live_date = data['go_live_date']
        
        # Merge custom fields
        if 'custom_fields' in data:
            if client.custom_fields is None:
                client.custom_fields = {}
            for key, val in data['custom_fields'].items():
                client.custom_fields[key] = val
                
        client.updated_at = datetime.utcnow()
        await client.save()
        
        # Return transformed client dict
        return {
            "id": str(client.id),
            "company_name": client.company_name,
            "industry": client.industry,
            "region": client.region,
            "contact_name": client.contact_name,
            "email": client.email,
            "phone": client.phone,
            "location": client.location,
            "deal_value": client.deal_value,
            "currency": client.currency,
            "assigned_csm": str(client.assigned_csm) if client.assigned_csm else None,
            "account_status": client.account_status,
            "notes": client.notes,
            "custom_fields": client.custom_fields or {},
            "contract_signed_date": client.contract_signed_date.isoformat() if hasattr(client.contract_signed_date, "isoformat") else str(client.contract_signed_date) if client.contract_signed_date else None,
            "go_live_date": client.go_live_date.isoformat() if hasattr(client.go_live_date, "isoformat") else str(client.go_live_date) if client.go_live_date else None,
            "created_at": client.created_at.isoformat() if hasattr(client.created_at, "isoformat") else str(client.created_at) if client.created_at else None,
            "updated_at": client.updated_at.isoformat() if hasattr(client.updated_at, "isoformat") else str(client.updated_at) if client.updated_at else None,
        }


    # ── Deals Management ──────────────────────────────────────────────────────
    
    STAGE_PROBABILITY_MAP = {
        DealStage.new: 10,
        DealStage.qualified: 25,
        DealStage.demo_scheduled: 40,
        DealStage.demo_completed: 60,
        DealStage.proposal_sent: 75,
        DealStage.negotiation: 90,
        DealStage.won: 100,
        DealStage.lost: 0
    }
    
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
        limit: int = 10
    ) -> Dict[str, Any]:
        """Get deals. Supports grouped stages (Kanban) or flat paginated list (Table)."""
        if grouped:
            deals = await CrmDeal.find(CrmDeal.tenant_id == tenant_id).sort(-CrmDeal.created_at).to_list()
            result = {}
            for s in DealStage:
                result[s.value] = []
            
            for deal in deals:
                lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
                agent_name = None
                if deal.assigned_to:
                    agent = await User.find_one(User.id == deal.assigned_to)
                    if agent:
                        agent_name = f"{agent.first_name} {agent.last_name}"
                
                activities = await CrmActivity.find(CrmActivity.deal_id == deal.id).sort(-CrmActivity.completed_at).to_list()
                
                deal_data = {
                    "id": str(deal.id),
                    "name": deal.name,
                    "company": lead.company_name if lead else deal.name,
                    "contact": f"{lead.first_name} {lead.last_name}" if lead else "",
                    "email": lead.email if lead else "",
                    "phone": lead.phone if lead else "",
                    "location": lead.region if lead else "",
                    "value": deal.deal_value,
                    "currency": deal.currency,
                    "priority": deal.priority or "medium",
                    "source": lead.source.value if lead else deal.source,
                    "assignedTo": agent_name,
                    "assigned_to": str(deal.assigned_to) if deal.assigned_to else None,
                    "createdDate": deal.created_at.strftime("%Y-%m-%d") if deal.created_at else "",
                    "expectedCloseDate": deal.close_date.strftime("%Y-%m-%d") if deal.close_date else "",
                    "daysInStage": deal.days_in_stage,
                    "stage": deal.stage.value,
                    "probability_pct": deal.probability_pct,
                    "contract": {
                        "status": deal.contract_status,
                        "sentDate": deal.contract_sent_date.strftime("%Y-%m-%d") if deal.contract_sent_date else None,
                        "signedDate": deal.contract_signed_date.strftime("%Y-%m-%d") if deal.contract_signed_date else None,
                        "file": deal.contract_file,
                        "version": deal.contract_version,
                    },
                    "pricing": {
                        "basePrice": deal.base_price,
                        "discountPct": deal.discount_pct,
                        "finalPrice": deal.final_price,
                        "breakdown": deal.pricing_breakdown,
                    },
                    "paymentTerms": {
                        "type": deal.payment_type,
                        "schedule": deal.payment_schedule,
                    },
                    "legal": {
                        "reviewStatus": deal.legal_review_status,
                        "reviewer": deal.legal_reviewer,
                        "notes": deal.legal_notes,
                        "reviewedDate": deal.legal_reviewed_date.strftime("%Y-%m-%d") if deal.legal_reviewed_date else None,
                    },
                    "approval": {
                        "status": deal.approval_status,
                        "approvers": deal.approvers,
                    },
                    "activities": [
                        {
                            "id": str(a.id),
                            "type": a.activity_type.value,
                            "description": a.subject,
                            "date": a.completed_at.strftime("%Y-%m-%d %I:%M %p") if a.completed_at else "",
                            "by": str(a.created_by),
                        }
                        for a in activities
                    ]
                }
                
                if deal.stage.value in result:
                    result[deal.stage.value].append(deal_data)
            
            return result
        else:
            find_query = {"tenant_id": tenant_id}
            if stage and stage != "all":
                try:
                    find_query["stage"] = DealStage(stage)
                except ValueError:
                    pass
            if priority and priority != "all":
                find_query["priority"] = priority
            
            if search:
                search_regex = {"$regex": search, "$options": "i"}
                matching_leads = await CrmLead.find({"tenant_id": tenant_id, "$or": [
                    {"company_name": search_regex},
                    {"first_name": search_regex},
                    {"last_name": search_regex},
                    {"email": search_regex}
                ]}).to_list()
                matching_lead_ids = [lead.id for lead in matching_leads]
                
                find_query["$or"] = [
                    {"name": search_regex},
                    {"lead_id": {"$in": matching_lead_ids}}
                ]
            
            total_count = await CrmDeal.find(find_query).count()
            
            # Apply sorting
            sort_field_map = {
                "created_at": CrmDeal.created_at,
                "deal_value": CrmDeal.deal_value,
                "name": CrmDeal.name,
                "close_date": CrmDeal.close_date,
                "stage": CrmDeal.stage,
                "probability_pct": CrmDeal.probability_pct
            }
            sort_field = sort_field_map.get(sort_by, CrmDeal.created_at)
            sort_order_sign = -sort_field if sort_order == "desc" else +sort_field
            
            skip = (page - 1) * limit
            deals = await CrmDeal.find(find_query).sort(sort_order_sign).skip(skip).limit(limit).to_list()
            
            flat_deals = []
            for deal in deals:
                lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
                agent_name = None
                if deal.assigned_to:
                    agent = await User.find_one(User.id == deal.assigned_to)
                    if agent:
                        agent_name = f"{agent.first_name} {agent.last_name}"
                
                flat_deals.append({
                    "id": str(deal.id),
                    "name": deal.name,
                    "company": lead.company_name if lead else deal.name,
                    "contact": f"{lead.first_name} {lead.last_name}" if lead else "",
                    "email": lead.email if lead else "",
                    "phone": lead.phone if lead else "",
                    "location": lead.region if lead else "",
                    "value": deal.deal_value,
                    "currency": deal.currency,
                    "priority": deal.priority or "medium",
                    "source": lead.source.value if lead else deal.source,
                    "assignedTo": agent_name,
                    "assigned_to": str(deal.assigned_to) if deal.assigned_to else None,
                    "createdDate": deal.created_at.strftime("%Y-%m-%d") if deal.created_at else "",
                    "expectedCloseDate": deal.close_date.strftime("%Y-%m-%d") if deal.close_date else "",
                    "daysInStage": deal.days_in_stage,
                    "stage": deal.stage.value,
                    "probability_pct": deal.probability_pct
                })
                
            return {
                "deals": flat_deals,
                "total": total_count,
                "page": page,
                "limit": limit,
                "pages": (total_count + limit - 1) // limit if limit > 0 else 1
            }

    @staticmethod
    async def create_deal(data: Dict[str, Any], user_id: UUID, tenant_id: UUID) -> CrmDeal:
        """Create a new deal"""
        lead_data = data.get("lead", {})
        if lead_data.get("email"):
            existing_lead = await CrmLead.find_one(CrmLead.email == lead_data["email"].lower(), CrmLead.tenant_id == tenant_id)
            if existing_lead:
                lead = existing_lead
            else:
                lead = CrmLead(
                    tenant_id=tenant_id,
                    first_name=lead_data.get("first_name", ""),
                    last_name=lead_data.get("last_name", ""),
                    email=lead_data["email"].lower(),
                    phone=lead_data.get("phone"),
                    company_name=lead_data.get("company_name", data.get("company", "")),
                    company_size=lead_data.get("company_size"),
                    industry=lead_data.get("industry"),
                    region=lead_data.get("region"),
                    source=LeadSource.manual,
                    status=LeadStatus.qualified,
                )
                await lead.insert()
        elif data.get("lead_id"):
            lead = await CrmLead.find_one(CrmLead.id == UUID(str(data["lead_id"])), CrmLead.tenant_id == tenant_id)
            if not lead:
                raise ValueError("Lead not found")
        else:
            lead = None
        
        stage_val = data.get("stage", "appointment_scheduled")
        try:
            stage_enum = DealStage(stage_val)
        except ValueError:
            stage_enum = DealStage.appointment_scheduled
            
        probability = CrmService.STAGE_PROBABILITY_MAP.get(stage_enum, 10)
        
        expected_close = None
        if data.get("expectedCloseDate"):
            expected_close = datetime.strptime(data["expectedCloseDate"][:10], "%Y-%m-%d").date()
        elif data.get("close_date"):
            expected_close = datetime.strptime(data["close_date"][:10], "%Y-%m-%d").date()

        assigned_to_uuid = None
        if data.get("assigned_to"):
            assigned_to_uuid = UUID(str(data["assigned_to"]))
        elif data.get("assignedTo"):
            assigned_to_uuid = user_id
        
        deal_lead_id = lead.id if lead else None
        deal_name = data.get("deal_name") or data.get("name") or "New Deal"
        deal = CrmDeal(
            tenant_id=tenant_id,
            lead_id=deal_lead_id,
            deal_name=deal_name,
            stage=stage_enum,
            deal_value=data.get("value", data.get("deal_value", 0)),
            currency=data.get("currency", "USD"),
            close_date=expected_close,
            assigned_to=assigned_to_uuid,
            probability=probability,
            priority=data.get("priority", "medium"),
            source=data.get("source"),
            days_in_stage=0,
        )
        
        contract_data = data.get("contract", {})
        if contract_data:
            deal.contract_status = contract_data.get("status")
            if contract_data.get("sentDate"):
                deal.contract_sent_date = datetime.strptime(contract_data["sentDate"][:10], "%Y-%m-%d").date()
            if contract_data.get("signedDate"):
                deal.contract_signed_date = datetime.strptime(contract_data["signedDate"][:10], "%Y-%m-%d").date()
            deal.contract_file = contract_data.get("file")
            deal.contract_version = contract_data.get("version")
            
        pricing_data = data.get("pricing", {})
        if pricing_data:
            deal.base_price = pricing_data.get("basePrice", 0)
            deal.discount_pct = pricing_data.get("discountPct", 0.0)
            deal.final_price = pricing_data.get("finalPrice", 0)
            deal.pricing_breakdown = pricing_data.get("breakdown", [])
            
        payment_data = data.get("paymentTerms", {})
        if payment_data:
            deal.payment_type = payment_data.get("type")
            deal.payment_schedule = payment_data.get("schedule", [])
            
        legal_data = data.get("legal", {})
        if legal_data:
            deal.legal_review_status = legal_data.get("reviewStatus")
            deal.legal_reviewer = legal_data.get("reviewer")
            deal.legal_notes = legal_data.get("notes")
            if legal_data.get("reviewedDate"):
                deal.legal_reviewed_date = datetime.strptime(legal_data["reviewedDate"][:10], "%Y-%m-%d").date()
                
        approval_data = data.get("approval", {})
        if approval_data:
            deal.approval_status = approval_data.get("status")
            deal.approvers = approval_data.get("approvers", [])
            
        await deal.insert()
        
        activity = CrmActivity(
            tenant_id=tenant_id,
            deal_id=deal.id,
            lead_id=deal.lead_id,
            activity_type=ActivityType.note,
            subject="Deal Created",
            body=f"Deal '{deal.name}' has been created manually.",
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        
        audit = CrmDealAuditLog(
            tenant_id=tenant_id,
            deal_id=deal.id,
            user_id=user_id,
            action="creation",
            details=f"Deal created manually. Stage set to {deal.stage.value}."
        )
        await audit.insert()
        
        logger.info(f"New deal created: {deal.name}")
        return deal

    @staticmethod
    async def update_deal(deal_id: UUID, data: Dict[str, Any], tenant_id: UUID) -> CrmDeal:
        """Update an existing deal"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")
        
        if "name" in data:
            deal.name = data["name"]
        if "value" in data:
            deal.deal_value = data["value"]
        elif "deal_value" in data:
            deal.deal_value = data["deal_value"]
            
        if "currency" in data:
            deal.currency = data["currency"]
            
        if "close_date" in data:
            deal.close_date = datetime.strptime(data["close_date"][:10], "%Y-%m-%d").date() if data["close_date"] else None
        elif "expectedCloseDate" in data:
            deal.close_date = datetime.strptime(data["expectedCloseDate"][:10], "%Y-%m-%d").date() if data["expectedCloseDate"] else None
            
        if "assigned_to" in data:
            deal.assigned_to = UUID(str(data["assigned_to"])) if data["assigned_to"] else None
        if "priority" in data:
            deal.priority = data["priority"]
            
        if "stage" in data:
            try:
                new_stage = DealStage(data["stage"])
                deal.stage = new_stage
                deal.probability_pct = CrmService.STAGE_PROBABILITY_MAP.get(new_stage, 10)
            except ValueError:
                pass
        elif "probability_pct" in data:
            deal.probability_pct = data["probability_pct"]
        
        if "contract" in data:
            contract = data["contract"]
            if "status" in contract:
                deal.contract_status = contract["status"]
            if "sentDate" in contract:
                deal.contract_sent_date = datetime.strptime(contract["sentDate"][:10], "%Y-%m-%d").date() if contract["sentDate"] else None
            if "signedDate" in contract:
                deal.contract_signed_date = datetime.strptime(contract["signedDate"][:10], "%Y-%m-%d").date() if contract["signedDate"] else None
            if "file" in contract:
                deal.contract_file = contract["file"]
            if "version" in contract:
                deal.contract_version = contract["version"]
        
        if "pricing" in data:
            pricing = data["pricing"]
            if "basePrice" in pricing:
                deal.base_price = pricing["basePrice"]
            if "discountPct" in pricing:
                deal.discount_pct = pricing["discountPct"]
            if "finalPrice" in pricing:
                deal.final_price = pricing["finalPrice"]
            if "breakdown" in pricing:
                deal.pricing_breakdown = pricing["breakdown"]
        
        if "paymentTerms" in data:
            payment = data["paymentTerms"]
            if "type" in payment:
                deal.payment_type = payment["type"]
            if "schedule" in payment:
                deal.payment_schedule = payment["schedule"]
        
        if "legal" in data:
            legal = data["legal"]
            if "reviewStatus" in legal:
                deal.legal_review_status = legal["reviewStatus"]
            if "reviewer" in legal:
                deal.legal_reviewer = legal["reviewer"]
            if "notes" in legal:
                deal.legal_notes = legal["notes"]
            if "reviewedDate" in legal:
                deal.legal_reviewed_date = datetime.strptime(legal["reviewedDate"][:10], "%Y-%m-%d").date() if legal["reviewedDate"] else None
        
        if "approval" in data:
            approval = data["approval"]
            if "status" in approval:
                deal.approval_status = approval["status"]
            if "approvers" in approval:
                deal.approvers = approval["approvers"]
        
        deal.updated_at = datetime.utcnow()
        await deal.save()
        return deal

    @staticmethod
    async def move_deal_stage(deal_id: UUID, new_stage: str, user_id: UUID, tenant_id: UUID) -> CrmDeal:
        """Move a deal to a different stage, updating probability, history, audit log, and notifying owner"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")
        
        try:
            stage_enum = DealStage(new_stage)
        except ValueError:
            raise ValueError(f"Invalid stage: {new_stage}")
            
        old_stage = deal.stage
        if old_stage == stage_enum:
            return deal
            
        deal.stage = stage_enum
        deal.probability_pct = CrmService.STAGE_PROBABILITY_MAP.get(stage_enum, 10)
        deal.days_in_stage = 0
        deal.updated_at = datetime.utcnow()
        await deal.save()
        
        history = CrmDealStageHistory(
            tenant_id=tenant_id,
            deal_id=deal.id,
            old_stage=old_stage.value,
            new_stage=stage_enum.value,
            changed_by=user_id
        )
        await history.insert()
        
        audit = CrmDealAuditLog(
            tenant_id=tenant_id,
            deal_id=deal.id,
            user_id=user_id,
            action="stage_change",
            details=f"Stage changed from {old_stage.value} to {stage_enum.value}. Probability set to {deal.probability_pct}%."
        )
        await audit.insert()
        
        activity = CrmActivity(
            tenant_id=tenant_id,
            deal_id=deal.id,
            lead_id=deal.lead_id,
            activity_type=ActivityType.note,
            subject=f"Stage updated: {stage_enum.value}",
            body=f"Stage transitioned from '{old_stage.value}' to '{stage_enum.value}'. Probability: {deal.probability_pct}%.",
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        
        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
        if lead:
            stage_map = {
                DealStage.qualified_to_buy: LeadStatus.qualified,
                DealStage.presentation_scheduled: LeadStatus.demo_scheduled,
                DealStage.proposal_sent: LeadStatus.proposal_sent,
                DealStage.negotiation: LeadStatus.negotiation,
                DealStage.won: LeadStatus.won,
                DealStage.lost: LeadStatus.lost,
            }
            if stage_enum in stage_map:
                lead.status = stage_map[stage_enum]
                lead.updated_at = datetime.utcnow()
                await lead.save()
                
        if deal.assigned_to:
            owner = await User.find_one(User.id == deal.assigned_to)
            if owner and owner.email:
                try:
                    from Utility.email_service import EmailService
                    subject = f"Deal Stage Transitioned: {deal.name}"
                    message = f"Hi {owner.first_name},\n\nThe deal '{deal.name}' has been moved to stage '{stage_enum.value}' (Probability: {deal.probability_pct}%).\n\nDetails:\n- Deal Name: {deal.name}\n- Preceding Stage: {old_stage.value}\n- New Stage: {stage_enum.value}\n- Expected Close Date: {deal.close_date or 'N/A'}\n- Value: {deal.deal_value} {deal.currency}\n\nBest,\nCRM Notifications"
                    EmailService.send_custom_email(owner.email, subject, message)
                    logger.info(f"Notification email sent to owner {owner.email}")
                except Exception as email_err:
                    logger.error(f"Failed to send email to owner: {email_err}", exc_info=True)
                    
        return deal

    @staticmethod
    async def delete_deal(deal_id: UUID, tenant_id: UUID) -> bool:
        """Delete a deal"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")
        
        await CrmActivity.find(CrmActivity.deal_id == deal_id).delete()
        await CrmDealStageHistory.find(CrmDealStageHistory.deal_id == deal_id).delete()
        await CrmDealAuditLog.find(CrmDealAuditLog.deal_id == deal_id).delete()
        await CrmProposal.find(CrmProposal.deal_id == deal_id).delete()
        await deal.delete()
        return True

    @staticmethod
    async def add_deal_activity(deal_id: UUID, activity_data: Dict[str, Any], user_id: UUID, tenant_id: UUID) -> CrmActivity:
        """Add an activity to a deal"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")
        
        activity = CrmActivity(
            tenant_id=tenant_id,
            deal_id=deal.id,
            lead_id=deal.lead_id,
            activity_type=ActivityType(activity_data.get("type", "note")),
            subject=activity_data.get("description", activity_data.get("subject", "Activity")),
            body=activity_data.get("body"),
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        return activity

    @staticmethod
    async def get_deal_timeline(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        """Retrieve chronological timeline events (activity feed + audit log logs)."""
        activities = await CrmActivity.find(CrmActivity.deal_id == deal_id, CrmActivity.tenant_id == tenant_id).to_list()
        history = await CrmDealStageHistory.find(CrmDealStageHistory.deal_id == deal_id, CrmDealStageHistory.tenant_id == tenant_id).to_list()
        audit_logs = await CrmDealAuditLog.find(CrmDealAuditLog.deal_id == deal_id, CrmDealAuditLog.tenant_id == tenant_id).to_list()
        
        timeline_events = []
        
        for a in activities:
            timeline_events.append({
                "id": str(a.id),
                "type": "activity",
                "activity_type": a.activity_type.value,
                "title": a.subject,
                "content": a.body,
                "outcome": a.outcome,
                "direction": a.direction,
                "duration": a.duration,
                "timestamp": a.completed_at or a.created_at,
                "created_by": str(a.created_by)
            })
            
        for h in history:
            timeline_events.append({
                "id": str(h.id),
                "type": "stage_change",
                "old_stage": h.old_stage,
                "new_stage": h.new_stage,
                "title": "Stage Changed",
                "content": f"Deal stage transitioned from '{h.old_stage}' to '{h.new_stage}'.",
                "timestamp": h.changed_at,
                "created_by": str(h.changed_by)
            })

        for log in audit_logs:
            if log.action != "stage_change":
                timeline_events.append({
                    "id": str(log.id),
                    "type": "audit",
                    "action": log.action,
                    "title": f"Action: {log.action.capitalize()}",
                    "content": log.details,
                    "timestamp": log.timestamp,
                    "created_by": str(log.user_id)
                })
        
        timeline_events.sort(key=lambda x: x["timestamp"], reverse=True)
        
        for event in timeline_events:
            if isinstance(event["timestamp"], datetime):
                event["timestamp"] = event["timestamp"].isoformat()
                
        return timeline_events

    @staticmethod
    async def convert_deal_to_client(deal_id: UUID, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Convert won deal to Client"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")
        
        old_stage = deal.stage
        deal.stage = DealStage.won
        deal.probability_pct = 100
        deal.updated_at = datetime.utcnow()
        await deal.save()
        
        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
        if lead:
            lead.status = LeadStatus.won
            lead.updated_at = datetime.utcnow()
            await lead.save()
            
        history = CrmDealStageHistory(
            tenant_id=tenant_id,
            deal_id=deal.id,
            old_stage=old_stage.value,
            new_stage=DealStage.won.value,
            changed_by=user_id
        )
        await history.insert()
        
        audit = CrmDealAuditLog(
            tenant_id=tenant_id,
            deal_id=deal.id,
            user_id=user_id,
            action="conversion",
            details="Deal marked as Won and converted to Client."
        )
        await audit.insert()
        
        client = CrmClient(
            tenant_id=tenant_id,
            company_name=lead.company_name if lead else deal.name,
            industry=lead.industry if lead else None,
            region=lead.region if lead else None,
            contact_name=f"{lead.first_name} {lead.last_name}" if lead else "Contact",
            email=lead.email if lead else "contact@example.com",
            phone=lead.phone if lead else None,
            location=lead.region if lead else None,
            deal_value=deal.deal_value,
            currency=deal.currency,
            deal_id=deal.id,
            lead_id=deal.lead_id,
            assigned_csm=deal.assigned_to or user_id,
            contract_signed_date=datetime.utcnow().date(),
            go_live_date=None,
            account_status="active",
            notes=f"Converted from won deal '{deal.name}'."
        )
        await client.insert()
        
        activity = CrmActivity(
            tenant_id=tenant_id,
            deal_id=deal.id,
            lead_id=deal.lead_id,
            activity_type=ActivityType.note,
            subject="Deal Converted to Client",
            body=f"Deal converted to Client record '{client.company_name}' successfully.",
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        
        return {
            "deal": deal,
            "client": client,
            "message": "Deal converted successfully"
        }

    @staticmethod
    async def change_lead_status(lead_id: UUID, new_status: LeadStatus, reason: Optional[str], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        old_status = lead.status
        lead.status = new_status
        lead.updated_at = datetime.utcnow()
        await lead.save()
        await CrmService.log_lead_audit_and_activity(
            lead=lead, action="status_change",
            details=f"Status changed from {old_status.value} to {new_status.value}. Reason: {reason or 'N/A'}",
            user_id=user_id,
            activity_subject=f"Status Changed: {new_status.value}",
            activity_body=f"Lead moved from '{old_status.value}' to '{new_status.value}'.\nReason: {reason or 'Not provided'}",
            activity_type=ActivityType.note
        )
        return {"lead": lead, "old_status": old_status.value, "new_status": new_status.value}

    @staticmethod
    async def schedule_follow_up(lead_id: UUID, data, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        from uuid import uuid4
        from Models.crm_task import CrmTask
        timestamp = datetime.utcnow()
        task = CrmTask(
            tenant_id=tenant_id, lead_id=lead.id,
            title=f"Follow-up: {data.purpose}",
            description=data.notes or "",
            due_date=data.scheduled_date,
            reminder_time="15m",
            assigned_to=str(data.assigned_to) if data.assigned_to else str(user_id),
            priority="medium"
        )
        await task.insert()
        await CrmService.log_lead_audit_and_activity(
            lead=lead, action="follow_up_scheduled",
            details=f"Follow-up scheduled: {data.purpose} for {data.scheduled_date.isoformat()}",
            user_id=user_id,
            activity_subject="Follow-up Scheduled",
            activity_body=f"Purpose: {data.purpose}\nDate: {data.scheduled_date.isoformat()}\nReminder: {data.reminder_date.isoformat() if data.reminder_date else 'None'}",
            activity_type=ActivityType.task
        )
        return {"message": "Follow-up scheduled", "task_id": str(task.id)}

    @staticmethod
    async def log_call(lead_id: UUID, data, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        activity = CrmActivity(
            tenant_id=tenant_id, lead_id=lead.id,
            activity_type=ActivityType.call,
            subject=data.subject,
            body=data.notes or "",
            outcome=data.outcome,
            direction=data.direction,
            duration=data.duration,
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        await CrmService.log_lead_audit_and_activity(
            lead=lead, action="call_logged",
            details=f"Call logged: {data.subject} (Duration: {data.duration}, Outcome: {data.outcome or 'N/A'})",
            user_id=user_id
        )
        return {"message": "Call logged", "activity_id": str(activity.id)}

    @staticmethod
    async def schedule_meeting(lead_id: UUID, data, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        activity = CrmActivity(
            tenant_id=tenant_id, lead_id=lead.id,
            activity_type=ActivityType.meeting,
            subject=data.title,
            body=f"Meeting scheduled\nLink: {data.meeting_link or 'TBD'}\nAttendees: {', '.join(data.attendees) if data.attendees else 'None'}\nNotes: {data.notes or ''}",
            outcome=data.outcome,
            scheduled_at=data.scheduled_time,
            duration=str(data.duration_minutes),
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()
        await CrmService.log_lead_audit_and_activity(
            lead=lead, action="meeting_scheduled",
            details=f"Meeting scheduled: {data.title} for {data.scheduled_time.isoformat()}",
            user_id=user_id,
            activity_subject="Meeting Scheduled",
            activity_body=f"Title: {data.title}\nTime: {data.scheduled_time.isoformat()}\nDuration: {data.duration_minutes} min\nLink: {data.meeting_link or 'TBD'}",
            activity_type=ActivityType.meeting
        )
        return {"message": "Meeting scheduled", "activity_id": str(activity.id)}

    @staticmethod
    async def create_task(lead_id: UUID, data, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        from Models.crm_task import CrmTask
        task = CrmTask(
            tenant_id=tenant_id,
            lead_id=lead.id,
            title=data.title,
            description=data.description or "",
            type=data.type or "task",
            priority=data.priority or "medium",
            due_date=data.due_date,
            owner_id=data.owner_id or user_id,
            assigned_to=data.assigned_to or user_id,
            reminder_time=data.reminder_time or "15m",
            status="not_started",
            created_by=user_id,
            updated_by=user_id
        )
        await task.insert()
        await CrmService.log_lead_audit_and_activity(
            lead=lead, action="task_created",
            details=f"Task created: {data.title}",
            user_id=user_id,
            activity_subject="Task Created",
            activity_body=f"Title: {data.title}\nDue: {data.due_date.isoformat() if data.due_date else 'No due date'}",
            activity_type=ActivityType.task
        )
        return {"message": "Task created", "task_id": str(task.id)}

    @staticmethod
    async def convert_lead_to_contact(
        lead_id: UUID, 
        user_id: UUID, 
        tenant_id: UUID,
        copy_notes: bool = True,
        copy_activities: bool = True,
        copy_tasks: bool = True,
        copy_meetings: bool = True,
        copy_calls: bool = True,
        copy_emails: bool = True
    ) -> Dict[str, Any]:
        """
        Convert Lead to Contact workflow inspired by HubSpot CRM.
        
        Business Rules:
        - Lead is NEVER deleted
        - Lead Status changes to 'Converted'
        - New Contact record is created with all important Lead information
        - Relationship between Lead and Contact is preserved
        - Only Qualified, Won, or Negotiation leads can be converted
        """
        
        # Step 1: Validate Lead exists and belongs to tenant
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        # Step 2: Check if Lead is already converted
        if lead.is_converted:
            raise ValueError(f"Lead is already converted. Contact ID: {str(lead.converted_contact_id)}")
        
        # Step 3: Validate Lead Status (only qualified, won, or negotiation can be converted)
        allowed_statuses = [LeadStatus.qualified, LeadStatus.won, LeadStatus.negotiation]
        if lead.status not in allowed_statuses:
            raise ValueError(
                f"Lead must be in 'Qualified', 'Won', or 'Negotiation' status to be converted. "
                f"Current status: {lead.status.value}"
            )
        
        # Step 4: Check for duplicate Contact (by email or phone)
        from Models.crm_contacts import CrmContact, CrmTimeline, CrmContactNote, CrmContactCall, CrmContactMeeting, CrmContactEmail
        
        existing_contact = None
        if lead.email:
            existing_contact = await CrmContact.find_one(
                CrmContact.tenant_id == tenant_id,
                CrmContact.email == lead.email,
                CrmContact.is_deleted == False
            )
        
        if not existing_contact and lead.phone:
            existing_contact = await CrmContact.find_one(
                CrmContact.tenant_id == tenant_id,
                CrmContact.phone == lead.phone,
                CrmContact.is_deleted == False
            )
        
        if existing_contact:
            return {
                "success": False,
                "error": "duplicate_contact",
                "message": "This Contact already exists.",
                "existing_contact_id": str(existing_contact.id),
                "existing_contact": {
                    "id": str(existing_contact.id),
                    "name": f"{existing_contact.first_name} {existing_contact.last_name or ''}".strip(),
                    "email": existing_contact.email,
                    "phone": existing_contact.phone
                }
            }
        
        # Step 5: Start Transaction-like operation (Beanie doesn't support transactions natively on standalone MongoDB)
        from Database import mongodb_client
        session = None
        use_transaction = False
        try:
            session = await mongodb_client.start_session()
            session.start_transaction()
            use_transaction = True
        except Exception as te:
            logger.warning(f"Could not start MongoDB transaction session (likely standalone database): {te}")
            if session:
                await session.end_session()
                session = None
                
        try:
            # Create new Contact with all Lead information
            contact = CrmContact(
                tenant_id=tenant_id,
                lead_id=lead_id,  # Preserve relationship
                
                # Basic Information
                first_name=lead.first_name,
                last_name=lead.last_name,
                full_name=f"{lead.first_name} {lead.last_name or ''}".strip(),
                email=lead.email,
                phone=lead.phone,
                
                # Company Information
                company_name=lead.company_name,
                industry=lead.industry,
                company_size=lead.company_size,
                website=lead.website,
                
                # Job Details
                job_title=lead.job_title,
                
                # Location
                region=lead.region,
                
                # Assignment & Tracking
                owner_id=lead.assigned_to or user_id,
                source=lead.source.value if lead.source else "manual",
                lead_source=lead.source.value if lead.source else "manual",
                priority=lead.priority.value if lead.priority else None,
                
                # Status & Lifecycle
                status="active",
                lead_status=lead.status.value if lead.status else "new",
                lifecycle_stage=lead.lifecycle_stage or "lead",
                
                # Tags
                tags=lead.tags if lead.tags else [],
                
                # Notes
                notes=lead.notes,
                
                # Metadata
                created_by=user_id,
                updated_by=user_id
            )
            
            # Step 6: Copy Notes List array if requested
            if copy_notes and lead.notes_list:
                contact.notes_list = lead.notes_list.copy()
            
            # Step 7: Copy Documents
            if lead.documents:
                contact.documents = lead.documents.copy()
            
            # Insert Contact
            if use_transaction:
                await contact.insert(session=session)
            else:
                await contact.insert()
                
            # Copy notes to CrmContactNote documents specifically so they show in Notes tab
            if copy_notes and lead.notes_list:
                for note_dict in lead.notes_list:
                    created_at_dt = datetime.utcnow()
                    if note_dict.get("created_at"):
                        try:
                            created_at_dt = datetime.fromisoformat(note_dict["created_at"])
                        except Exception:
                            pass
                    contact_note = CrmContactNote(
                        id=UUID(note_dict["id"]) if note_dict.get("id") else uuid4(),
                        contact_id=contact.id,
                        tenant_id=tenant_id,
                        lead_id=lead_id,
                        body=note_dict.get("text") or note_dict.get("body") or "",
                        created_by=UUID(note_dict["created_by"]) if note_dict.get("created_by") else user_id,
                        created_at=created_at_dt,
                        updated_at=created_at_dt
                    )
                    if use_transaction:
                        await contact_note.insert(session=session)
                    else:
                        await contact_note.insert()
            
            # Step 9: Update Lead with conversion information
            lead.is_converted = True
            lead.status = LeadStatus.converted
            lead.converted_contact_id = contact.id
            lead.converted_at = datetime.utcnow()
            lead.converted_by = user_id
            lead.updated_at = datetime.utcnow()
            if use_transaction:
                await lead.save(session=session)
            else:
                await lead.save()
            
            # Step 10: Copy Activities (duplicating CrmActivity with contact_id set)
            copied_activities_count = 0
            if copy_activities:
                activities = await CrmActivity.find(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.lead_id == lead_id
                ).to_list()
                
                for act in activities:
                    new_act = CrmActivity(
                        tenant_id=tenant_id,
                        lead_id=lead_id,
                        deal_id=act.deal_id,
                        contact_id=contact.id,
                        activity_type=act.activity_type,
                        subject=act.subject,
                        body=act.body,
                        outcome=act.outcome,
                        direction=act.direction,
                        duration=act.duration,
                        scheduled_at=act.scheduled_at,
                        completed_at=act.completed_at,
                        created_by=act.created_by,
                        created_at=act.created_at
                    )
                    if use_transaction:
                        await new_act.insert(session=session)
                    else:
                        await new_act.insert()
                    copied_activities_count += 1
            
            # Step 11: Copy Tasks (duplicating CrmTask with contact_id set)
            copied_tasks_count = 0
            if copy_tasks:
                tasks = await CrmTask.find(
                    CrmTask.tenant_id == tenant_id,
                    CrmTask.lead_id == lead_id
                ).to_list()
                
                for task in tasks:
                    new_task = CrmTask(
                        tenant_id=tenant_id,
                        lead_id=lead_id,
                        deal_id=task.deal_id,
                        contact_id=contact.id,
                        title=task.title,
                        description=task.description,
                        due_date=task.due_date,
                        priority=task.priority,
                        assigned_to=task.assigned_to,
                        status=task.status,
                        due_time=task.due_time,
                        reminder_time=task.reminder_time,
                        completed_at=task.completed_at,
                        created_at=task.created_at
                    )
                    if use_transaction:
                        await new_task.insert(session=session)
                    else:
                        await new_task.insert()
                    copied_tasks_count += 1
            
            # Step 12: Copy Meetings, Calls, Emails specifically to contact tables
            copied_calls_count = 0
            copied_meetings_count = 0
            copied_emails_count = 0
            
            if copy_calls or copy_meetings or copy_emails:
                activities = await CrmActivity.find(
                    CrmActivity.tenant_id == tenant_id,
                    CrmActivity.lead_id == lead_id
                ).to_list()
                
                for act in activities:
                    if copy_calls and act.activity_type == ActivityType.call:
                        contact_call = CrmContactCall(
                            contact_id=contact.id,
                            tenant_id=tenant_id,
                            lead_id=lead_id,
                            subject=act.subject,
                            notes=act.body,
                            outcome=act.outcome or "connected",
                            duration_seconds=0,
                            created_by=act.created_by,
                            created_at=act.completed_at or act.created_at
                        )
                        if use_transaction:
                            await contact_call.insert(session=session)
                        else:
                            await contact_call.insert()
                        copied_calls_count += 1
                        
                    elif copy_meetings and (act.activity_type == ActivityType.meeting or act.activity_type == ActivityType.demo):
                        contact_meeting = CrmContactMeeting(
                            contact_id=contact.id,
                            tenant_id=tenant_id,
                            lead_id=lead_id,
                            title=act.subject,
                            description=act.body,
                            start_time=act.scheduled_at or act.completed_at or act.created_at,
                            end_time=act.completed_at or act.scheduled_at or act.created_at,
                            outcome=act.outcome or "scheduled",
                            created_by=act.created_by,
                            created_at=act.created_at
                        )
                        if use_transaction:
                            await contact_meeting.insert(session=session)
                        else:
                            await contact_meeting.insert()
                        copied_meetings_count += 1
                        
                    elif copy_emails and act.activity_type == ActivityType.email:
                        contact_email = CrmContactEmail(
                            contact_id=contact.id,
                            tenant_id=tenant_id,
                            lead_id=lead_id,
                            subject=act.subject,
                            body=act.body or "",
                            direction=act.direction or "outbound",
                            created_by=act.created_by,
                            created_at=act.completed_at or act.created_at
                        )
                        if use_transaction:
                            await contact_email.insert(session=session)
                        else:
                            await contact_email.insert()
                        copied_emails_count += 1
            
            # Step 13: Create Timeline Entries
            
            # Timeline entry for Lead
            lead_timeline_event = {
                "id": str(uuid4()),
                "timestamp": datetime.utcnow().isoformat(),
                "user_id": str(user_id),
                "action": "lead_converted_to_contact",
                "description": f"Lead converted to Contact: {contact.full_name}",
                "contact_id": str(contact.id)
            }
            if not lead.audit_logs:
                lead.audit_logs = []
            lead.audit_logs.append(lead_timeline_event)
            if use_transaction:
                await lead.save(session=session)
            else:
                await lead.save()
            
            # Timeline entry for Contact
            contact_timeline = CrmTimeline(
                contact_id=contact.id,
                activity_type="contact_created",
                description=f"Contact created from Lead conversion by {user_id}",
                performed_by=user_id,
                metadata={
                    "lead_id": str(lead_id),
                    "conversion_date": datetime.utcnow().isoformat(),
                    "copied_notes": copy_notes,
                    "copied_activities": copy_activities,
                    "copied_tasks": copy_tasks,
                    "activities_count": copied_activities_count,
                    "tasks_count": copied_tasks_count,
                    "calls_count": copied_calls_count,
                    "meetings_count": copied_meetings_count,
                    "emails_count": copied_emails_count
                }
            )
            if use_transaction:
                await contact_timeline.insert(session=session)
            else:
                await contact_timeline.insert()
            
            # Step 14: Log Audit Trail
            await CrmService.log_lead_audit_and_activity(
                lead=lead,
                action="converted_to_contact",
                details=f"Lead converted to Contact. Contact ID: {str(contact.id)}. "
                       f"Copied: {copied_activities_count} activities, {copied_tasks_count} tasks",
                user_id=user_id,
                activity_subject="Lead Converted to Contact",
                activity_body=f"Lead has been successfully converted to a Contact record.\n\n"
                              f"Contact Name: {contact.full_name}\n"
                              f"Contact Email: {contact.email}\n"
                              f"Contact ID: {str(contact.id)}\n\n"
                              f"Activities Copied: {copied_activities_count}\n"
                              f"Tasks Copied: {copied_tasks_count}",
                activity_type=ActivityType.note
            )
            
            # Commit Database Transaction
            if use_transaction:
                await session.commit_transaction()
                await session.end_session()
            
            # Step 15: Return Success Response
            return {
                "success": True,
                "lead_id": str(lead_id),
                "contact_id": str(contact.id),
                "message": "Lead successfully converted to Contact",
                "contact": {
                    "id": str(contact.id),
                    "name": contact.full_name,
                    "email": contact.email,
                    "phone": contact.phone,
                    "company": contact.company_name,
                    "owner_id": str(contact.owner_id) if contact.owner_id else None
                },
                "summary": {
                    "activities_copied": copied_activities_count,
                    "tasks_copied": copied_tasks_count,
                    "notes_copied": len(contact.notes_list) if contact.notes_list else 0,
                    "documents_copied": len(contact.documents) if contact.documents else 0,
                    "calls_copied": copied_calls_count,
                    "meetings_copied": copied_meetings_count,
                    "emails_copied": copied_emails_count
                }
            }
            
        except Exception as e:
            # Rollback if any error occurs
            if use_transaction and session:
                await session.abort_transaction()
                await session.end_session()
            logger.error(f"Error converting lead to contact: {str(e)}", exc_info=True)
            raise ValueError(f"Failed to convert lead to contact: {str(e)}")

    @staticmethod
    async def check_lead_conversion_eligibility(lead_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """
        Check if a Lead can be converted to a Contact.
        Returns eligibility status and any blocking issues.
        """
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        
        issues = []
        can_convert = True
        
        # Check if already converted
        if lead.is_converted:
            issues.append({
                "type": "already_converted",
                "message": "Lead is already converted to a Contact",
                "contact_id": str(lead.converted_contact_id) if lead.converted_contact_id else None
            })
            can_convert = False
        
        # Check Lead Status
        allowed_statuses = [LeadStatus.qualified, LeadStatus.won, LeadStatus.negotiation]
        if lead.status not in allowed_statuses and not lead.is_converted:
            issues.append({
                "type": "invalid_status",
                "message": f"Lead must be in 'Qualified', 'Won', or 'Negotiation' status. Current: {lead.status.value}",
                "current_status": lead.status.value,
                "allowed_statuses": [s.value for s in allowed_statuses]
            })
            can_convert = False
        
        # Check for duplicate Contact
        from Models.crm_contacts import CrmContact
        existing_contact = None
        
        if lead.email:
            existing_contact = await CrmContact.find_one(
                CrmContact.tenant_id == tenant_id,
                CrmContact.email == lead.email,
                CrmContact.is_deleted == False
            )
        
        if not existing_contact and lead.phone:
            existing_contact = await CrmContact.find_one(
                CrmContact.tenant_id == tenant_id,
                CrmContact.phone == lead.phone,
                CrmContact.is_deleted == False
            )
        
        if existing_contact:
            issues.append({
                "type": "duplicate_contact",
                "message": "A Contact with this email or phone already exists",
                "contact_id": str(existing_contact.id),
                "contact_name": f"{existing_contact.first_name} {existing_contact.last_name or ''}".strip(),
                "contact_email": existing_contact.email,
                "contact_phone": existing_contact.phone
            })
            can_convert = False
        
        return {
            "can_convert": can_convert,
            "lead_id": str(lead_id),
            "lead_name": f"{lead.first_name} {lead.last_name or ''}".strip(),
            "lead_status": lead.status.value,
            "is_converted": lead.is_converted,
            "issues": issues,
            "message": "Lead can be converted" if can_convert else "Lead cannot be converted"
        }
    
    @staticmethod
    async def archive_lead(lead_id: UUID, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        lead.status = LeadStatus.dormant
        lead.updated_at = datetime.utcnow()
        await lead.save()
        await CrmService.log_lead_audit_and_activity(
            lead=lead, action="archived",
            details="Lead archived (set to dormant)",
            user_id=user_id,
            activity_subject="Lead Archived",
            activity_body="This lead has been archived.",
            activity_type=ActivityType.note
        )
        return {"message": "Lead archived", "lead_id": str(lead.id)}

    @staticmethod
    async def get_lead_audit_logs(lead_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        lead = await CrmLead.find_one(CrmLead.id == lead_id, CrmLead.tenant_id == tenant_id)
        if not lead:
            raise ValueError("Lead not found")
        return lead.audit_logs or []

    @staticmethod
    async def get_demo_calendar(tenant_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all leads with status == demo_scheduled AND demo_date IS NOT NULL.
        Falls back to nested demos[] array for backward compatibility with existing data.
        Returns calendar events sorted by demo_date ascending.
        """
        # Strategy 1: Get leads where flat demo_date field exists and is not null
        from pymongo import DESCENDING
        leads_with_demo_date = await CrmLead.find(
            CrmLead.tenant_id == tenant_id,
            CrmLead.status == "demo_scheduled",
            CrmLead.demo_date != None
        ).sort(+CrmLead.demo_date).to_list()
        
        # Strategy 2: Also get leads where status == demo_scheduled but flat demo_date field is missing
        # (existing data created before schema update that doesn't have demo_date field at all)
        from pymongo import ASCENDING
        missing_query = {
            "tenant_id": tenant_id,
            "status": "demo_scheduled",
            "$or": [
                {"demo_date": {"$exists": False}},
                {"demo_date": None}
            ]
        }
        leads_missing_demo_date = await CrmLead.find(missing_query).to_list()
        
        # Merge both lists, deduplicate by id
        seen_ids = set()
        all_leads = []
        for lead in leads_with_demo_date + leads_missing_demo_date:
            if lead.id not in seen_ids:
                seen_ids.add(lead.id)
                all_leads.append(lead)
        
        # For leads missing flat demo_date, try to extract from nested demos[] array
        for lead in all_leads:
            if lead.demo_date is None and lead.demos and len(lead.demos) > 0:
                # Try to get the earliest scheduled demo time
                sorted_demos = sorted(lead.demos, key=lambda d: d.get("scheduled_time", ""))
                latest_demo = sorted_demos[-1]
                st = latest_demo.get("scheduled_time")
                if st:
                    try:
                        lead.demo_date = datetime.fromisoformat(st.replace("Z", "+00:00")) if isinstance(st, str) else st
                    except:
                        pass
            
            # If still no date, use current time as fallback
            if lead.demo_date is None:
                lead.demo_date = datetime.utcnow()
        
        # Sort by demo_date ascending
        all_leads.sort(key=lambda l: l.demo_date or datetime.min)
        
        events = []
        for lead in all_leads:
            agent_name = None
            if lead.assigned_to:
                agent = await User.find_one(User.id == lead.assigned_to)
                if agent:
                    agent_name = f"{agent.first_name} {agent.last_name}"
            
            events.append({
                "id": str(lead.id),
                "title": f"Demo - {lead.company_name}",
                "company_name": lead.company_name,
                "contact_name": f"{lead.first_name} {lead.last_name or ''}".strip(),
                "email": lead.email,
                "phone": lead.phone,
                "demo_date": lead.demo_date.isoformat() if lead.demo_date else None,
                "demo_duration": lead.demo_duration or 30,
                "meeting_link": lead.demo_meeting_link or "",
                "assigned_to": agent_name,
                "assigned_to_id": str(lead.assigned_to) if lead.assigned_to else None,
                "status": lead.status.value if hasattr(lead.status, 'value') else lead.status,
                "priority": lead.priority.value if lead.priority else None,
                "demo_focus_areas": lead.demo_focus_areas or [],
                "lead_id": str(lead.id)
            })
        
        return events

    @staticmethod
    async def get_all_meetings(tenant_id: UUID) -> List[Dict[str, Any]]:
        """
        Get all meetings for leads and deals.
        - Lead meetings: from CrmActivity where activity_type == ActivityType.meeting
        - Deal meetings: from CrmDealMeeting
        """
        from Models.crm_deal_activities import CrmDealMeeting
        import re

        meetings_list = []

        # 1. Lead Meetings
        lead_activities = await CrmActivity.find(
            CrmActivity.tenant_id == tenant_id,
            CrmActivity.activity_type == ActivityType.meeting
        ).to_list()

        for act in lead_activities:
            company_name = "Unknown"
            contact_name = "N/A"
            if act.lead_id:
                lead = await CrmLead.find_one(CrmLead.id == act.lead_id)
                if lead:
                    company_name = lead.company_name or "Unknown"
                    contact_name = f"{lead.first_name} {lead.last_name or ''}".strip()

            # Parse meeting link from body
            meeting_link = ""
            if act.body:
                match = re.search(r"Link:\s*([^\n]+)", act.body)
                if match:
                    meeting_link = match.group(1).strip()
                    if meeting_link == "TBD":
                        meeting_link = ""

            # Parse duration
            duration = 30
            if act.duration and act.duration.isdigit():
                duration = int(act.duration)

            meetings_list.append({
                "id": str(act.id),
                "name": company_name,
                "contact_name": contact_name,
                "demo_type": "Lead Meeting",
                "demo_date": act.scheduled_at.isoformat() if act.scheduled_at else act.created_at.isoformat(),
                "demo_duration": duration,
                "demo_meeting_link": meeting_link,
                "demo_outcome": act.outcome or "scheduled"
            })

        # 2. Deal Meetings
        deal_meetings = await CrmDealMeeting.find(
            CrmDealMeeting.tenant_id == tenant_id
        ).to_list()

        for dm in deal_meetings:
            company_name = "Unknown"
            contact_name = "N/A"
            if dm.deal_id:
                deal = await CrmDeal.find_one(CrmDeal.id == dm.deal_id)
                if deal:
                    company_name = deal.deal_name or "Unknown"
                    # If deal has a contact, we can try to resolve contact_name
                    if deal.contact_id:
                        from Models.crm_contacts import CrmContact
                        contact = await CrmContact.find_one(CrmContact.id == deal.contact_id)
                        if contact:
                            contact_name = f"{contact.first_name} {contact.last_name or ''}".strip()
                    elif deal.lead_id:
                        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
                        if lead:
                            contact_name = f"{lead.first_name} {lead.last_name or ''}".strip()

            duration = 30
            if dm.start_time and dm.end_time:
                duration = int((dm.end_time - dm.start_time).total_seconds() // 60)

            meetings_list.append({
                "id": str(dm.id),
                "name": company_name,
                "contact_name": contact_name,
                "demo_type": "Deal Meeting",
                "demo_date": dm.start_time.isoformat() if dm.start_time else dm.created_at.isoformat(),
                "demo_duration": duration,
                "demo_meeting_link": dm.meeting_link or "",
                "demo_outcome": dm.outcome or (dm.status.value if hasattr(dm.status, 'value') else str(dm.status))
            })

        # Sort all meetings by date descending
        meetings_list.sort(key=lambda x: x["demo_date"], reverse=True)
        return meetings_list


