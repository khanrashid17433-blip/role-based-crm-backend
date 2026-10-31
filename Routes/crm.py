from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from typing import Dict, Any, Optional
from uuid import UUID
import logging
import os
import shutil

from Schema.crm import (
    WebFormLeadRequest, LeadManualCreateRequest, LeadQualifyRequest,
    DemoScheduleRequest, DemoCompleteRequest, ProposalCreateRequest,
    DealWonRequest, DealLostRequest, LeadUpdateRequest,
    LeadAssignRequest, LeadEmailRequest, LeadActivityCreateRequest,
    LeadNoteCreateRequest, LeadDemoScheduleRequest, LeadProposalCreateRequest,
    LeadDocumentUploadRequest, FollowUpCreateRequest, CallLogRequest,
    MeetingScheduleRequest, TaskCreateRequest, LeadStatusChangeRequest,
    LeadArchiveRequest, LeadImportRequest
)
from Services.crm_service import CrmService
from Utility.auth_helpers import get_current_user, verify_platform_admin
from Models.crm import LeadStatus

logger = logging.getLogger(__name__)

# Directory to save CRM lead attachments (same pattern as task attachments)
CRM_ATTACHMENTS_DIR = "static/crm_attachments"
os.makedirs(CRM_ATTACHMENTS_DIR, exist_ok=True)

router = APIRouter(prefix="/api/crm", tags=["CRM"])

# ── Lead CRUD ──

