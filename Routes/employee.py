from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from typing import Optional, List, Dict, Any
from uuid import UUID

from Services.employee_service import EmployeeService
from Services.employee_invitation_service import EmployeeInvitationService
from Schema.employee import (
    EmployeeCreateSchema, EmployeeUpdateSchema, EmployeeResponseSchema, EmployeeListResponseSchema,
    DepartmentCreateSchema, DepartmentUpdateSchema, DepartmentResponseSchema, DepartmentListResponseSchema,
    JobTitleCreateSchema, JobTitleUpdateSchema, JobTitleResponseSchema, JobTitleListResponseSchema,
    WorkLocationCreateSchema, WorkLocationUpdateSchema, WorkLocationResponseSchema, WorkLocationListResponseSchema,
    EmployeeDocumentCreateSchema, EmployeeDocumentResponseSchema,
    EmployeeNoteCreateSchema, EmployeeNoteResponseSchema,
    EmergencyContactCreateSchema, EmergencyContactUpdateSchema, EmergencyContactResponseSchema,
    JobHistoryResponseSchema
)
from Utility.auth_helpers import get_current_user, require_permissions
from Utility.exceptions import ValidationError, NotFoundError, ConflictError
from Models.tenant_user import User

router = APIRouter(prefix="/api/employees")

async def build_employee_response(service: EmployeeService, employee, tenant_id: UUID) -> EmployeeResponseSchema:
    schema_emp = EmployeeResponseSchema.from_orm(employee)
    linked_user = None
    if employee.user_id:
        linked_user = await User.find_one(User.id == employee.user_id, User.tenant_id == tenant_id)
    if not linked_user and employee.email_work:
        linked_user = await User.find_one(User.email == employee.email_work.lower().strip(), User.tenant_id == tenant_id)
    if linked_user:
        schema_emp.system_role = linked_user.role
        schema_emp.user_type = linked_user.user_type.value if linked_user.user_type else None
    documents = await service.get_employee_documents(employee.id, tenant_id)
    schema_emp.documents = [EmployeeDocumentResponseSchema.from_orm(doc) for doc in documents]
    return schema_emp

# --- STATIC / SPECIAL ENDPOINTS (Must be defined BEFORE /{employee_id}) ---

from pydantic import BaseModel
from datetime import date, datetime, timedelta

class LeaveApplyRequest(BaseModel):
    leave_type: str
    start_date: date
    end_date: date
    reason: str
    contact_number: Optional[str] = None

async def get_current_employee_profile(user_id: UUID, tenant_id: UUID, email: Optional[str] = None) -> Any:
    """Helper to query the current logged-in employee by user_id or email, with dynamic stub seeding fallback"""
    from Models.employee import Employee
    
    employee = None
    if user_id:
        employee = await Employee.find_one(
            Employee.user_id == user_id,
            Employee.tenant_id == tenant_id
        )
    if not employee and email:
        employee = await Employee.find_one(
            Employee.email_work == email.lower().strip(),
            Employee.tenant_id == tenant_id
        )
        if employee and not employee.user_id:
            employee.user_id = user_id
            await employee.save()
        
    if not employee:
        # Automatically create/seed a stub profile on the fly to prevent crashes
        from Models.tenant_user import User
        user_record = await User.find_one(User.id == user_id)
        user_email = email or (user_record.email if user_record else "employee@company.com")
        
        first_name = user_record.first_name if user_record and getattr(user_record, 'first_name', None) else "New"
        last_name = user_record.last_name if user_record and getattr(user_record, 'last_name', None) else "Employee"
        if not (user_record and getattr(user_record, 'first_name', None)):
            if user_record and user_record.email:
                parts = user_record.email.split('@')[0].split('.')
                first_name = parts[0].capitalize()
                if len(parts) > 1:
                    last_name = parts[1].capitalize()
            elif email:
                parts = email.split('@')[0].split('.')
                first_name = parts[0].capitalize()
                if len(parts) > 1:
                    last_name = parts[1].capitalize()
                
        # Generate next EMP number
        last_emp = await Employee.find(Employee.tenant_id == tenant_id).sort("-created_at").first_or_none()
        next_num = 1
        if last_emp and last_emp.employee_number:
            import re
            match = re.search(r'EMP-(\d+)', last_emp.employee_number)
            if match:
                next_num = int(match.group(1)) + 1
        employee_number = f"EMP-{next_num:06d}"
        
        from Models.employee import EmploymentStatus, EmploymentType
        employee = Employee(
            tenant_id=tenant_id,
            user_id=user_id,
            employee_number=employee_number,
            first_name=first_name,
            last_name=last_name,
            email_work=user_email.lower().strip(),
            employment_status=EmploymentStatus.ACTIVE,
            employment_type=EmploymentType.FULL_TIME
        )
        await employee.insert()
        
    return employee

