from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
from uuid import UUID, uuid4

from Models.crm import (
    CrmDeal, CrmLead, CrmActivity, CrmProposal, CrmDealAuditLog,
    DealStage, ActivityType
)
from Models.crm_deal_activities import (
    CrmDealNote, CrmDealCall, CrmDealMeeting,
    CrmDealDocument, CrmDealActivityFeed,
    DealCallType, DealMeetingStatus
)
from Models.crm_task import CrmTask
from Models.tenant_user import User

logger = logging.getLogger(__name__)


class DealWorkspaceService:

    STAGE_PROBABILITY_MAP = {
        "new": 10,
        "qualified": 20,
        "demo_scheduled": 40,
        "demo_completed": 60,
        "proposal_sent": 75,
        "negotiation": 90,
        "won": 100,
        "lost": 0
    }

    PIPELINE_STAGES = ["new", "qualified", "demo_scheduled", "demo_completed", "proposal_sent", "negotiation", "won", "lost"]

    # ── Core Deal Data ───────────────────────────────────────────────────

    @staticmethod
    async def get_deal_workspace(deal_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Get complete deal workspace data"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
        
        owner_name = None
        if deal.assigned_to:
            owner = await User.find_one(User.id == deal.assigned_to)
            if owner:
                owner_name = f"{owner.first_name} {owner.last_name}"

        # Get proposal
        proposal = await CrmProposal.find_one(CrmProposal.deal_id == deal.id)
        
        # Get activity counts
        notes_count = await CrmDealNote.find(CrmDealNote.deal_id == deal.id).count()
        calls_count = await CrmDealCall.find(CrmDealCall.deal_id == deal.id).count()
        meetings_count = await CrmDealMeeting.find(CrmDealMeeting.deal_id == deal.id).count()
        tasks_count = await CrmTask.find(CrmTask.deal_id == deal.id, CrmTask.tenant_id == tenant_id, CrmTask.archived_at == None).count()
        docs_count = await CrmDealDocument.find(CrmDealDocument.deal_id == deal.id).count()

        return {
            "id": str(deal.id),
            "name": deal.name,
            "lead_id": str(deal.lead_id) if deal.lead_id else None,
            "company_name": lead.company_name if lead else None,
            "contact_name": f"{lead.first_name} {lead.last_name}".strip() if lead else None,
            "contact_email": lead.email if lead else None,
            "contact_phone": lead.phone if lead else None,
            "contact_designation": lead.job_title if lead else None,
            "deal_value": deal.deal_value,
            "currency": deal.currency,
            "pipeline": "Sales Pipeline",
            "stage": deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage),
            "probability_pct": deal.probability_pct,
            "priority": deal.priority,
            "lead_source": lead.source.value if lead and hasattr(lead.source, 'value') else str(lead.source) if lead and lead.source else None,
            "owner_id": str(deal.assigned_to) if deal.assigned_to else None,
            "owner_name": owner_name,
            "close_date": deal.close_date.isoformat() if deal.close_date else None,
            "created_at": deal.created_at.isoformat(),
            "updated_at": deal.updated_at.isoformat(),
            "last_activity": deal.updated_at.isoformat(),
            "status": "active" if deal.stage not in [DealStage.won, DealStage.lost] else deal.stage.value,
            "tags": [],
            "plan_id": str(deal.plan_id) if deal.plan_id else None,
            "employees_count": deal.headcount_estimate,
            "contract_duration": deal.contract_status,
            "discount_pct": deal.discount_pct,
            "mrr": deal.base_price if deal.base_price else 0,
            "arr": deal.base_price * 12 if deal.base_price else 0,
            "forecast_category": deal.stage.value,
            "next_follow_up": None,
            "won_reason": deal.won_reason,
            "lost_reason": deal.lost_reason,
            "custom_fields": {},
            "proposal": {
                "id": str(proposal.id) if proposal else None,
                "status": proposal.status if proposal else None,
                "value": proposal.value if proposal else None,
                "sent_at": proposal.sent_at.isoformat() if proposal and proposal.sent_at else None,
                "viewed_at": proposal.viewed_at.isoformat() if proposal and proposal.viewed_at else None,
                "signed_at": proposal.signed_at.isoformat() if proposal and proposal.signed_at else None,
                "file_url": proposal.file_url if proposal else None,
            } if proposal else None,
            "activity_counts": {
                "notes": notes_count,
                "calls": calls_count,
                "meetings": meetings_count,
                "tasks": tasks_count,
                "documents": docs_count,
            }
        }

    # ── Pipeline Stage ───────────────────────────────────────────────────

    @staticmethod
    async def update_stage(deal_id: UUID, new_stage: str, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Update deal stage with auto probability"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        # Validate stage
        valid_stages = [s.value for s in DealStage]
        if new_stage not in valid_stages:
            raise ValueError(f"Invalid stage: {new_stage}. Valid stages: {valid_stages}")

        stage_enum = DealStage(new_stage)
        old_stage = deal.stage.value if hasattr(deal.stage, 'value') else str(deal.stage)
        
        # Map to probability
        probability = DealWorkspaceService.STAGE_PROBABILITY_MAP.get(new_stage, 10)
        deal.stage = stage_enum
        deal.probability_pct = probability
        deal.updated_at = datetime.utcnow()
        await deal.save()

        # Create activity feed
        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="stage_change",
            title=f"Stage changed to {new_stage}",
            description=f"Stage changed from {old_stage} to {new_stage} (Probability: {probability}%)",
            metadata={"old_stage": old_stage, "new_stage": new_stage, "probability": probability},
            created_by=user_id
        )
        await feed.insert()

        # Create audit log
        audit = CrmDealAuditLog(
            tenant_id=tenant_id,
            deal_id=deal.id,
            user_id=user_id,
            action="stage_change",
            details=f"Stage changed from {old_stage} to {new_stage}"
        )
        await audit.insert()

        # Update lead status
        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
        if lead:
            from Models.crm import LeadStatus
            status_map = {
                "new": LeadStatus.new,
                "qualified": LeadStatus.qualified,
                "demo_scheduled": LeadStatus.demo_scheduled,
                "demo_completed": LeadStatus.demo_done,
                "proposal_sent": LeadStatus.proposal_sent,
                "negotiation": LeadStatus.negotiation,
                "won": LeadStatus.won,
                "lost": LeadStatus.lost,
            }
            if new_stage in status_map:
                lead.status = status_map[new_stage]
                await lead.save()

        return {
            "id": str(deal.id),
            "stage": new_stage,
            "probability_pct": probability,
            "old_stage": old_stage
        }

    # ── Notes ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_notes(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        notes = await CrmDealNote.find(
            CrmDealNote.deal_id == deal_id,
            CrmDealNote.tenant_id == tenant_id
        ).sort(-CrmDealNote.created_at).to_list()
        
        result = []
        for n in notes:
            user = await User.find_one(User.id == n.created_by)
            result.append({
                "id": str(n.id),
                "note": n.note,
                "is_pinned": n.is_pinned,
                "created_by": str(n.created_by),
                "created_by_name": f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                "created_at": n.created_at.isoformat(),
            })
        return result

    @staticmethod
    async def add_note(deal_id: UUID, note_text: str, is_pinned: bool, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        note = CrmDealNote(
            deal_id=deal.id,
            tenant_id=tenant_id,
            note=note_text,
            is_pinned=is_pinned,
            created_by=user_id
        )
        await note.insert()

        # Create activity feed
        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="note",
            title="Note Added",
            description=note_text[:200],
            metadata={"note_id": str(note.id)},
            created_by=user_id
        )
        await feed.insert()

        return {"id": str(note.id), "note": note_text, "is_pinned": is_pinned}

    @staticmethod
    async def update_note(deal_id: UUID, note_id: UUID, data: Dict[str, Any], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Update an existing note"""
        note = await CrmDealNote.find_one(
            CrmDealNote.id == note_id,
            CrmDealNote.deal_id == deal_id,
            CrmDealNote.tenant_id == tenant_id
        )
        if not note:
            raise ValueError("Note not found")

        if "note" in data:
            note.note = data["note"]
        if "is_pinned" in data:
            note.is_pinned = data["is_pinned"]
        note.updated_at = datetime.utcnow()
        await note.save()

        return {"id": str(note.id), "note": note.note, "is_pinned": note.is_pinned}

    @staticmethod
    async def delete_note(deal_id: UUID, note_id: UUID, tenant_id: UUID) -> None:
        """Delete a note"""
        note = await CrmDealNote.find_one(
            CrmDealNote.id == note_id,
            CrmDealNote.deal_id == deal_id,
            CrmDealNote.tenant_id == tenant_id
        )
        if not note:
            raise ValueError("Note not found")
        await note.delete()

    @staticmethod
    async def toggle_note_pin(deal_id: UUID, note_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Toggle pin status of a note"""
        note = await CrmDealNote.find_one(
            CrmDealNote.id == note_id,
            CrmDealNote.deal_id == deal_id,
            CrmDealNote.tenant_id == tenant_id
        )
        if not note:
            raise ValueError("Note not found")
        note.is_pinned = not note.is_pinned
        note.updated_at = datetime.utcnow()
        await note.save()
        return {"id": str(note.id), "is_pinned": note.is_pinned}

    # ── Calls ────────────────────────────────────────────────────────────

    @staticmethod
    async def get_calls(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        calls = await CrmDealCall.find(
            CrmDealCall.deal_id == deal_id,
            CrmDealCall.tenant_id == tenant_id
        ).sort(-CrmDealCall.created_at).to_list()
        
        result = []
        for c in calls:
            user = await User.find_one(User.id == c.created_by)
            result.append({
                "id": str(c.id),
                "call_type": c.call_type.value if hasattr(c.call_type, 'value') else str(c.call_type),
                "duration": c.duration,
                "outcome": c.outcome,
                "notes": c.notes,
                "created_by": str(c.created_by),
                "created_by_name": f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                "created_at": c.created_at.isoformat(),
            })
        return result

    @staticmethod
    async def log_call(deal_id: UUID, call_type: str, duration: Optional[int], outcome: Optional[str], notes: Optional[str], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        try:
            ct = DealCallType(call_type)
        except ValueError:
            ct = DealCallType.outbound

        call = CrmDealCall(
            deal_id=deal.id,
            tenant_id=tenant_id,
            call_type=ct,
            duration=duration,
            outcome=outcome,
            notes=notes,
            created_by=user_id
        )
        await call.insert()

        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="call",
            title=f"Call Logged ({call_type})",
            description=notes or outcome or "No details",
            metadata={"call_id": str(call.id), "duration": duration, "outcome": outcome},
            created_by=user_id
        )
        await feed.insert()

        return {"id": str(call.id), "call_type": call_type, "duration": duration, "outcome": outcome}

    # ── Meetings ─────────────────────────────────────────────────────────

    @staticmethod
    async def get_meetings(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        meetings = await CrmDealMeeting.find(
            CrmDealMeeting.deal_id == deal_id,
            CrmDealMeeting.tenant_id == tenant_id
        ).sort(-CrmDealMeeting.start_time).to_list()

        result = []
        for m in meetings:
            user = await User.find_one(User.id == m.created_by)
            result.append({
                "id": str(m.id),
                "title": m.title,
                "agenda": m.agenda,
                "meeting_link": m.meeting_link,
                "start_time": m.start_time.isoformat(),
                "end_time": m.end_time.isoformat() if m.end_time else None,
                "status": m.status.value if hasattr(m.status, 'value') else str(m.status),
                "outcome": m.outcome,
                "created_by": str(m.created_by),
                "created_by_name": f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                "created_at": m.created_at.isoformat(),
            })
        return result

    @staticmethod
    async def schedule_meeting(deal_id: UUID, title: str, agenda: Optional[str], meeting_link: Optional[str], start_time: str, end_time: Optional[str], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        meeting = CrmDealMeeting(
            deal_id=deal.id,
            tenant_id=tenant_id,
            title=title,
            agenda=agenda,
            meeting_link=meeting_link,
            start_time=datetime.fromisoformat(start_time) if isinstance(start_time, str) else start_time,
            end_time=datetime.fromisoformat(end_time) if end_time and isinstance(end_time, str) else end_time,
            status=DealMeetingStatus.scheduled,
            created_by=user_id
        )
        await meeting.insert()

        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="meeting",
            title=f"Meeting Scheduled: {title}",
            description=agenda or "No agenda",
            metadata={"meeting_id": str(meeting.id), "start_time": start_time},
            created_by=user_id
        )
        await feed.insert()

        return {
            "id": str(meeting.id),
            "title": title,
            "start_time": meeting.start_time.isoformat(),
            "status": "scheduled"
        }

    @staticmethod
    async def update_meeting(deal_id: UUID, meeting_id: UUID, data: Dict[str, Any], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Update meeting details including status"""
        meeting = await CrmDealMeeting.find_one(
            CrmDealMeeting.id == meeting_id,
            CrmDealMeeting.deal_id == deal_id,
            CrmDealMeeting.tenant_id == tenant_id
        )
        if not meeting:
            raise ValueError("Meeting not found")

        # Update fields if provided
        if "status" in data:
            status_value = data["status"]
            # Handle both string and enum values
            if isinstance(status_value, str):
                meeting.status = DealMeetingStatus(status_value)
            else:
                meeting.status = status_value
        
        if "title" in data:
            meeting.title = data["title"]
        if "agenda" in data:
            meeting.agenda = data["agenda"]
        if "meeting_link" in data:
            meeting.meeting_link = data["meeting_link"]
        if "outcome" in data:
            meeting.outcome = data["outcome"]
        
        await meeting.save()

        # Log activity if status changed
        if "status" in data:
            feed = CrmDealActivityFeed(
                deal_id=deal_id,
                tenant_id=tenant_id,
                activity_type="meeting",
                title=f"Meeting {data['status']}: {meeting.title}",
                description=f"Meeting status changed to {data['status']}",
                metadata={"meeting_id": str(meeting.id)},
                created_by=user_id
            )
            await feed.insert()

        return {
            "id": str(meeting.id),
            "title": meeting.title,
            "status": meeting.status.value if hasattr(meeting.status, 'value') else str(meeting.status)
        }

    # ── Tasks (Centralized CRM Tasks) ────────────────────────────────────

    @staticmethod
    async def get_tasks(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        """Get tasks associated with a deal from the centralized CrmTask collection"""
        tasks = await CrmTask.find(
            CrmTask.deal_id == deal_id,
            CrmTask.tenant_id == tenant_id,
            CrmTask.archived_at == None
        ).sort(-CrmTask.created_at).to_list()

        result = []
        for t in tasks:
            owner_name = None
            if t.owner_id:
                owner = await User.find_one(User.id == t.owner_id)
                if owner:
                    owner_name = f"{owner.first_name} {owner.last_name}".strip()
            assigned_name = None
            if t.assigned_to:
                assigned_user = await User.find_one(User.id == t.assigned_to)
                assigned_name = f"{assigned_user.first_name} {assigned_user.last_name}".strip() if assigned_user else "Unknown"
            result.append({
                "id": str(t.id),
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "status": t.status,
                "type": t.type,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "owner_id": str(t.owner_id) if t.owner_id else None,
                "owner_name": owner_name,
                "assigned_to": str(t.assigned_to) if t.assigned_to else None,
                "assigned_to_name": assigned_name,
                "lead_id": str(t.lead_id) if t.lead_id else None,
                "contact_id": str(t.contact_id) if t.contact_id else None,
                "deal_id": str(t.deal_id) if t.deal_id else None,
                "created_by": str(t.created_by),
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "created_at": t.created_at.isoformat(),
            })
        return result

    @staticmethod
    async def create_task(deal_id: UUID, title: str, description: Optional[str], priority: str, due_date: Optional[str], assigned_to: Optional[UUID], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Create a task using the centralized CrmTask model, associated with this deal"""
        from Models.crm_task import CrmTask
        
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        # Normalize priority
        if priority not in ["high", "medium", "low", "urgent"]:
            priority = "medium"

        due_date_dt = datetime.fromisoformat(due_date) if due_date and isinstance(due_date, str) else None

        task = CrmTask(
            tenant_id=tenant_id,
            title=title,
            description=description,
            type="task",
            priority=priority,
            status="not_started",
            owner_id=user_id,
            assigned_to=assigned_to,
            lead_id=deal.lead_id,
            deal_id=deal.id,
            due_date=due_date_dt,
            created_by=user_id,
            updated_by=user_id
        )
        await task.insert()

        # Create activity feed
        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="task",
            title=f"Task Created: {title}",
            description=description or "No description",
            metadata={"task_id": str(task.id), "priority": priority, "due_date": due_date},
            created_by=user_id
        )
        await feed.insert()

        return {
            "id": str(task.id),
            "title": title,
            "priority": priority,
            "status": "not_started",
            "deal_id": str(deal.id),
            "lead_id": str(deal.lead_id) if deal.lead_id else None
        }

    @staticmethod
    async def update_task_status(deal_id: UUID, task_id: UUID, status: str, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Update task status using the centralized CrmTask model"""
        from Models.crm_task import CrmTask
        
        task = await CrmTask.find_one(
            CrmTask.id == task_id,
            CrmTask.deal_id == deal_id,
            CrmTask.tenant_id == tenant_id
        )
        if not task:
            raise ValueError("Task not found")

        valid_statuses = ["not_started", "in_progress", "waiting", "completed", "cancelled"]
        # Handle old DealTaskStatus naming convention for backward compatibility
        status_map = {
            "pending": "not_started",
            "active": "in_progress",
        }
        if status in status_map:
            status = status_map[status]
        if status not in valid_statuses:
            status = "not_started"

        task.status = status
        task.updated_at = datetime.utcnow()
        task.updated_by = user_id
        if status == "completed":
            task.completed_at = datetime.utcnow()
        await task.save()

        return {"id": str(task.id), "status": status}

    # ── Documents ────────────────────────────────────────────────────────

    @staticmethod
    async def get_documents(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        docs = await CrmDealDocument.find(
            CrmDealDocument.deal_id == deal_id,
            CrmDealDocument.tenant_id == tenant_id
        ).sort(-CrmDealDocument.uploaded_at).to_list()

        result = []
        for d in docs:
            user = await User.find_one(User.id == d.uploaded_by)
            result.append({
                "id": str(d.id),
                "file_name": d.file_name,
                "file_url": d.file_url,
                "file_size": d.file_size,
                "file_type": d.file_type,
                "uploaded_by": str(d.uploaded_by),
                "uploaded_by_name": f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                "uploaded_at": d.uploaded_at.isoformat(),
            })
        return result

    @staticmethod
    async def upload_document(deal_id: UUID, file_name: str, file_url: Optional[str], file_size: Optional[str], file_type: Optional[str], user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        doc = CrmDealDocument(
            deal_id=deal.id,
            tenant_id=tenant_id,
            file_name=file_name,
            file_url=file_url,
            file_size=file_size,
            file_type=file_type,
            uploaded_by=user_id
        )
        await doc.insert()

        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="document",
            title=f"Document Uploaded: {file_name}",
            description=f"File type: {file_type or 'Unknown'}, Size: {file_size or 'Unknown'}",
            metadata={"document_id": str(doc.id), "file_name": file_name},
            created_by=user_id
        )
        await feed.insert()

        return {"id": str(doc.id), "file_name": file_name}

    # ── Timeline / Activity Feed ─────────────────────────────────────────

    @staticmethod
    async def get_timeline(deal_id: UUID, tenant_id: UUID) -> List[Dict[str, Any]]:
        """Get combined timeline from activity feed, system activities, and audit logs"""
        feed_events = await CrmDealActivityFeed.find(
            CrmDealActivityFeed.deal_id == deal_id,
            CrmDealActivityFeed.tenant_id == tenant_id
        ).sort(-CrmDealActivityFeed.created_at).to_list()

        audit_logs = await CrmDealAuditLog.find(
            CrmDealAuditLog.deal_id == deal_id,
            CrmDealAuditLog.tenant_id == tenant_id
        ).sort(-CrmDealAuditLog.timestamp).to_list()

        timeline = []

        for f in feed_events:
            user = await User.find_one(User.id == f.created_by)
            timeline.append({
                "id": str(f.id),
                "type": f.activity_type,
                "title": f.title,
                "description": f.description,
                "metadata": f.metadata,
                "created_by": str(f.created_by),
                "created_by_name": f"{user.first_name} {user.last_name}".strip() if user else "Unknown",
                "created_at": f.created_at.isoformat(),
            })

        for log in audit_logs:
            already_exists = any(
                t["type"] == "stage_change" and t["description"] == log.details
                for t in timeline
            )
            if not already_exists:
                user = await User.find_one(User.id == log.user_id)
                timeline.append({
                    "id": f"audit-{str(log.id)}",
                    "type": "audit",
                    "title": f"Action: {log.action.replace('_', ' ').title()}",
                    "description": log.details,
                    "metadata": {},
                    "created_by": str(log.user_id),
                    "created_by_name": f"{user.first_name} {user.last_name}".strip() if user else "System",
                    "created_at": log.timestamp.isoformat(),
                })

        timeline.sort(key=lambda x: x["created_at"], reverse=True)
        return timeline

    # ── Associations ─────────────────────────────────────────────────────

    @staticmethod
    async def get_associations(deal_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """Get associated lead, contact, company, tasks, meetings, documents"""
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        lead = await CrmLead.find_one(CrmLead.id == deal.lead_id)
        
        # Get associated contact from lead
        contact = None
        if lead:
            from Models.crm_contacts import CrmContact
            contact = await CrmContact.find_one(CrmContact.lead_id == lead.id, CrmContact.tenant_id == tenant_id)

        # Use centralized CrmTask model instead of CrmDealTask
        tasks = await CrmTask.find(
            CrmTask.deal_id == deal.id,
            CrmTask.tenant_id == tenant_id,
            CrmTask.archived_at == None
        ).sort(-CrmTask.created_at).to_list()

        meetings = await CrmDealMeeting.find(
            CrmDealMeeting.deal_id == deal.id,
            CrmDealMeeting.tenant_id == tenant_id
        ).sort(-CrmDealMeeting.start_time).to_list()

        docs = await CrmDealDocument.find(
            CrmDealDocument.deal_id == deal.id,
            CrmDealDocument.tenant_id == tenant_id
        ).sort(-CrmDealDocument.uploaded_at).to_list()

        return {
            "lead": {
                "id": str(lead.id) if lead else None,
                "name": f"{lead.first_name} {lead.last_name}".strip() if lead else None,
                "source": lead.source.value if lead and hasattr(lead.source, 'value') else str(lead.source) if lead and lead.source else None,
                "status": lead.status.value if lead and hasattr(lead.status, 'value') else str(lead.status) if lead and lead.status else None,
            } if lead else None,
            "contact": {
                "id": str(contact.id) if contact else None,
                "name": contact.full_name if contact else None,
                "email": contact.email if contact else None,
                "phone": contact.phone if contact else None,
                "designation": contact.job_title if contact else None,
            } if contact else None,
            "company": {
                "name": lead.company_name if lead else None,
                "industry": lead.industry if lead else None,
                "employees": lead.company_size if lead else None,
                "website": lead.website if lead else None,
            } if lead else None,
            "tasks": {
                "pending": [
                    {"id": str(t.id), "title": t.title, "due_date": t.due_date.isoformat() if t.due_date else None, "priority": t.priority}
                    for t in tasks if t.status in ["not_started", "in_progress", "waiting"]
                ],
                "completed": [
                    {"id": str(t.id), "title": t.title, "completed_at": t.completed_at.isoformat() if t.completed_at else None}
                    for t in tasks if t.status == "completed"
                ]
            },
            "meetings": {
                "upcoming": [
                    {"id": str(m.id), "title": m.title, "start_time": m.start_time.isoformat(), "meeting_link": m.meeting_link}
                    for m in meetings if (m.status == DealMeetingStatus.scheduled or (hasattr(m.status, 'value') and m.status.value == 'scheduled') or str(m.status) == 'scheduled') and m.start_time >= datetime.utcnow()
                ],
                "completed": [
                    {"id": str(m.id), "title": m.title, "start_time": m.start_time.isoformat()}
                    for m in meetings if (m.status == DealMeetingStatus.completed or (hasattr(m.status, 'value') and m.status.value == 'completed') or str(m.status) == 'completed')
                ]
            },
            "documents": [
                {"id": str(d.id), "file_name": d.file_name, "file_url": d.file_url, "uploaded_at": d.uploaded_at.isoformat()}
                for d in docs
            ]
        }

    # ── Email ────────────────────────────────────────────────────────────

    @staticmethod
    async def send_email(deal_id: UUID, subject: str, body: str, user_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        deal = await CrmDeal.find_one(CrmDeal.id == deal_id, CrmDeal.tenant_id == tenant_id)
        if not deal:
            raise ValueError("Deal not found")

        activity = CrmActivity(
            tenant_id=tenant_id,
            deal_id=deal.id,
            lead_id=deal.lead_id,
            activity_type=ActivityType.email,
            subject=subject,
            body=body,
            direction="outbound",
            completed_at=datetime.utcnow(),
            created_by=user_id
        )
        await activity.insert()

        feed = CrmDealActivityFeed(
            deal_id=deal.id,
            tenant_id=tenant_id,
            activity_type="email",
            title=f"Email Sent: {subject}",
            description=body[:200] if body else "No content",
            metadata={"subject": subject},
            created_by=user_id
        )
        await feed.insert()

        return {"id": str(activity.id), "subject": subject}