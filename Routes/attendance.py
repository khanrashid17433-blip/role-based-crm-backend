from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from typing import Dict, Any, List
from uuid import UUID
from datetime import datetime, date
import logging

from Schema.attendance import (
    WebPunchRequest, RegularisationRequest, ShiftCreateRequest, 
    BiometricPunchRequest, QrScanRequest, AttendanceAdminUpdateRequest,
    GlobalPolicyUpdateRequest, ShiftAssignRequest, RosterGenerateRequest
)
from Services.attendance_service import AttendanceService
from Utility.auth_helpers import get_current_user, verify_tenant_admin
from Models.attendance import Shift

logger = logging.getLogger(__name__)

class AttendanceConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("New live attendance websocket client connected.")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info("Live attendance websocket client disconnected.")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to ws connection: {str(e)}")
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

manager = AttendanceConnectionManager()

compat_router = APIRouter()

router = APIRouter(prefix="/api/v1/attendance", tags=["Attendance"])

@router.websocket("/ws")
async def attendance_ws_endpoint(websocket: WebSocket):
    
    await manager.connect(websocket)
    try:
        while True:
            # Heartbeat check
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.warning(f"WS endpoint exception: {str(e)}")
        manager.disconnect(websocket)

@router.get("/today", summary="Today's Attendance Summary")
async def get_today_summary(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        employee_id = UUID(current_user.get('sub'))
        summary = await AttendanceService.get_today_summary(tenant_id, employee_id)
        return summary
    except Exception as e:
        logger.error(f"Failed to fetch today's summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/punch", summary="Web/Mobile Clock In/Out")
async def web_punch(data: WebPunchRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        employee_id = UUID(current_user.get('sub'))
        log = await AttendanceService.process_web_punch(tenant_id, employee_id, data)
        await manager.broadcast({"event": "attendance_updated", "employee_id": str(employee_id)})
        return {"message": f"Successfully {data.action.replace('_', ' ')}", "log_id": str(log.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Punch failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/regularisation/{log_id}", summary="Request Attendance Correction")
async def request_regularisation(log_id: str, data: RegularisationRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        employee_id = UUID(current_user.get('sub'))
        # Using a dummy approver ID for now, in a real app this would be fetched from Employee hierarchy
        approver_id = UUID("00000000-0000-0000-0000-000000000000") 
        
        parsed_log_id = None
        try:
            parsed_log_id = UUID(log_id)
        except ValueError:
            parsed_log_id = None
            
        req = await AttendanceService.create_regularisation_request(tenant_id, employee_id, parsed_log_id, data, approver_id)
        return {"message": "Regularisation request submitted", "request_id": str(req.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/regularisations", summary="List Attendance Correction Requests")
async def get_regularisations(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_type = current_user.get('user_type')
        user_role = current_user.get('role')
        employee_id = UUID(current_user.get('sub'))
        
        is_admin = user_type in ["tenant_admin", "platform_admin", "admin"] or user_role in [
            "admin", "tenant_admin", "super_admin", "hr", "hr_admin", "hr_manager", "manager"
        ]
        
        from Models.attendance import AttendanceRegularisation, AttendanceLog
        from Models.employee import Employee, Department
        
        employees = await Employee.find(Employee.tenant_id == tenant_id).to_list()
        emp_map = {}
        for emp in employees:
            emp_map[emp.id] = emp
            emp_map[str(emp.id)] = emp
        
        departments = await Department.find(Department.tenant_id == tenant_id).to_list()
        dept_map = {dept.id: dept.name for dept in departments}
        
        colors = ["bg-blue-500", "bg-violet-500", "bg-green-500", "bg-pink-500", "bg-amber-500", "bg-teal-500", "bg-indigo-500", "bg-rose-500", "bg-orange-500", "bg-cyan-500", "bg-sky-500", "bg-fuchsia-500"]
        
        def build_avatar(emp_name, emp_id):
            avatar = "".join([part[0] for part in emp_name.split() if part])[:2].upper() if emp_name else "EE"
            color_idx = hash(str(emp_id)) % len(colors)
            return avatar, colors[color_idx]
        
        def fmt_time(dt):
            if not dt:
                return "—"
            try:
                return dt.strftime("%I:%M %p")
            except:
                return str(dt)
        
        def fmt_hours(h):
            if not h or h <= 0:
                return "—"
            hrs = int(h)
            mins = round((h - hrs) * 60)
            return f"{hrs}h {mins:02d}m" if mins > 0 else f"{hrs}h 00m"
        
        result = []
        
        # ── 1. Fetch regularisation REQUESTS ───────────────────────────────
        if not is_admin:
            reqs = await AttendanceRegularisation.find(AttendanceRegularisation.employee_id == employee_id).to_list()
        else:
            emp_ids = [emp.id for emp in employees]
            reqs = await AttendanceRegularisation.find({"employee_id": {"$in": emp_ids}}).to_list()
        
        # Track which (employee_id, date) pairs already have a regularisation request
        req_keys = set()
        for r in reqs:
            emp = emp_map.get(r.employee_id)
            emp_name = f"{emp.first_name} {emp.last_name}".strip() if emp else "Unknown Employee"
            dept_name = dept_map.get(emp.department_id) if (emp and emp.department_id) else "General"
            avatar, avatar_color = build_avatar(emp_name, r.employee_id)
            date_str = r.date.strftime("%Y-%m-%d") if isinstance(r.date, (datetime, date)) else str(r.date)
            req_keys.add((str(r.employee_id), date_str))
            result.append({
                "id": str(r.id),
                "employee": emp_name,
                "avatar": avatar,
                "avatarColor": avatar_color,
                "department": dept_name,
                "date": date_str,
                "type": "Regularisation",
                "reason": r.reason,
                "requestedIn": r.correct_check_in,
                "requestedOut": r.correct_check_out,
                "totalHours": "—",
                "notes": r.notes,
                "attachment_url": r.attachment_url,
                "status": r.status.value.capitalize() if hasattr(r.status, "value") else str(r.status).capitalize(),
                "isLog": False,
            })
        
        # ── 2. Fetch attendance logs (all employees incl. those with 9h) ──
        if is_admin:
            logs = await AttendanceLog.find({"tenant_id": tenant_id}).sort("-date").limit(500).to_list()
        else:
            logs = await AttendanceLog.find(
                AttendanceLog.employee_id == employee_id
            ).sort("-date").limit(100).to_list()
        
        for log in logs:
            emp = emp_map.get(log.employee_id)
            if not emp:
                continue
            emp_name = f"{emp.first_name} {emp.last_name}".strip()
            dept_name = dept_map.get(emp.department_id) if emp.department_id else "General"
            avatar, avatar_color = build_avatar(emp_name, log.employee_id)
            date_str = log.date.strftime("%Y-%m-%d") if isinstance(log.date, (datetime, date)) else str(log.date)
            
            # Skip if already included as a regularisation request (same emp + date)
            key = (str(log.employee_id), date_str)
            if key in req_keys:
                continue
            
            total_hours = fmt_hours(log.working_hours)
            check_in_str = fmt_time(log.check_in_at)
            check_out_str = fmt_time(log.check_out_at)
            log_status = log.status.value.capitalize() if hasattr(log.status, "value") else str(log.status).capitalize()
            
            result.append({
                "id": f"log_{str(log.id)}",
                "employee": emp_name,
                "avatar": avatar,
                "avatarColor": avatar_color,
                "department": dept_name,
                "date": date_str,
                "type": "Attendance Log",
                "reason": f"{log_status} — {total_hours}",
                "requestedIn": check_in_str,
                "requestedOut": check_out_str,
                "totalHours": total_hours,
                "notes": log.notes or "",
                "attachment_url": None,
                "status": "Completed" if (log.working_hours and log.working_hours >= 8.5) else log_status,
                "isLog": True,
                "logId": str(log.id),
            })
        
        # Sort: regularisation requests first, then logs, both by date desc
        result.sort(key=lambda x: (x["isLog"], x["date"]), reverse=True)
        return result
    except Exception as e:
        logger.error(f"Failed to fetch regularisations: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regularisation/{req_id}/approve", summary="Approve/Reject Regularisation")
async def process_regularisation(req_id: str, action: str, reason: str = None, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        approver_id = UUID(current_user.get('sub'))
        req = await AttendanceService.process_regularisation(tenant_id, UUID(req_id), approver_id, action, reason)
        await manager.broadcast({"event": "attendance_updated", "employee_id": str(req.employee_id)})
        return {"message": f"Regularisation request {action}d"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/shifts", summary="Create Shift Configuration", status_code=status.HTTP_201_CREATED)
async def create_shift(data: ShiftCreateRequest, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        shift = await AttendanceService.create_shift(tenant_id, data)
        return {"message": "Shift created successfully", "shift_id": str(shift.id)}
    except Exception as e:
        logger.error(f"Failed to create shift: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/biometric", summary="Biometric Device Webhook", status_code=status.HTTP_201_CREATED)
async def biometric_webhook(data: BiometricPunchRequest, current_user = Depends(verify_tenant_admin)): # Or verify_device_api_key in real app
    try:
        tenant_id = UUID(current_user.get('tid'))
        log = await AttendanceService.process_biometric_punch(
            tenant_id, data.device_id, data.employee_id, data.timestamp, data.punch_type
        )
        await manager.broadcast({"event": "attendance_updated", "employee_id": str(data.employee_id)})
        return {"message": "Biometric punch captured", "raw_log_id": str(log.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/qr/scan", summary="Scan QR Code to Check In/Out")
async def scan_qr_punch(data: QrScanRequest, current_user = Depends(get_current_user)):
    # Basic skeleton: In reality, you'd validate the QR token with AttendanceQrSession
    try:
        tenant_id = UUID(current_user.get('tid'))
        employee_id = UUID(current_user.get('sub'))
        # Using web punch logic as a stand-in for the scan action
        punch_req = WebPunchRequest(action="check_in", work_mode="office", location=data.location)
        log = await AttendanceService.process_web_punch(tenant_id, employee_id, punch_req)
        await manager.broadcast({"event": "attendance_updated", "employee_id": str(employee_id)})
        return {"message": "QR Scan Successful", "log_id": str(log.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/logs", summary="Fetch Attendance Logs (Reporting)")
async def get_attendance_logs(
    start_date: date, 
    end_date: date, 
    employee_id: str = None, 
    status_filter: str = None,
    current_user = Depends(get_current_user)
):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_type = current_user.get('user_type')
        user_role = current_user.get('role')
        
        # Check if administrative or management role
        is_admin = user_type in ["tenant_admin", "platform_admin", "admin"] or user_role in [
            "admin", "tenant_admin", "super_admin", "hr", "hr_admin", "hr_manager", "manager"
        ]
        
        if not is_admin:
            # Force current user to query only their own records
            emp_uuid = UUID(current_user.get('sub'))
        else:
            emp_uuid = UUID(employee_id) if employee_id and employee_id != "all" else None
            
        logs = await AttendanceService.get_attendance_logs(tenant_id, start_date, end_date, emp_uuid, status_filter)
        
        # Enrich logs with employee details
        from Models.employee import Employee, Department
        
        # Fetch all employees for this tenant
        employees = await Employee.find(Employee.tenant_id == tenant_id).to_list()
        emp_map = {str(emp.id): emp for emp in employees}
        
        # Fetch all departments
        departments = await Department.find(Department.tenant_id == tenant_id).to_list()
        dept_map = {str(dept.id): dept.name for dept in departments}
        
        # Fetch all shifts
        shifts = await Shift.find(Shift.tenant_id == tenant_id).to_list()
        shift_map = {str(s.id): s for s in shifts}
        
        # Enrich each log with employee, department, and shift details
        enriched_logs = []
        for log in logs:
            emp = emp_map.get(str(log.employee_id))
            if emp:
                log_dict = {
                    "id": str(log.id),
                    "tenant_id": str(log.tenant_id),
                    "employee_id": str(log.employee_id),
                    "employee_name": f"{emp.first_name} {emp.last_name}".strip(),
                    "employee_number": emp.employee_number,
                    "department": dept_map.get(str(emp.department_id)) if emp.department_id else "Not Assigned",
                    "department_id": str(emp.department_id) if emp.department_id else None,
                    "date": log.date.isoformat() if log.date else None,
                    "shift_id": str(log.shift_id) if log.shift_id else None,
                    "shift_name": None,
                    "shift_start_time": None,
                    "shift_end_time": None,
                    "check_in_at": log.check_in_at.isoformat() if log.check_in_at else None,
                    "check_out_at": log.check_out_at.isoformat() if log.check_out_at else None,
                    "source": log.source.value if hasattr(log.source, 'value') else str(log.source),
                    "check_in_location_json": log.check_in_location_json,
                    "check_out_location_json": log.check_out_location_json,
                    "is_wfh": log.is_wfh,
                    "working_hours": float(log.working_hours) if log.working_hours else 0.0,
                    "break_duration_mins": log.break_duration_mins,
                    "overtime_hours": float(log.overtime_hours) if log.overtime_hours else 0.0,
                    "status": log.status.value if hasattr(log.status, 'value') else str(log.status),
                    "is_regularised": log.is_regularised,
                    "regularised_by": str(log.regularised_by) if log.regularised_by else None,
                    "regularised_at": log.regularised_at.isoformat() if log.regularised_at else None,
                    "notes": log.notes,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "updated_at": log.updated_at.isoformat() if log.updated_at else None,
                }
                
                # Add shift details if shift_id exists
                if log.shift_id:
                    shift = shift_map.get(str(log.shift_id))
                    if shift:
                        log_dict["shift_name"] = shift.name
                        log_dict["shift_start_time"] = shift.start_time
                        log_dict["shift_end_time"] = shift.end_time
                
                enriched_logs.append(log_dict)
        
        return enriched_logs
    except Exception as e:
        logger.error(f"Failed to fetch attendance logs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/logs/{log_id}", summary="Admin Override Attendance Record")
async def admin_update_attendance_log(
    log_id: str, 
    data: AttendanceAdminUpdateRequest, 
    current_user = Depends(verify_tenant_admin)
):
    """Allows HR/Admins to directly modify an attendance record, bypassing the regularisation workflow."""
    try:
        tenant_id = UUID(current_user.get('tid'))
        admin_id = UUID(current_user.get('sub'))
        log = await AttendanceService.admin_update_log(tenant_id, UUID(log_id), data, admin_id)
        await manager.broadcast({"event": "attendance_updated", "employee_id": str(log.employee_id)})
        return {"message": "Attendance record updated successfully via admin override", "log_id": str(log.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to admin update attendance log: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/shifts", summary="Fetch Shift Configurations")
async def get_shifts(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        shifts = await AttendanceService.get_shifts(tenant_id)
        return [
            {
                "id": str(s.id),
                "tenant_id": str(s.tenant_id),
                "name": s.name,
                "shift_type": s.shift_type,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "break_duration_mins": s.break_duration_mins,
                "is_break_paid": s.is_break_paid,
                "overtime_after_hrs": s.overtime_after_hrs,
                "ot_rate_multiplier": s.ot_rate_multiplier,
                "working_days": s.working_days,
                "grace_period_mins": s.grace_period_mins,
                "applicable_locations": [str(loc) for loc in (s.applicable_locations or [])],
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in shifts
        ]
    except Exception as e:
        logger.error(f"Failed to fetch shifts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.put("/shifts/{shift_id}", summary="Update Shift Configuration")
async def update_shift(shift_id: str, data: ShiftCreateRequest, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        shift = await AttendanceService.update_shift(tenant_id, UUID(shift_id), data)
        return {
            "message": "Shift updated successfully",
            "shift": {
                "id": str(shift.id),
                "name": shift.name,
                "shift_type": shift.shift_type,
                "start_time": shift.start_time,
                "end_time": shift.end_time,
                "break_duration_mins": shift.break_duration_mins,
                "is_break_paid": shift.is_break_paid,
                "overtime_after_hrs": shift.overtime_after_hrs,
                "ot_rate_multiplier": shift.ot_rate_multiplier,
                "working_days": shift.working_days,
                "grace_period_mins": shift.grace_period_mins,
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update shift: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.delete("/shifts/{shift_id}", summary="Delete Shift Configuration")
async def delete_shift(shift_id: str, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        await AttendanceService.delete_shift(tenant_id, UUID(shift_id))
        return {"message": "Shift deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete shift: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/shifts/assign", summary="Directly Map Shift Policy to Employees")
async def assign_shift(data: ShiftAssignRequest, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        admin_id = UUID(current_user.get('sub'))
        result = await AttendanceService.assign_shift(tenant_id, data, admin_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to assign shift: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/policies", summary="Fetch Global Attendance Policies")
async def get_global_policy(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        policy = await AttendanceService.get_global_policy(tenant_id)
        return policy
    except Exception as e:
        logger.error(f"Failed to fetch global policy: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.put("/policies", summary="Update Global Attendance Policies")
async def update_global_policy(data: GlobalPolicyUpdateRequest, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        policy = await AttendanceService.update_global_policy(tenant_id, data)
        return {"message": "Global policies updated successfully", "policy": policy}
    except Exception as e:
        logger.error(f"Failed to update global policy: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/roster", summary="Fetch Weekly Roster Grid Sheet")
async def get_weekly_roster(week_start: date, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        roster = await AttendanceService.get_weekly_roster(tenant_id, week_start)
        return roster
    except Exception as e:
        logger.error(f"Failed to fetch weekly roster: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.post("/roster/generate", summary="Run Weekly Auto-Roster Engine")
async def generate_weekly_roster(data: RosterGenerateRequest, current_user = Depends(verify_tenant_admin)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        admin_id = UUID(current_user.get('sub'))
        result = await AttendanceService.generate_weekly_roster(tenant_id, data.week_start, admin_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate auto roster: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")
@router.get("/reports")
async def get_reports(current_user = Depends(get_current_user)):

    reports = [
        {
            "id": "daily_attendance",
            "title": "Daily Attendance Report",
            "desc": "All employees — Shift, Check-in, Check-out, Hours Worked, OT Hours",
            "icon": "CalendarDays",
            "format": "CSV",
            "color": "from-blue-500 to-indigo-600",
            "badge": "Daily",
            "category": "Operational Reports",
            "export_type": "csv",

            # Existing Dynamic API
            "data_api": "/api/v1/attendance/logs",

            # frontend preview route
            "preview_api": "/api/v1/reports/preview/daily-attendance",

            # export route
            "export_api": "/api/v1/reports/export/daily-attendance",

            "fields": ["Employee", "Dept", "Shift", "Check-In", "Check-Out", "Hours", "OT Hrs", "Status"],
            "filters": [
                "start_date",
                "end_date",
                "employee_id",
                "status_filter"
            ]
        },

        {
            "id": "late_arrivals",
            "title": "Late Arrivals Report",
            "desc": "Count, dates, minutes late, Bradford Factor score",
            "icon": "TrendingDown",
            "format": "CSV",
            "color": "from-rose-500 to-pink-600",
            "badge": "Compliance",
            "category": "Compliance Reports",
            "export_type": "csv",

            "data_api": "/api/v1/attendance/logs",
            "preview_api": "/api/v1/reports/preview/late-arrivals",
            "export_api": "/api/v1/reports/export/late-arrivals",

            "fields": ["Employee", "Date", "Scheduled", "Actual In", "Mins Late", "Bradford Pts"],
            "filters": [
                "start_date",
                "end_date",
                "employee_id"
            ]
        },
        {
            "id": "monthly",
            "title": "Monthly Attendance Summary",
            "desc": "One row per employee, columns per day. P/A/L/H/WH/HD colour-coded",
            "icon": "FileSpreadsheet",
            "format": "XLSX",
            "color": "from-violet-500 to-purple-600",
            "badge": "Monthly",
            "category": "Operational Reports",
            "export_type": "xlsx",
            "data_api": "/api/v1/attendance/logs",
            "preview_api": "/api/v1/reports/preview/monthly-attendance",
            "export_api": "/api/v1/reports/export/monthly-attendance",
            "fields": ["Employee", "Day 1", "Day 2", "...", "Day 31", "Total P", "Total A"],
            "filters": ["month", "department", "employee_id"]
        },
        {
            "id": "absence",
            "title": "Absence Report",
            "desc": "Unexplained absences + approved leave, Bradford Factor (UK)",
            "icon": "AlertCircle",
            "format": "CSV",
            "color": "from-slate-600 to-slate-800",
            "badge": "HR",
            "category": "Operational Reports",
            "export_type": "csv",
            "data_api": "/api/v1/attendance/logs",
            "preview_api": "/api/v1/reports/preview/absence",
            "export_api": "/api/v1/reports/export/absence",
            "fields": ["Employee", "Date", "Type", "Leave Code", "Approved", "Bradford Score"],
            "filters": ["start_date", "end_date", "department", "employee_id", "type"]
        }
    ]

    return {
        "success": True,
        "data": reports
    }

@router.get("/reports/stats")
async def get_reports_stats(current_user = Depends(get_current_user)):
    stats = [
        { "label": "Reports Available", "value": "4", "color": "bg-blue-600" },
        { "label": "CSV Exports", "value": "3", "color": "bg-emerald-600" },
        { "label": "PDF Reports", "value": "0", "color": "bg-violet-600" },
        { "label": "Excel Exports", "value": "1", "color": "bg-amber-500" },
    ]
    return {
        "success": True,
        "data": stats
    }

@router.get("/reports/groups")
async def get_reports_groups(current_user = Depends(get_current_user)):
    groups = [
        { 
            "label": "🌍 Operational Reports", 
            "reports": ["daily_attendance", "monthly", "absence"] 
        },
        { 
            "label": "📋 Statutory & Compliance Reports", 
            "reports": ["late_arrivals"] 
        },
    ]
    return {
        "success": True,
        "data": groups
    }

@router.get("/compliance", summary="Get Compliance Rules by Region")
async def get_compliance_rules(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get("tid"))

        data = await AttendanceService.get_compliance_rules(tenant_id)

        return {
            "status": "success",
            "data": data
        }

    except Exception as e:
        logger.error(f"Compliance fetch failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/compliance/{region}")
async def get_compliance_by_region(region: str, current_user = Depends(get_current_user)):
    try:
        data = await AttendanceService.get_compliance_rules(UUID(current_user.get("tid")))

        filtered = [r for r in data if r["region"].lower() == region.lower()]

        if not filtered:
            raise HTTPException(status_code=404, detail="Region not found")

        return filtered[0]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Compatibility routes for frontend (handles /api/compliance and /api/attendance/compliance)
@compat_router.get("/api/compliance", summary="Get Compliance Rules by Region (Compatibility)", tags=["Attendance"])
async def get_compliance_rules_compat1(current_user = Depends(get_current_user)):
    return await get_compliance_rules(current_user)

@compat_router.get("/api/compliance/{region}", tags=["Attendance"])
async def get_compliance_by_region_compat1(region: str, current_user = Depends(get_current_user)):
    return await get_compliance_by_region(region, current_user)

@compat_router.get("/api/attendance/compliance", summary="Get Compliance Rules by Region (Compatibility)", tags=["Attendance"])
async def get_compliance_rules_compat2(current_user = Depends(get_current_user)):
    return await get_compliance_rules(current_user)

@compat_router.get("/api/attendance/compliance/{region}", tags=["Attendance"])
async def get_compliance_by_region_compat2(region: str, current_user = Depends(get_current_user)):
    return await get_compliance_by_region(region, current_user)