@router.get("/leads", summary="List Leads")
async def list_leads(
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user = Depends(verify_platform_admin)
):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        leads = await CrmService.get_leads(tenant_id, status=status, source=source, search=search)
        return leads
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/sales-agents", summary="List Sales Agents")
async def list_sales_agents(current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        agents = await CrmService.get_sales_agents(tenant_id)
        return [{"id": str(a.id), "name": f"{a.first_name} {a.last_name}", "email": a.email} for a in agents]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/leads/assign", summary="Assign Leads")
async def assign_leads(data: LeadAssignRequest, current_user = Depends(verify_platform_admin)):
    try:
        if not data.lead_ids:
            raise HTTPException(status_code=400, detail="No lead IDs provided")
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        leads = await CrmService.assign_leads(data.lead_ids, data.assigned_to, tenant_id)
        return {"message": "Leads assigned successfully", "count": len(leads)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads/{lead_id}", summary="Get Lead Details")
async def get_lead_details(lead_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.get_lead_by_id(UUID(lead_id), tenant_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        return lead
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid lead ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/leads/{lead_id}", summary="Update Lead Details")
async def update_lead_details(lead_id: str, data: LeadUpdateRequest, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        user_id = UUID(current_user.get('sub'))
        lead = await CrmService.update_lead(UUID(lead_id), data, tenant_id, user_id=user_id)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/leads/{lead_id}", summary="Delete Lead")
async def delete_lead(lead_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        await CrmService.delete_lead(UUID(lead_id), tenant_id)
        return {"message": "Lead deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/web-form", summary="Capture Lead from Web Form", status_code=status.HTTP_201_CREATED)
async def capture_web_lead(data: WebFormLeadRequest):
    try:
        lead = await CrmService.capture_web_lead(data)
        return {"message": "Lead captured successfully", "lead_id": str(lead.id)}
    except Exception as e:
        logger.error(f"Failed to capture web lead: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/leads", summary="Manual Lead Entry", status_code=status.HTTP_201_CREATED)
async def create_manual_lead(data: LeadManualCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.create_manual_lead(data, user_id, tenant_id)
        return {"message": "Lead created successfully", "lead_id": str(lead.id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/import", summary="Bulk Import Leads from CSV", status_code=status.HTTP_201_CREATED)
async def import_leads_bulk(data: LeadImportRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.import_leads_bulk(data.leads, user_id, tenant_id)
        return {"message": f"{result['created']} leads imported successfully", "created": result['created'], "failed": result['failed'], "errors": result['errors']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/leads/{lead_id}/qualify", summary="Qualify Lead (BANT)")
async def qualify_lead(lead_id: str, data: LeadQualifyRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.qualify_lead(UUID(lead_id), data, user_id, tenant_id)
        return {"message": "Lead qualification processed", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Lead Status Management ──

@router.patch("/leads/{lead_id}/status", summary="Change Lead Status")
async def change_lead_status(lead_id: str, data: LeadStatusChangeRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.change_lead_status(UUID(lead_id), data.status, data.reason, user_id, tenant_id)
        return {"message": "Lead status updated", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Deals Management ──

@router.post("/deals/{deal_id}/demo/schedule", summary="Schedule Demo")
async def schedule_demo(deal_id: str, data: DemoScheduleRequest, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        opp = await CrmService.schedule_demo(UUID(deal_id), data, tenant_id)
        return {"message": "Demo scheduled", "deal_id": str(opp.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deals/{deal_id}/demo/complete", summary="Complete Demo")
async def complete_demo(deal_id: str, data: DemoCompleteRequest, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        opp = await CrmService.complete_demo(UUID(deal_id), data, tenant_id)
        return {"message": "Demo completed", "deal_id": str(opp.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deals/{deal_id}/proposals", summary="Create Proposal")
async def create_proposal(deal_id: str, data: ProposalCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        proposal = await CrmService.create_proposal(UUID(deal_id), data, tenant_id)
        return {"message": "Proposal created", "proposal_id": str(proposal.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deals/{deal_id}/won", summary="Mark Deal as Won")
async def mark_opportunity_won(deal_id: str, data: DealWonRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.mark_won(UUID(deal_id), data, user_id, tenant_id)
        return {"message": "Deal won", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/deals/{deal_id}/lost", summary="Mark Deal as Lost")
async def mark_opportunity_lost(deal_id: str, data: DealLostRequest, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        opp = await CrmService.mark_lost(UUID(deal_id), data, tenant_id)
        return {"message": "Deal lost", "deal_id": str(opp.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/leads/{lead_id}/email", summary="Send Email to Lead")
async def send_lead_email(lead_id: str, data: LeadEmailRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.send_lead_email(UUID(lead_id), data.subject, data.message, data.template, user_id, tenant_id)
        return {"message": "Email sent successfully", "activity_id": str(result.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads/{lead_id}/activities", summary="Get Activities for Lead")
async def get_lead_activities(lead_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        activities = await CrmService.get_lead_activities(UUID(lead_id), tenant_id)
        return activities
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/activities", summary="Log Activity for Lead")
async def log_lead_activity(lead_id: str, data: LeadActivityCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        activity = await CrmService.log_lead_activity(UUID(lead_id), data, user_id, tenant_id)
        return {"message": "Activity logged successfully", "activity_id": str(activity.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clients", summary="Create Client from Opportunity")
async def create_client(data: Dict[str, Any], current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        client = await CrmService.create_client(data, tenant_id)
        return {"message": "Client created successfully", "client_id": str(client.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clients", summary="Get All Clients")
async def get_clients(current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        clients = await CrmService.get_clients(tenant_id)
        return clients
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"{repr(e)} | Trace: {err_msg}")

@router.get("/clients/{client_id}", summary="Get Client Details")
async def get_client_details(client_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        client = await CrmService.get_client_by_id(UUID(client_id), tenant_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid client ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/clients/{client_id}", summary="Update Client Details")
async def update_client_details(client_id: str, data: Dict[str, Any], current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        client = await CrmService.update_client(UUID(client_id), data, tenant_id)
        return client
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deals", summary="Get Deals")
async def get_deals(
    grouped: bool = Query(False),
    stage: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: Optional[str] = Query("created_at"),
    sort_order: Optional[str] = Query("desc"),
    page: int = Query(1),
    limit: int = Query(10),
    current_user = Depends(verify_platform_admin)
):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        deals = await CrmService.get_deals(
            tenant_id=tenant_id, grouped=grouped, stage=stage, priority=priority,
            search=search, sort_by=sort_by, sort_order=sort_order, page=page, limit=limit
        )
        return deals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deals/{deal_id}", summary="Get Deal Details")
async def get_deal_details(deal_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        from Models.crm import CrmDeal, CrmLead
        from Models.tenant_user import User
        deal = await CrmDeal.find_one(CrmDeal.id == UUID(deal_id), CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise HTTPException(status_code=404, detail="Deal not found")
        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
        agent_name = None
        if deal.assigned_to:
            agent = await User.find_one(User.id == deal.assigned_to)
            if agent:
                agent_name = f"{agent.first_name} {agent.last_name}"
        return {
            "id": str(deal.id), "name": deal.name, "company": lead.company_name if lead else deal.name,
            "contact": f"{lead.first_name} {lead.last_name}" if lead else "",
            "email": lead.email if lead else "", "phone": lead.phone if lead else "",
            "location": lead.region if lead else "", "value": deal.deal_value,
            "currency": deal.currency, "priority": deal.priority or "medium",
            "source": lead.source.value if lead else deal.source, "assignedTo": agent_name,
            "assigned_to": str(deal.assigned_to) if deal.assigned_to else None,
            "createdDate": deal.created_at.strftime("%Y-%m-%d") if deal.created_at else "",
            "expectedCloseDate": deal.close_date.strftime("%Y-%m-%d") if deal.close_date else "",
            "daysInStage": deal.days_in_stage, "stage": deal.stage.value,
            "probability_pct": deal.probability_pct,
            "contract": {
                "status": deal.contract_status, "sentDate": deal.contract_sent_date.strftime("%Y-%m-%d") if deal.contract_sent_date else None,
                "signedDate": deal.contract_signed_date.strftime("%Y-%m-%d") if deal.contract_signed_date else None,
                "file": deal.contract_file, "version": deal.contract_version,
            },
            "pricing": {"basePrice": deal.base_price, "discountPct": deal.discount_pct, "finalPrice": deal.final_price, "breakdown": deal.pricing_breakdown},
            "paymentTerms": {"type": deal.payment_type, "schedule": deal.payment_schedule},
            "legal": {"reviewStatus": deal.legal_review_status, "reviewer": deal.legal_reviewer, "notes": deal.legal_notes, "reviewedDate": deal.legal_reviewed_date.strftime("%Y-%m-%d") if deal.legal_reviewed_date else None},
            "approval": {"status": deal.approval_status, "approvers": deal.approvers}
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deal ID format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deals", summary="Create New Deal", status_code=status.HTTP_201_CREATED)
async def create_deal(data: Dict[str, Any], current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        deal = await CrmService.create_deal(data, user_id, tenant_id)
        return {"message": "Deal created successfully", "deal_id": str(deal.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/deals/{deal_id}", summary="Update Deal")
async def update_deal(deal_id: str, data: Dict[str, Any], current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        deal = await CrmService.update_deal(UUID(deal_id), data, tenant_id)
        return {"message": "Deal updated successfully", "deal_id": str(deal.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/deals/{deal_id}/stage", summary="Move Deal to Different Stage")
async def move_deal_stage(deal_id: str, stage: str = Query(...), current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        deal = await CrmService.move_deal_stage(UUID(deal_id), stage, user_id, tenant_id)
        return {"message": "Deal stage updated successfully", "deal_id": str(deal.id), "new_stage": deal.stage.value, "probability_pct": deal.probability_pct}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deals/{deal_id}/convert", summary="Convert Deal to Client")
async def convert_deal_to_client(deal_id: str, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.convert_deal_to_client(UUID(deal_id), user_id, tenant_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deals/{deal_id}/timeline", summary="Get Deal Timeline")
async def get_deal_timeline(deal_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        timeline = await CrmService.get_deal_timeline(UUID(deal_id), tenant_id)
        return timeline
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/deals/{deal_id}", summary="Delete Deal")
async def delete_deal(deal_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        await CrmService.delete_deal(UUID(deal_id), tenant_id)
        return {"message": "Deal deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deals/{deal_id}/activities", summary="Add Activity to Deal", status_code=status.HTTP_201_CREATED)
async def add_deal_activity(deal_id: str, data: Dict[str, Any], current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        activity = await CrmService.add_deal_activity(UUID(deal_id), data, user_id, tenant_id)
        return {"message": "Activity added successfully", "activity_id": str(activity.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads/{lead_id}/timeline", summary="Get Lead Timeline")
async def get_lead_timeline(lead_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        timeline = await CrmService.get_lead_timeline(UUID(lead_id), tenant_id)
        return timeline
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/notes", summary="Add Note to Lead")
async def add_lead_note(lead_id: str, data: LeadNoteCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.add_lead_note(UUID(lead_id), data.text, data.is_pinned, user_id, tenant_id, mentions=data.mentions, attachments=data.attachments)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/leads/{lead_id}/notes/{note_id}/pin", summary="Toggle Note Pin")
async def toggle_lead_note_pin(lead_id: str, note_id: str, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.toggle_lead_note_pin(UUID(lead_id), note_id, user_id, tenant_id)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/leads/{lead_id}/notes/{note_id}", summary="Edit Lead Note")
async def edit_lead_note(lead_id: str, note_id: str, data: LeadNoteCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.edit_lead_note(UUID(lead_id), note_id, data.text, data.is_pinned, user_id, tenant_id, mentions=data.mentions, attachments=data.attachments)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/leads/{lead_id}/notes/{note_id}", summary="Delete Lead Note")
async def delete_lead_note(lead_id: str, note_id: str, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.delete_lead_note(UUID(lead_id), note_id, user_id, tenant_id)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/demos", summary="Schedule Lead Demo")
async def schedule_lead_demo(lead_id: str, data: LeadDemoScheduleRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.schedule_lead_demo(UUID(lead_id), data.model_dump(), user_id, tenant_id)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/proposals", summary="Create Lead Proposal")
async def create_lead_proposal(lead_id: str, data: LeadProposalCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.generate_lead_proposal(UUID(lead_id), data.model_dump(), user_id, tenant_id)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/documents", summary="Upload Lead Document")
async def upload_lead_document(lead_id: str, data: LeadDocumentUploadRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.upload_lead_document(UUID(lead_id), data.name, data.file_size, user_id, tenant_id, file_type=data.file_type, file_url=data.file_url)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/leads/{lead_id}/documents/{doc_id}", summary="Delete Lead Document")
async def delete_lead_document(lead_id: str, doc_id: str, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        lead = await CrmService.delete_lead_document(UUID(lead_id), doc_id, user_id, tenant_id)
        return lead
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/attachments/upload", summary="Upload Lead Attachment File")
async def upload_lead_attachment_file(lead_id: str, file: UploadFile = File(...), current_user = Depends(verify_platform_admin)):
    """Real multipart file upload — saves file to disk, stores metadata in DB on the lead"""
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))

        lead_dir = os.path.join(CRM_ATTACHMENTS_DIR, lead_id)
        os.makedirs(lead_dir, exist_ok=True)

        safe_filename = file.filename.replace(" ", "_")
        file_path = os.path.join(lead_dir, safe_filename)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size_bytes = os.path.getsize(file_path)
        file_size_str = f"{round(file_size_bytes / 1024, 1)} KB" if file_size_bytes < 1024 * 1024 else f"{round(file_size_bytes / (1024 * 1024), 2)} MB"
        file_url = f"/static/crm_attachments/{lead_id}/{safe_filename}"

        await CrmService.upload_lead_document(
            UUID(lead_id), safe_filename, file_size_str, user_id, tenant_id,
            file_type=file.content_type or "application/octet-stream",
            file_url=file_url
        )
        return {
            "message": "File uploaded successfully",
            "file_url": file_url,
            "file_name": safe_filename,
            "file_size": file_size_str,
            "file_type": file.content_type
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── New Lead Operations ──

@router.post("/leads/{lead_id}/follow-ups", summary="Schedule Follow-up")
async def schedule_follow_up(lead_id: str, data: FollowUpCreateRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.schedule_follow_up(UUID(lead_id), data, user_id, tenant_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/calls", summary="Log Call")
async def log_call(lead_id: str, data: CallLogRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.log_call(UUID(lead_id), data, user_id, tenant_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/meetings", summary="Schedule Meeting")
async def schedule_meeting(lead_id: str, data: MeetingScheduleRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.schedule_meeting(UUID(lead_id), data, user_id, tenant_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/tasks", summary="Create Task (unified crm_tasks)")
async def create_lead_task(lead_id: str, data: TaskCreateRequest, current_user = Depends(verify_platform_admin)):
    """Create a task linked to this lead — stored in the unified crm_tasks collection"""
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        from Services.task_service import TaskService as CrmTaskService
        task_data = data.model_dump() if hasattr(data, 'model_dump') else data.dict()
        task_data['lead_id'] = lead_id  # always set the lead association
        task = await CrmTaskService.create_task(task_data, user_id, tenant_id)
        return {"message": "Task created successfully", "task_id": str(task.id), "lead_id": lead_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads/{lead_id}/tasks", summary="List Lead Tasks")
async def list_lead_tasks(lead_id: str, current_user = Depends(verify_platform_admin)):
    """Get all tasks for a specific lead from the unified crm_tasks collection"""
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        from Services.task_service import TaskService as CrmTaskService
        from Routes.crm_tasks import serialize_task, resolve_associated_record, resolve_associated_id
        tasks, total = await CrmTaskService.get_tasks(tenant_id, {"lead_id": lead_id}, page=1, limit=100)
        serialized = []
        for t in tasks:
            d = await serialize_task(t)
            serialized.append(d)
        return {"tasks": serialized, "total": total}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# Shared conversion handler with permissions check
async def execute_lead_conversion(
    lead_id: str,
    copy_notes: bool,
    copy_activities: bool,
    copy_tasks: bool,
    copy_meetings: bool,
    copy_calls: bool,
    copy_emails: bool,
    current_user
):
    try:
        user_role = current_user.get("role", "")
        user_type = current_user.get("user_type", "")
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        
        # Enforce business rules permission checks:
        # Only Sales Manager (manager), Admin (admin/super_admin/tenant_admin), or Authorized Sales Rep (owner of the lead) can convert.
        is_admin = (
            user_role in ["admin", "tenant_admin", "super_admin", "platform_admin"] or
            user_type in ["platform_admin", "tenant_admin", "admin"]
        )
        is_manager = user_role in ["manager", "sales_manager"]
        is_sales = user_role in ["sales", "sales_executive"]
        
        from Models.crm import CrmLead
        lead = await CrmLead.find_one(CrmLead.id == UUID(lead_id), CrmLead.tenant_id == tenant_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
            
        if not (is_admin or is_manager or (is_sales and lead.assigned_to == user_id)):
            raise HTTPException(
                status_code=403, 
                detail="You do not have permission to convert this lead. Only Admins, Sales Managers, or the Lead Owner can perform this action."
            )
            
        result = await CrmService.convert_lead_to_contact(
            UUID(lead_id), user_id, tenant_id,
            copy_notes=copy_notes,
            copy_activities=copy_activities,
            copy_tasks=copy_tasks,
            copy_meetings=copy_meetings,
            copy_calls=copy_calls,
            copy_emails=copy_emails
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/leads/{lead_id}/convert", summary="Convert Lead to Contact (Standard)")
async def convert_lead_standard(
    lead_id: str,
    copy_notes: bool = Query(True),
    copy_activities: bool = Query(True),
    copy_tasks: bool = Query(True),
    copy_meetings: bool = Query(True),
    copy_calls: bool = Query(True),
    copy_emails: bool = Query(True),
    current_user = Depends(verify_platform_admin)
):
    return await execute_lead_conversion(
        lead_id, copy_notes, copy_activities, copy_tasks, copy_meetings, copy_calls, copy_emails, current_user
    )

@router.post("/leads/{lead_id}/convert-to-contact", summary="Convert Lead to Contact (Compatibility)")
async def convert_lead_compat(
    lead_id: str,
    copy_notes: bool = Query(True),
    copy_activities: bool = Query(True),
    copy_tasks: bool = Query(True),
    copy_meetings: bool = Query(True),
    copy_calls: bool = Query(True),
    copy_emails: bool = Query(True),
    current_user = Depends(verify_platform_admin)
):
    return await execute_lead_conversion(
        lead_id, copy_notes, copy_activities, copy_tasks, copy_meetings, copy_calls, copy_emails, current_user
    )

@router.get("/leads/{lead_id}/can-convert", summary="Check if Lead can be converted")
async def can_convert_lead(lead_id: str, current_user = Depends(verify_platform_admin)):
    """
    Check if a Lead can be converted to a Contact.
    Returns validation status and any blocking issues.
    """
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        user_role = current_user.get("role", "")
        user_type = current_user.get("user_type", "")
        user_id = UUID(current_user.get('sub'))
        
        result = await CrmService.check_lead_conversion_eligibility(UUID(lead_id), tenant_id)
        
        # Add permission validation issue
        is_admin = (
            user_role in ["admin", "tenant_admin", "super_admin", "platform_admin"] or
            user_type in ["platform_admin", "tenant_admin", "admin"]
        )
        is_manager = user_role in ["manager", "sales_manager"]
        is_sales = user_role in ["sales", "sales_executive"]
        
        from Models.crm import CrmLead
        lead = await CrmLead.find_one(CrmLead.id == UUID(lead_id), CrmLead.tenant_id == tenant_id)
        if lead:
            has_permission = is_admin or is_manager or (is_sales and lead.assigned_to == user_id)
            if not has_permission:
                result["can_convert"] = False
                result["issues"].append({
                    "type": "permission_denied",
                    "message": "Only Admins, Sales Managers, or the Lead Owner can convert this lead."
                })
                result["message"] = "Lead cannot be converted due to permissions"
                
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/leads/{lead_id}/archive", summary="Archive Lead")
async def archive_lead(lead_id: str, data: LeadArchiveRequest, current_user = Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await CrmService.archive_lead(UUID(lead_id), user_id, tenant_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/leads/{lead_id}/audit-logs", summary="Get Lead Audit Logs")
async def get_lead_audit_logs(lead_id: str, current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        logs = await CrmService.get_lead_audit_logs(UUID(lead_id), tenant_id)
        return logs
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── Demo Calendar ──

@router.get("/demo/calendar", summary="Get Demo Calendar Events")
async def get_demo_calendar(current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        events = await CrmService.get_demo_calendar(tenant_id)
        return events
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meetings", summary="Get All CRM Meetings")
async def get_all_meetings(current_user = Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        meetings = await CrmService.get_all_meetings(tenant_id)
        return meetings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
