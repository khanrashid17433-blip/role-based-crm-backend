from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from datetime import datetime
from typing import List

from Utility.auth_helpers import get_current_user
from Models.ticket import Ticket, TicketComment, TicketActivity
from Models.tenant_user import User
from Models.employee import Employee
from Schema.ticket import (
    TicketCreate, TicketUpdateStatus, TicketAssign, 
    TicketCommentCreate, TicketCommentResponse, TicketResponse, 
    TicketsListResponse, BulkStatusUpdate, BulkAssignUpdate, BulkDelete
)

router = APIRouter(prefix="/api/v1/tickets", tags=["Tickets"])

def get_tenant_and_user_ids(current_user: dict) -> tuple[UUID, UUID]:
    tenant_id_str = current_user.get('tid') or current_user.get('tenant_id')
    user_id_str = current_user.get('sub') or current_user.get('user_id') or current_user.get('id')
    if not tenant_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant ID missing from token payload")
    if not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID missing from token payload")
    return UUID(str(tenant_id_str)), UUID(str(user_id_str))

async def get_user_display_details(user_id: UUID) -> tuple[str, str]:
    """Helper to get user's display name and role description"""
    name = "Anonymous"
    role = "Staff"
    try:
        user = await User.get(user_id)
        if user:
            name = user.display_name or f"{user.first_name} {user.last_name}".strip() or user.email
            role = user.role or "Staff"
    except Exception:
        pass
    return name, role

