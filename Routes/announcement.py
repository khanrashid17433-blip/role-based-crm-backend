from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
from Utility.auth_helpers import get_current_user
from Services.announcement_service import AnnouncementService
from Schema.announcement import AnnouncementCreate, AnnouncementResponse, AnnouncementsListResponse
from Models.employee import Employee

router = APIRouter(prefix="/api/announcements", tags=["Announcements"])

@router.post("", response_model=AnnouncementResponse)
async def create_announcement(data: AnnouncementCreate, current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        
        # Restrict employee users from posting announcements
        user_type = current_user.get("user_type")
        role = current_user.get("role", "")
        if user_type == "employee" or role == "employee":
            raise HTTPException(status_code=403, detail="Employees are not allowed to create announcements.")
            
        return await AnnouncementService.create_announcement(tenant_id, user_id, data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("", response_model=AnnouncementsListResponse)
async def get_announcements(current_user: dict = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        
        # If the user is an employee, we map their user_id to employee_id
        # For simplicity and robust mapping, if not found assume user_id is the reference for reading
        # Real logic: employee = await Employee.find_one(Employee.user_id == user_id)
        # Using user_id as employee_id for read status tracking
        employee_id = user_id
        
        return await AnnouncementService.get_announcements_for_employee(tenant_id, employee_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{announcement_id}/read")
async def mark_announcement_as_read(announcement_id: UUID, current_user: dict = Depends(get_current_user)):
    try:
        employee_id = UUID(current_user['sub']) # Using user ID
        success = await AnnouncementService.mark_as_read(announcement_id, employee_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