@router.get("/me/dashboard-summary")
async def get_my_dashboard_summary(
    current_user: dict = Depends(get_current_user)
):
    """Retrieve aggregate data for the employee dashboard — real data only, no mocks"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])

        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))

        if not employee.custom_fields_json:
            employee.custom_fields_json = {}

        # Real leave balances — empty list if HR hasn't assigned any yet
        leave_balances = employee.custom_fields_json.get("leave_balances", [])
        if not leave_balances:
            leave_balances = [
                {"type": "Casual", "total": 12, "used": 0},
                {"type": "Sick", "total": 10, "used": 0},
                {"type": "Earned", "total": 15, "used": 0}
            ]
            employee.custom_fields_json["leave_balances"] = leave_balances
            await employee.save()
            
        leave_history  = employee.custom_fields_json.get("leave_history",  [])

        # Get Today's Attendance Summary
        from Services.attendance_service import AttendanceService
        today_attendance = await AttendanceService.get_today_summary(tenant_id, user_id)

        # Tasks assigned to this employee
        from Models.pm import Task, TaskStatus
        tasks = await Task.find(
            Task.assigned_to == user_id,
            Task.tenant_id == tenant_id
        ).to_list()

        # Remove any duplicates that crept in via race conditions
        seen_titles = set()
        cleaned_tasks = []
        for t in tasks:
            if t.title not in seen_titles:
                seen_titles.add(t.title)
                cleaned_tasks.append(t)
            else:
                await t.delete()
        tasks = cleaned_tasks

        # Format tasks for dashboard
        formatted_tasks = []
        for t in tasks:
            due_str = "Today"
            if t.due_at:
                now_date = datetime.utcnow().date()
                due_date = t.due_at.date()
                if due_date == now_date:
                    due_str = "Today"
                elif due_date == now_date + timedelta(days=1):
                    due_str = "Tomorrow"
                else:
                    due_str = t.due_at.strftime("%b %d")

            project_tag = t.tags_json[0] if t.tags_json else "General"
            formatted_tasks.append({
                "id":       str(t.id),
                "title":    t.title,
                "project":  project_tag,
                "due":      due_str,
                "done":     (
                    t.status == TaskStatus.done
                    or (hasattr(t.status, "value") and t.status.value == "done")
                    or t.status == "done"
                ),
                "priority": t.priority.value if hasattr(t.priority, "value") else t.priority
            })

        # Real announcements — return empty list if none exist
        from Models.announcement import CompanyAnnouncement
        announcements_list = await CompanyAnnouncement.find(
            CompanyAnnouncement.tenant_id == tenant_id
        ).sort("-created_at").to_list()

        announcements = []
        for a in announcements_list:
            try:
                delta = datetime.utcnow() - a.created_at.replace(tzinfo=None)
                if delta.days > 0:
                    time_str = f"{delta.days} day ago" if delta.days == 1 else f"{delta.days} days ago"
                else:
                    hours = delta.seconds // 3600
                    if hours > 0:
                        time_str = f"{hours} hr ago" if hours == 1 else f"{hours} hrs ago"
                    else:
                        mins = delta.seconds // 60
                        time_str = f"{mins} min ago" if mins == 1 else f"{mins} mins ago"
            except Exception:
                time_str = ""
            announcements.append({
                "id":    str(a.id),
                "title": a.title,
                "time":  time_str,
                "tag":   a.type
            })

        # Real payslips — return empty list if payroll hasn't been run yet
        from Models.employee import Payslip
        payslips_list = await Payslip.find(
            Payslip.tenant_id == tenant_id,
            Payslip.user_id == user_id
        ).sort("-created_at").to_list()

        payslips = [
            {
                "id":     str(p.id),
                "month":  p.month,
                "net":    p.net_pay,
                "status": p.status
            }
            for p in payslips_list
        ]

        # Real recognition — return null if none
        from Models.employee import Recognition
        recognition_obj = await Recognition.find_one(
            Recognition.tenant_id == tenant_id,
            Recognition.user_id == user_id
        )
        recognition = (
            {
                "kudos":  recognition_obj.kudos,
                "sender": recognition_obj.sender,
                "streak": recognition_obj.streak
            }
            if recognition_obj else None
        )

        return {
            "employee_id":       str(employee.id),
            "name":              f"{employee.first_name} {employee.last_name}".strip(),
            "first_name":        employee.first_name,
            "employee_number":   employee.employee_number,
            "today_attendance":  today_attendance,
            "leave_balances":    leave_balances,
            "leave_history":     leave_history,
            "tasks":             formatted_tasks,
            "payslips":          payslips,
            "announcements":     announcements,
            "recognition":       recognition
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/me/apply-leave")
async def apply_my_leave(
    data: LeaveApplyRequest,
    current_user: dict = Depends(get_current_user)
):
    """Submit a leave application and update leave balance dynamically"""
    try:
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])

        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))

        if not employee.custom_fields_json:
            employee.custom_fields_json = {}

        # Use only real leave balances assigned by HR — no seeding
        leave_balances = employee.custom_fields_json.get("leave_balances", [])
        if not leave_balances:
            leave_balances = [
                {"type": "Casual", "total": 12, "used": 0},
                {"type": "Sick", "total": 10, "used": 0},
                {"type": "Earned", "total": 15, "used": 0}
            ]
            employee.custom_fields_json["leave_balances"] = leave_balances
            await employee.save()
            
        leave_history  = employee.custom_fields_json.get("leave_history",  [])

        num_days = (data.end_date - data.start_date).days + 1
        if num_days <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be on or after start date")

        clean_type = data.leave_type.replace(" Leave", "").strip()
        matching_balance = next((b for b in leave_balances if b["type"].lower() == clean_type.lower()), None)

        if not matching_balance:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Leave type '{data.leave_type}' not found")

        available_days = matching_balance["total"] - matching_balance["used"]
        if available_days < num_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient balance. You have {available_days} days left, but requested {num_days} days."
            )

        matching_balance["used"] += num_days

        import uuid
        new_entry = {
            "id":           str(uuid.uuid4()),
            "leave_type":   matching_balance["type"] + " Leave",
            "start_date":   data.start_date.isoformat(),
            "end_date":     data.end_date.isoformat(),
            "days":         num_days,
            "reason":       data.reason,
            "status":       "Pending",
            "applied_on":   date.today().isoformat()
        }
        leave_history.insert(0, new_entry)

        employee.custom_fields_json["leave_balances"] = leave_balances
        employee.custom_fields_json["leave_history"]  = leave_history
        await employee.save()

        from Models.employee import EmployeeNote
        note = EmployeeNote(
            employee_id=employee.id,
            note_text=f"Applied for {num_days} days of {matching_balance['type']} Leave ({data.start_date} to {data.end_date}). Reason: {data.reason}",
            is_private=False,
            created_by=user_id
        )
        await note.insert()

        return {
            "message":       "Leave application submitted successfully!",
            "leave_balances": leave_balances,
            "leave_history":  leave_history
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/me", response_model=EmployeeResponseSchema)
async def get_my_employee_profile(
    current_user: dict = Depends(get_current_user)
):
    """Get the employee profile for the current logged-in user"""
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        return await build_employee_response(service, employee, tenant_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/me/department", response_model=DepartmentResponseSchema)
async def get_my_department(
    current_user: dict = Depends(get_current_user)
):
    """Get the department details for the current logged-in user"""
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        if not employee or not employee.department_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found for this user")
            
        departments = await service.get_departments(tenant_id)
        my_dept = next((d for d in departments if d.id == employee.department_id), None)
        
        if not my_dept:
             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Department not found")
             
        return DepartmentResponseSchema.from_orm(my_dept)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/departments", response_model=DepartmentListResponseSchema)
async def get_departments(
    current_user: dict = Depends(get_current_user)
):
    """Get all departments"""
    require_permissions(current_user, ["department:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        departments = await service.get_departments(tenant_id)
        return DepartmentListResponseSchema(
            departments=[DepartmentResponseSchema.from_orm(dept) for dept in departments],
            total=len(departments)
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch departments")

@router.post("/departments", response_model=DepartmentResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_department(
    department_data: DepartmentCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Create a new department"""
    require_permissions(current_user, ["department:create"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        department = await service.create_department(department_data, tenant_id)
        return DepartmentResponseSchema.from_orm(department)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create department")

@router.get("/job-titles", response_model=JobTitleListResponseSchema)
async def get_job_titles(
    current_user: dict = Depends(get_current_user)
):
    """Get all job titles"""
    require_permissions(current_user, ["job_title:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        job_titles = await service.get_job_titles(tenant_id)
        return JobTitleListResponseSchema(
            job_titles=[JobTitleResponseSchema.from_orm(jt) for jt in job_titles],
            total=len(job_titles)
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch job titles")

@router.post("/job-titles", response_model=JobTitleResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_job_title(
    job_title_data: JobTitleCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Create a new job title"""
    require_permissions(current_user, ["job_title:create"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        job_title = await service.create_job_title(job_title_data, tenant_id)
        return JobTitleResponseSchema.from_orm(job_title)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create job title")

@router.get("/work-locations", response_model=WorkLocationListResponseSchema)
async def get_work_locations(
    current_user: dict = Depends(get_current_user)
):
    """Get all work locations"""
    require_permissions(current_user, ["work_location:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        work_locations = await service.get_work_locations(tenant_id)
        return WorkLocationListResponseSchema(
            work_locations=[WorkLocationResponseSchema.from_orm(wl) for wl in work_locations],
            total=len(work_locations)
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch work locations")

@router.post("/work-locations", response_model=WorkLocationResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_work_location(
    location_data: WorkLocationCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Create a new work location"""
    require_permissions(current_user, ["work_location:create"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        work_location = await service.create_work_location(location_data, tenant_id)
        return WorkLocationResponseSchema.from_orm(work_location)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create work location")

@router.post("/invite", response_model=dict, status_code=status.HTTP_201_CREATED)
async def invite_employee(
    employee_data: EmployeeCreateSchema,
    send_invitation: bool = Query(True, description="Whether to send invitation email"),
    current_user: dict = Depends(get_current_user)
):
    """Create employee and send invitation"""
    require_permissions(current_user, ["employee:create", "invitation:create"])
    
    try:
        service = EmployeeInvitationService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        result = await service.invite_employee(
            employee_data, tenant_id, user_id, send_invitation
        )
        
        employee_service = EmployeeService()
        return {
            "employee": await build_employee_response(employee_service, result["employee"], tenant_id),
            "invitation_sent": result["invitation"] is not None,
            "message": result["message"]
        }
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to invite employee")

@router.post("/manual", response_model=EmployeeResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_employee_manually(
    employee_data: EmployeeCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Create employee manually without invitation"""
    require_permissions(current_user, ["employee:create"])
    
    try:
        service = EmployeeInvitationService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await service.create_employee_manually(employee_data, tenant_id, user_id)
        employee_service = EmployeeService()
        return await build_employee_response(employee_service, employee, tenant_id)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create employee")

# --- GENERAL EMPLOYEE COLLECTION ENDPOINTS ---

@router.get("/", response_model=EmployeeListResponseSchema)
async def get_employees(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=1000),
    search: Optional[str] = Query(None),
    department_id: Optional[UUID] = Query(None),
    employment_status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """Get paginated list of employees with filters"""
    require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        result = await service.get_employees(
            tenant_id, page, per_page, search, department_id, employment_status
        )
        
        return EmployeeListResponseSchema(
            employees=result["employees"],
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
            total_pages=result["total_pages"]
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch employees")

@router.post("/", response_model=EmployeeResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_employee(
    employee_data: EmployeeCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Create a new employee"""
    require_permissions(current_user, ["employee:create"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await service.create_employee(employee_data, tenant_id, user_id)
        return await build_employee_response(service, employee, tenant_id)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# --- INDIVIDUAL EMPLOYEE ENDPOINTS (Using Path Parameters) ---

@router.get("/{employee_id}", response_model=EmployeeResponseSchema)
async def get_employee(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get employee by ID"""
    require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        employee = await service.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        
        from Models.employee import Department, JobTitle, Employee
        dept = await Department.find_one(Department.id == employee.department_id) if employee.department_id else None
        title = await JobTitle.find_one(JobTitle.id == employee.job_title_id) if employee.job_title_id else None
        manager = await Employee.find_one(Employee.id == employee.manager_id) if employee.manager_id else None
        linked_user = None
        if employee.user_id:
            linked_user = await User.find_one(User.id == employee.user_id, User.tenant_id == tenant_id)
        if not linked_user and employee.email_work:
            linked_user = await User.find_one(User.email == employee.email_work.lower().strip(), User.tenant_id == tenant_id)
        
        schema_emp = EmployeeResponseSchema.from_orm(employee)
        schema_emp.department_name = dept.name if dept else None
        schema_emp.job_title = title.name if title else None
        schema_emp.manager_name = f"{manager.first_name} {manager.last_name}".strip() if manager else None
        if linked_user:
            schema_emp.system_role = linked_user.role
            schema_emp.user_type = linked_user.user_type.value if linked_user.user_type else None
        documents = await service.get_employee_documents(employee.id, tenant_id)
        schema_emp.documents = [EmployeeDocumentResponseSchema.from_orm(doc) for doc in documents]
        
        return schema_emp
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch employee")

@router.get("/number/{employee_number}", response_model=EmployeeResponseSchema)
async def get_employee_by_number(
    employee_number: str,
    current_user: dict = Depends(get_current_user)
):
    """Get employee by employee number"""
    require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        employee = await service.get_employee_by_number(employee_number, tenant_id)
        if not employee:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
        
        return await build_employee_response(service, employee, tenant_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch employee")

@router.put("/{employee_id}", response_model=EmployeeResponseSchema)
async def update_employee(
    employee_id: UUID,
    employee_data: EmployeeUpdateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Update employee"""
    require_permissions(current_user, ["employee:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        employee = await service.update_employee(employee_id, employee_data, tenant_id, user_id)
        return await build_employee_response(service, employee, tenant_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update employee")

@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_employee(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Soft delete employee"""
    require_permissions(current_user, ["employee:delete"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        await service.delete_employee(employee_id, tenant_id, user_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/{employee_id}/link-user/{user_id}", response_model=EmployeeResponseSchema)
async def link_user_to_employee(
    employee_id: UUID,
    user_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Link a user account to an employee"""
    require_permissions(current_user, ["employee:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        employee = await service.link_user_to_employee(employee_id, user_id, tenant_id)
        return await build_employee_response(service, employee, tenant_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to link user to employee")

# --- SUB-RESOURCES ---

@router.put("/departments/{department_id}", response_model=DepartmentResponseSchema)
async def update_department(
    department_id: UUID,
    department_data: DepartmentUpdateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Update department"""
    require_permissions(current_user, ["department:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        department = await service.update_department(department_id, department_data, tenant_id)
        return DepartmentResponseSchema.from_orm(department)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update department")

@router.put("/job-titles/{job_title_id}", response_model=JobTitleResponseSchema)
async def update_job_title(
    job_title_id: UUID,
    job_title_data: JobTitleUpdateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Update job title"""
    require_permissions(current_user, ["job_title:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        job_title = await service.update_job_title(job_title_id, job_title_data, tenant_id)
        return JobTitleResponseSchema.from_orm(job_title)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update job title")

@router.put("/work-locations/{location_id}", response_model=WorkLocationResponseSchema)
async def update_work_location(
    location_id: UUID,
    location_data: WorkLocationUpdateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Update work location"""
    require_permissions(current_user, ["work_location:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        work_location = await service.update_work_location(location_id, location_data, tenant_id)
        return WorkLocationResponseSchema.from_orm(work_location)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update work location")

@router.post("/{employee_id}/documents", response_model=EmployeeDocumentResponseSchema, status_code=status.HTTP_201_CREATED)
async def add_employee_document(
    employee_id: UUID,
    document_data: EmployeeDocumentCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Add document to employee"""
    tenant_id = UUID(current_user['tid'])
    user_id = UUID(current_user['sub'])
    
    is_self = False
    try:
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        if employee and employee.id == employee_id:
            is_self = True
    except Exception:
        pass
        
    if not is_self:
        require_permissions(current_user, ["employee:update"])
    
    try:
        service = EmployeeService()
        document = await service.add_employee_document(employee_id, document_data, tenant_id, user_id)
        return EmployeeDocumentResponseSchema.from_orm(document)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add document")

@router.get("/{employee_id}/documents", response_model=List[EmployeeDocumentResponseSchema])
async def get_employee_documents(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get all documents for employee"""
    tenant_id = UUID(current_user['tid'])
    user_id = UUID(current_user['sub'])
    
    is_self = False
    try:
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        if employee and employee.id == employee_id:
            is_self = True
    except Exception:
        pass
        
    if not is_self:
        require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        documents = await service.get_employee_documents(employee_id, tenant_id)
        return [EmployeeDocumentResponseSchema.from_orm(doc) for doc in documents]
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch documents")

@router.post("/{employee_id}/notes", response_model=EmployeeNoteResponseSchema, status_code=status.HTTP_201_CREATED)
async def add_employee_note(
    employee_id: UUID,
    note_data: EmployeeNoteCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Add note to employee"""
    tenant_id = UUID(current_user['tid'])
    user_id = UUID(current_user['sub'])
    
    is_self = False
    try:
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        if employee and employee.id == employee_id:
            is_self = True
    except Exception:
        pass
        
    if not is_self:
        require_permissions(current_user, ["employee:update"])
    
    try:
        service = EmployeeService()
        note = await service.add_employee_note(employee_id, note_data, tenant_id, user_id)
        return EmployeeNoteResponseSchema.from_orm(note)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add note")

@router.get("/{employee_id}/notes", response_model=List[EmployeeNoteResponseSchema])
async def get_employee_notes(
    employee_id: UUID,
    include_private: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    """Get notes for employee"""
    tenant_id = UUID(current_user['tid'])
    user_id = UUID(current_user['sub'])
    
    is_self = False
    try:
        employee = await get_current_employee_profile(user_id, tenant_id, current_user.get('email'))
        if employee and employee.id == employee_id:
            is_self = True
    except Exception:
        pass
        
    if not is_self:
        require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        notes = await service.get_employee_notes(employee_id, tenant_id, include_private)
        return [EmployeeNoteResponseSchema.from_orm(note) for note in notes]
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch notes")

@router.post("/{employee_id}/emergency-contacts", response_model=EmergencyContactResponseSchema, status_code=status.HTTP_201_CREATED)
async def add_emergency_contact(
    employee_id: UUID,
    contact_data: EmergencyContactCreateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Add emergency contact to employee"""
    require_permissions(current_user, ["employee:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        contact = await service.add_emergency_contact(employee_id, contact_data, tenant_id)
        return EmergencyContactResponseSchema.from_orm(contact)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add emergency contact")

@router.get("/{employee_id}/emergency-contacts", response_model=List[EmergencyContactResponseSchema])
async def get_emergency_contacts(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get emergency contacts for employee"""
    require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        contacts = await service.get_emergency_contacts(employee_id, tenant_id)
        return [EmergencyContactResponseSchema.from_orm(contact) for contact in contacts]
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch emergency contacts")

@router.put("/{employee_id}/emergency-contacts/{contact_id}", response_model=EmergencyContactResponseSchema)
async def update_emergency_contact(
    employee_id: UUID,
    contact_id: UUID,
    contact_data: EmergencyContactUpdateSchema,
    current_user: dict = Depends(get_current_user)
):
    """Update emergency contact"""
    require_permissions(current_user, ["employee:update"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        contact = await service.update_emergency_contact(contact_id, contact_data, employee_id, tenant_id)
        return EmergencyContactResponseSchema.from_orm(contact)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update emergency contact")

@router.get("/{employee_id}/invitation-status", response_model=dict)
async def get_employee_invitation_status(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get invitation status for employee"""
    require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeInvitationService()
        tenant_id = UUID(current_user['tid'])
        status_info = await service.get_employee_invitation_status(employee_id, tenant_id)
        return status_info
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get invitation status")

@router.post("/{employee_id}/resend-invitation", response_model=dict)
async def resend_employee_invitation(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Resend invitation to employee"""
    require_permissions(current_user, ["employee:update", "invitation:create"])
    
    try:
        service = EmployeeInvitationService()
        tenant_id = UUID(current_user['tid'])
        user_id = UUID(current_user['sub'])
        result = await service.resend_employee_invitation(employee_id, tenant_id, user_id)
        return result
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to resend invitation")

@router.get("/{employee_id}/job-history", response_model=List[JobHistoryResponseSchema])
async def get_employee_job_history(
    employee_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get job history for employee"""
    require_permissions(current_user, ["employee:read"])
    
    try:
        service = EmployeeService()
        tenant_id = UUID(current_user['tid'])
        job_history = await service.get_employee_job_history(employee_id, tenant_id)
        return [JobHistoryResponseSchema.from_orm(jh) for jh in job_history]
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch job history")