@router.get("", response_model=TicketsListResponse)
async def list_tickets(current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        _, user_role = await get_user_display_details(user_id)
        
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        
        if not is_staff:
            employee = await Employee.find_one(Employee.user_id == user_id, Employee.tenant_id == tenant_id)
            employee_id = employee.id if employee else user_id
            tickets = await Ticket.find(
                Ticket.tenant_id == tenant_id,
                Ticket.employee_id == employee_id
            ).sort(-Ticket.created_at).to_list()
        else:
            tickets = await Ticket.find(Ticket.tenant_id == tenant_id).sort(-Ticket.created_at).to_list()
            
        return TicketsListResponse(tickets=tickets)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch tickets: {str(e)}")

@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(data: TicketCreate, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        
        # Resolve user name and role for activity logging
        user_name, user_role = await get_user_display_details(user_id)
        
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        
        # Resolve employee link
        employee = await Employee.find_one(Employee.user_id == user_id, Employee.tenant_id == tenant_id)
        employee_id = employee.id if employee else user_id
        
        employee_name = data.employee_name
        if not is_staff:
            if employee:
                employee_name = f"{employee.first_name} {employee.last_name}".strip()
            else:
                employee_name = user_name
        
        # Calculate sequence ID (e.g. TKT-2026-00101)
        count = await Ticket.find(Ticket.tenant_id == tenant_id).count()
        ticket_seq_id = f"TKT-2026-00{101 + count}"
        
        ticket = Ticket(
            ticket_seq_id=ticket_seq_id,
            tenant_id=tenant_id,
            employee_name=employee_name,
            employee_id=employee_id,
            department=data.department,
            issue_type=data.issue_type,
            priority=data.priority,
            status="Open",
            description=data.description,
            attachments=data.attachments or [],
            comments=[],
            activity=[
                TicketActivity(
                    action="Ticket Created",
                    time=datetime.utcnow(),
                    user_name=user_name
                )
            ]
        )
        await ticket.insert()
        return ticket
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create ticket: {str(e)}")

@router.patch("/{ticket_id}/status", response_model=TicketResponse)
async def update_ticket_status(ticket_id: UUID, data: TicketUpdateStatus, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        user_name, user_role = await get_user_display_details(user_id)
        
        ticket = await Ticket.find_one(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        
        if not is_staff:
            employee = await Employee.find_one(Employee.user_id == user_id, Employee.tenant_id == tenant_id)
            employee_id = employee.id if employee else user_id
            if ticket.employee_id != employee_id:
                raise HTTPException(status_code=403, detail="Not authorized to update status of this ticket")
            
        old_status = ticket.status
        ticket.status = data.status
        ticket.activity.append(
            TicketActivity(
                action=f"Status updated from {old_status} to {data.status}",
                time=datetime.utcnow(),
                user_name=user_name
            )
        )
        await ticket.save()
        return ticket
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update ticket status: {str(e)}")

@router.patch("/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(ticket_id: UUID, data: TicketAssign, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        user_name, user_role = await get_user_display_details(user_id)
        
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        if not is_staff:
            raise HTTPException(status_code=403, detail="Employees are not authorized to assign tickets")
            
        ticket = await Ticket.find_one(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        ticket.assigned_to = data.assigned_to
        ticket.assigned_to_id = data.assigned_to_id
        ticket.assigned_role = data.assigned_role
        ticket.activity.append(
            TicketActivity(
                action=f"Assigned ticket to {data.assigned_to} ({data.assigned_role})",
                time=datetime.utcnow(),
                user_name=user_name
            )
        )
        await ticket.save()
        return ticket
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assign ticket: {str(e)}")

@router.post("/{ticket_id}/comments", response_model=TicketCommentResponse)
async def add_ticket_comment(ticket_id: UUID, data: TicketCommentCreate, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        user_name, user_role = await get_user_display_details(user_id)
        
        ticket = await Ticket.find_one(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
            
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        if not is_staff:
            employee = await Employee.find_one(Employee.user_id == user_id, Employee.tenant_id == tenant_id)
            employee_id = employee.id if employee else user_id
            if ticket.employee_id != employee_id:
                raise HTTPException(status_code=403, detail="Not authorized to comment on this ticket")
                
        avatar_letter = "".join([part[0].upper() for part in user_name.split() if part])[:2]
        if not avatar_letter:
            avatar_letter = "U"
            
        comment = TicketComment(
            sender=user_name,
            role=user_role,
            text=data.text,
            time=datetime.utcnow(),
            avatar_letter=avatar_letter,
            user_id=user_id
        )
        
        if not ticket.comments:
            ticket.comments = []
        ticket.comments.append(comment)
        
        ticket.activity.append(
            TicketActivity(
                action="Added comment to discussion",
                time=datetime.utcnow(),
                user_name=user_name
            )
        )
        await ticket.save()
        return comment
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add comment: {str(e)}")

@router.post("/bulk/status")
async def bulk_update_status(data: BulkStatusUpdate, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        user_name, user_role = await get_user_display_details(user_id)
        
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        if not is_staff:
            raise HTTPException(status_code=403, detail="Employees are not authorized to run bulk status updates")
            
        updated_count = 0
        for ticket_id in data.ticket_ids:
            ticket = await Ticket.find_one(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
            if ticket:
                old_status = ticket.status
                ticket.status = data.status
                ticket.activity.append(
                    TicketActivity(
                        action=f"Bulk updated status from {old_status} to {data.status}",
                        time=datetime.utcnow(),
                        user_name=user_name
                    )
                )
                await ticket.save()
                updated_count += 1
        return {"status": "success", "updated_count": updated_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk/assign")
async def bulk_assign_tickets(data: BulkAssignUpdate, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        user_name, user_role = await get_user_display_details(user_id)
        
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        if not is_staff:
            raise HTTPException(status_code=403, detail="Employees are not authorized to assign tickets")
            
        updated_count = 0
        for ticket_id in data.ticket_ids:
            ticket = await Ticket.find_one(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
            if ticket:
                ticket.assigned_to = data.assigned_to
                ticket.assigned_to_id = data.assigned_to_id
                ticket.assigned_role = data.assigned_role
                ticket.activity.append(
                    TicketActivity(
                        action=f"Bulk assigned ticket to {data.assigned_to} ({data.assigned_role})",
                        time=datetime.utcnow(),
                        user_name=user_name
                    )
                )
                await ticket.save()
                updated_count += 1
        return {"status": "success", "updated_count": updated_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/bulk/delete")
async def bulk_delete_tickets(data: BulkDelete, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id, user_id = get_tenant_and_user_ids(current_user)
        _, user_role = await get_user_display_details(user_id)
        
        user_role_lower = user_role.lower().strip()
        is_staff = any(r in user_role_lower for r in ["admin", "super", "owner", "hr", "manager"])
        if not is_staff:
            raise HTTPException(status_code=403, detail="Employees are not authorized to delete tickets")
            
        deleted_count = 0
        for ticket_id in data.ticket_ids:
            ticket = await Ticket.find_one(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
            if ticket:
                await ticket.delete()
                deleted_count += 1
        return {"status": "success", "deleted_count": deleted_count}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
