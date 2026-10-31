from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from uuid import UUID
import logging
import os

from Services.deal_workspace_service import DealWorkspaceService
from Utility.auth_helpers import get_current_user, verify_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/deals", tags=["Deal Workspace"])


@router.get("/{deal_id}/workspace", summary="Get Complete Deal Workspace")
async def get_deal_workspace(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        workspace = await DealWorkspaceService.get_deal_workspace(UUID(deal_id), tenant_id)
        return workspace
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{deal_id}/associations", summary="Get Deal Associations")
async def get_deal_associations(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        associations = await DealWorkspaceService.get_associations(UUID(deal_id), tenant_id)
        return associations
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Pipeline Stage ───────────────────────────────────────────────────

@router.patch("/{deal_id}/stage", summary="Update Deal Stage")
async def update_deal_stage(deal_id: str, stage: str = Query(...), current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await DealWorkspaceService.update_stage(UUID(deal_id), stage, user_id, tenant_id)
        return {"message": "Stage updated", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Notes ────────────────────────────────────────────────────────────

@router.get("/{deal_id}/notes", summary="Get Deal Notes")
async def get_notes(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        notes = await DealWorkspaceService.get_notes(UUID(deal_id), tenant_id)
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/notes", summary="Add Deal Note")
async def add_note(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        note = await DealWorkspaceService.add_note(
            UUID(deal_id), data.get("note", ""), data.get("is_pinned", False), user_id, tenant_id
        )
        return {"message": "Note added", "note": note}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{deal_id}/notes/{note_id}", summary="Update Deal Note")
async def update_note(deal_id: str, note_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await DealWorkspaceService.update_note(UUID(deal_id), UUID(note_id), data, user_id, tenant_id)
        return {"message": "Note updated", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{deal_id}/notes/{note_id}", summary="Delete Deal Note")
async def delete_note(deal_id: str, note_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        await DealWorkspaceService.delete_note(UUID(deal_id), UUID(note_id), tenant_id)
        return {"message": "Note deleted"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{deal_id}/notes/{note_id}/pin", summary="Toggle Note Pin")
async def toggle_note_pin(deal_id: str, note_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await DealWorkspaceService.toggle_note_pin(UUID(deal_id), UUID(note_id), tenant_id)
        return {"message": "Pin toggled", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Calls ────────────────────────────────────────────────────────────

@router.get("/{deal_id}/calls", summary="Get Deal Calls")
async def get_calls(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        calls = await DealWorkspaceService.get_calls(UUID(deal_id), tenant_id)
        return calls
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/calls", summary="Log Deal Call")
async def log_call(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        call = await DealWorkspaceService.log_call(
            UUID(deal_id),
            data.get("call_type", "outbound"),
            data.get("duration"),
            data.get("outcome"),
            data.get("notes"),
            user_id,
            tenant_id
        )
        return {"message": "Call logged", "call": call}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Meetings ─────────────────────────────────────────────────────────

@router.get("/{deal_id}/meetings", summary="Get Deal Meetings")
async def get_meetings(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        meetings = await DealWorkspaceService.get_meetings(UUID(deal_id), tenant_id)
        return meetings
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/meetings", summary="Schedule Deal Meeting")
async def schedule_meeting(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        meeting = await DealWorkspaceService.schedule_meeting(
            UUID(deal_id),
            data.get("title", "Meeting"),
            data.get("agenda"),
            data.get("meeting_link"),
            data.get("start_time"),
            data.get("end_time"),
            user_id,
            tenant_id
        )
        return {"message": "Meeting scheduled", "meeting": meeting}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{deal_id}/meetings/{meeting_id}", summary="Update Deal Meeting")
async def update_meeting(deal_id: str, meeting_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        meeting = await DealWorkspaceService.update_meeting(
            UUID(deal_id),
            UUID(meeting_id),
            data,
            user_id,
            tenant_id
        )
        return {"message": "Meeting updated", "meeting": meeting}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Tasks ────────────────────────────────────────────────────────────

@router.get("/{deal_id}/tasks", summary="Get Deal Tasks")
async def get_tasks(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        tasks = await DealWorkspaceService.get_tasks(UUID(deal_id), tenant_id)
        return tasks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/tasks", summary="Create Deal Task")
async def create_task(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        
        assigned_to = None
        if data.get("assigned_to"):
            assigned_to = UUID(data["assigned_to"])
            
        task = await DealWorkspaceService.create_task(
            UUID(deal_id),
            data.get("title", "Task"),
            data.get("description"),
            data.get("priority", "medium"),
            data.get("due_date"),
            assigned_to,
            user_id,
            tenant_id
        )
        return {"message": "Task created", "task": task}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{deal_id}/tasks/{task_id}", summary="Update Task Status")
async def update_task_status(deal_id: str, task_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await DealWorkspaceService.update_task_status(
            UUID(deal_id), UUID(task_id), data.get("status", "pending"), user_id, tenant_id
        )
        return {"message": "Task updated", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Documents ────────────────────────────────────────────────────────

@router.get("/{deal_id}/documents", summary="Get Deal Documents")
async def get_documents(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        docs = await DealWorkspaceService.get_documents(UUID(deal_id), tenant_id)
        return docs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{deal_id}/documents", summary="Upload Deal Document")
async def upload_document(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        doc = await DealWorkspaceService.upload_document(
            UUID(deal_id),
            data.get("file_name", "document"),
            data.get("file_url"),
            data.get("file_size"),
            data.get("file_type"),
            user_id,
            tenant_id
        )
        return {"message": "Document uploaded", "document": doc}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Timeline ─────────────────────────────────────────────────────────

@router.get("/{deal_id}/timeline", summary="Get Deal Timeline")
async def get_timeline(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        timeline = await DealWorkspaceService.get_timeline(UUID(deal_id), tenant_id)
        return timeline
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Email ────────────────────────────────────────────────────────────

@router.get("/{deal_id}/emails", summary="Get Deal Emails")
async def get_emails(deal_id: str, current_user=Depends(verify_platform_admin)):
    try:
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        from Models.crm import CrmActivity, ActivityType
        from Models.tenant_user import User
        
        # Fetch email activities for this deal from CrmActivity
        activities = await CrmActivity.find(
            CrmActivity.deal_id == UUID(deal_id),
            CrmActivity.activity_type == ActivityType.email,
            CrmActivity.tenant_id == tenant_id
        ).sort(-CrmActivity.created_at).to_list()
        
        result = []
        for act in activities:
            user = None
            sender_name = "System"
            if act.created_by:
                user = await User.find_one(User.id == act.created_by)
                if user:
                    sender_name = f"{user.first_name or ''} {user.last_name or ''}".strip() or user.email or "System"
            
            result.append({
                "id": str(act.id),
                "subject": act.subject or "No Subject",
                "body": act.body or "",
                "from": sender_name,
                "from_name": sender_name,
                "from_email": user.email if user else "",
                "to": act.outcome or "",
                "direction": act.direction or "outbound",
                "created_at": act.created_at.isoformat() if act.created_at else None,
                "deal_id": str(act.deal_id) if act.deal_id else None,
                "lead_id": str(act.lead_id) if act.lead_id else None,
            })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{deal_id}/email", summary="Send Email from Deal")
async def send_email(deal_id: str, data: Dict[str, Any], current_user=Depends(verify_platform_admin)):
    try:
        user_id = UUID(current_user.get('sub'))
        tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
        result = await DealWorkspaceService.send_email(
            UUID(deal_id),
            data.get("subject", "No Subject"),
            data.get("body", ""),
            user_id,
            tenant_id
        )
        return {"message": "Email sent", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))