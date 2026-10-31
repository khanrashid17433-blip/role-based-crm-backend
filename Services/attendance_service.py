from typing import Dict, Any, List, Optional
from datetime import datetime, date, timezone, time, timedelta
import logging
from uuid import UUID, uuid4

from Models.attendance import (
    AttendanceRawLog, AttendanceLog, AttendanceGeoFence, AttendanceRegularisation,
    Shift, PunchType, AttendanceSource, AttendanceStatus, RegularisationStatus,
    GlobalAttendancePolicy, RosterDraft, RosterAssignment, ShiftType
)
from Schema.attendance import (
    WebPunchRequest, RegularisationRequest, ShiftCreateRequest, AttendanceAdminUpdateRequest,
    GlobalPolicyUpdateRequest, ShiftAssignRequest, RosterGenerateRequest
)

logger = logging.getLogger(__name__)


def _ensure_utc(dt: datetime) -> datetime:
    """Guarantee a datetime is timezone-aware (UTC).

    MongoDB / Beanie sometimes returns naive datetimes even when the stored
    value is UTC.  This helper attaches tzinfo=UTC when it is missing so
    arithmetic such as (aware - naive) never raises a TypeError.
    """
    if dt is None:
        return dt
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class AttendanceService:
    
    @staticmethod
    async def process_web_punch(tenant_id: UUID, employee_id: UUID, data: WebPunchRequest) -> AttendanceLog:
        """Process manual web punch from browser/mobile PWA"""
        now = datetime.now(timezone.utc)
        today_date = now.date()
        today = datetime.combine(today_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        
        # Log to raw tables first
        raw_log = AttendanceRawLog(
            tenant_id=tenant_id,
            employee_id=employee_id,
            raw_timestamp=now,
            punch_type=PunchType(data.action),
            source=AttendanceSource.web,
            raw_payload_json={"work_mode": data.work_mode, "location": data.location.model_dump() if data.location else None, "notes": data.notes},
            processed=True,
            processed_at=now
        )
        await raw_log.insert()
        
        # Geo-fence validation logic (simplified for now)
        if data.work_mode == "field" and not data.location:
            raise ValueError("GPS location is required for field work mode")
            
        # Find or create today's log
        log = await AttendanceLog.find_one(
            AttendanceLog.tenant_id == tenant_id,
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.date == today
        )
        
        if not log:
            log = AttendanceLog(
                tenant_id=tenant_id,
                employee_id=employee_id,
                date=today,
                source=AttendanceSource.web,
                is_wfh=(data.work_mode == "wfh"),
                notes=data.notes
            )
            
        if data.action == "check_in":
            if log.check_in_at:
                raise ValueError("Already checked in for today")
            log.check_in_at = now
            if data.location:
                log.check_in_location_json = data.location.model_dump()
                
        elif data.action == "check_out":
            if not log.check_in_at:
                raise ValueError("Cannot check out without checking in")
            log.check_out_at = now
            if data.location:
                log.check_out_location_json = data.location.model_dump()

            # Normalize both sides to UTC-aware before subtracting
            check_in_utc  = _ensure_utc(log.check_in_at)
            check_out_utc = _ensure_utc(log.check_out_at)
            duration = (check_out_utc - check_in_utc).total_seconds() / 3600.0
            log.working_hours = round(duration, 2)

            # Enforce 9-hour threshold for Present status
            if log.working_hours >= 9.0:
                log.status = AttendanceStatus.present
            else:
                log.status = AttendanceStatus.absent

        await log.save()
        return log

    @staticmethod
    async def create_regularisation_request(tenant_id: UUID, employee_id: UUID, log_id: Optional[UUID], data: RegularisationRequest, approver_id: UUID) -> AttendanceRegularisation:
        """Employee requests attendance correction"""
        log = None
        if log_id and str(log_id) != "00000000-0000-0000-0000-000000000000":
            log = await AttendanceLog.find_one(
                AttendanceLog.id == log_id,
                AttendanceLog.tenant_id == tenant_id
            )
            
        if not log:
            log_date = datetime.combine(data.date, datetime.min.time()).replace(tzinfo=timezone.utc)
            log = await AttendanceLog.find_one(
                AttendanceLog.tenant_id == tenant_id,
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.date == log_date
            )
            if not log:
                log = AttendanceLog(
                    tenant_id=tenant_id,
                    employee_id=employee_id,
                    date=log_date,
                    source=AttendanceSource.web,
                    status=AttendanceStatus.absent
                )
                await log.insert()
            
        if log.is_regularised:
            raise ValueError("This day is already regularised")
            
        req = AttendanceRegularisation(
            tenant_id=tenant_id,
            employee_id=employee_id,
            attendance_log_id=log.id,
            date=datetime.combine(data.date, datetime.min.time()).replace(tzinfo=timezone.utc),
            reason=data.reason,
            correct_check_in=data.correct_check_in,
            correct_check_out=data.correct_check_out,
            notes=data.notes,
            attachment_url=data.attachment_url,
            approver_id=approver_id
        )
        await req.insert()
        return req

    @staticmethod
    async def process_regularisation(tenant_id: UUID, req_id: UUID, approver_id: UUID, action: str, reason: Optional[str] = None) -> AttendanceRegularisation:
        """Manager approves or rejects regularisation"""
        req = await AttendanceRegularisation.find_one(AttendanceRegularisation.id == req_id)
        if not req:
            raise ValueError("Regularisation request not found")
            
        log = await AttendanceLog.find_one(
            AttendanceLog.id == req.attendance_log_id,
            AttendanceLog.tenant_id == tenant_id
        )
        if not log:
            raise ValueError("Related attendance log not found or unauthorized")
            
        if req.approver_id != approver_id:
            raise ValueError("You are not authorized to approve this request")
            
        if req.status != RegularisationStatus.pending:
            raise ValueError("Request is already processed")
            
        if action == "approve":
            req.status = RegularisationStatus.approved
            req.approved_at = datetime.now(timezone.utc)

            # Helper to parse time string (e.g. "09:00:00" or "09:00") to datetime.time
            def parse_time(time_str):
                if isinstance(time_str, time):
                    return time_str
                for fmt in ("%H:%M:%S", "%H:%M"):
                    try:
                        return datetime.strptime(time_str, fmt).time()
                    except ValueError:
                        continue
                raise ValueError(f"Invalid time format: {time_str}")

            # Update original log
            check_in  = datetime.combine(req.date, parse_time(req.correct_check_in)).replace(tzinfo=timezone.utc)
            check_out = datetime.combine(req.date, parse_time(req.correct_check_out)).replace(tzinfo=timezone.utc)
            log.check_in_at  = check_in
            log.check_out_at = check_out
            log.is_regularised  = True
            log.regularised_by  = approver_id
            log.regularised_at  = datetime.now(timezone.utc)

            # Recalculate working hours
            duration = (_ensure_utc(log.check_out_at) - _ensure_utc(log.check_in_at)).total_seconds() / 3600.0
            log.working_hours = round(duration, 2)

            # Enforce 9-hour threshold for Present status
            if log.working_hours >= 9.0:
                log.status = AttendanceStatus.present
            else:
                log.status = AttendanceStatus.absent

            await log.save()
                
        elif action == "reject":
            req.status = RegularisationStatus.rejected
            req.rejection_reason = reason
        else:
            raise ValueError("Invalid action")
            
        await req.save()
        return req

    @staticmethod
    async def create_shift(tenant_id: UUID, data: ShiftCreateRequest) -> Shift:
        """Create a new shift configuration"""
        shift = Shift(
            tenant_id=tenant_id,
            name=data.name,
            shift_type=data.shift_type,
            start_time=data.start_time,
            end_time=data.end_time,
            break_duration_mins=data.break_duration_mins,
            is_break_paid=data.is_break_paid,
            overtime_after_hrs=data.overtime_after_hrs,
            ot_rate_multiplier=data.ot_rate_multiplier,
            working_days=data.working_days,
            grace_period_mins=data.grace_period_mins,
            applicable_locations=data.applicable_locations
        )
        await shift.insert()
        return shift

    @staticmethod
    async def get_today_summary(tenant_id: UUID, employee_id: UUID) -> Dict[str, Any]:
        """Get today's summary for the employee dashboard"""
        today_date = datetime.now(timezone.utc).date()
        today = datetime.combine(today_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        log = await AttendanceLog.find_one(
            AttendanceLog.tenant_id == tenant_id,
            AttendanceLog.employee_id == employee_id,
            AttendanceLog.date == today
        )
        
        if not log:
            return {
                "status": "Not Checked In",
                "check_in_time": None,
                "hours_so_far": 0.0,
                "shift": "Default Shift"
            }
            
        hours_so_far = log.working_hours
        if log.check_in_at and not log.check_out_at:
            # Calculate running total — normalize check_in_at to UTC-aware
            now = datetime.now(timezone.utc)
            duration = (now - _ensure_utc(log.check_in_at)).total_seconds() / 3600.0
            hours_so_far = round(duration, 2)
            
        return {
            "status": "Clocked In" if not log.check_out_at else "Clocked Out",
            "check_in_time": _ensure_utc(log.check_in_at).isoformat() if log.check_in_at else None,
            "check_out_time": _ensure_utc(log.check_out_at).isoformat() if log.check_out_at else None,
            "hours_so_far": hours_so_far,
            "is_wfh": log.is_wfh
        }

    @staticmethod
    async def process_biometric_punch(tenant_id: UUID, device_id: str, employee_id: str, timestamp: datetime, punch_type: str) -> AttendanceRawLog:
        """Process incoming webhook from ZKTeco/eSSL devices"""
        
        # In a real system, employee_id from device is often a string mapping (e.g. '1001')
        # You would look up the actual UUID using that mapping. For now we assume UUID.
        try:
            emp_uuid = UUID(employee_id)
        except:
            raise ValueError("Invalid employee ID format from device")
            
        # Log to raw tables first
        raw_log = AttendanceRawLog(
            tenant_id=tenant_id,
            employee_id=emp_uuid,
            raw_timestamp=timestamp,
            source=AttendanceSource.biometric,
            raw_payload_json={"device_id": device_id, "punch_type": punch_type},
            processed=False # Handled by a background worker later matching IN/OUT pairs
        )
        await raw_log.insert()
        return raw_log
        
    @staticmethod
    async def get_attendance_logs(
        tenant_id: UUID, 
        start_date: date, 
        end_date: date, 
        employee_id: Optional[UUID] = None,
        status: Optional[str] = None
    ) -> List[AttendanceLog]:
        """Fetch attendance reports for payroll/HR"""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())
        
        filters = [
            AttendanceLog.tenant_id == tenant_id,
            AttendanceLog.date >= start_dt,
            AttendanceLog.date <= end_dt
        ]
        
        if employee_id:
            filters.append(AttendanceLog.employee_id == employee_id)
        if status:
            filters.append(AttendanceLog.status == status)
            
        return await AttendanceLog.find({"$and": filters}).to_list()

    @staticmethod
    async def admin_update_log(tenant_id: UUID, log_id: UUID, data: AttendanceAdminUpdateRequest, admin_id: UUID) -> AttendanceLog:
        """HR/Admin direct override of an attendance record"""
        log = await AttendanceLog.find_one(
            AttendanceLog.id == log_id,
            AttendanceLog.tenant_id == tenant_id
        )
        if not log:
            # If log not found, log_id is treated as employee_id, and we create a new log on the fly!
            log_date = datetime.now(timezone.utc).date()
            if data.check_in_time is not None:
                log_date = data.check_in_time.date()
            elif data.check_out_time is not None:
                log_date = data.check_out_time.date()
                
            today_start = datetime.combine(log_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            
            # Double check to prevent duplication
            log = await AttendanceLog.find_one(
                AttendanceLog.tenant_id == tenant_id,
                AttendanceLog.employee_id == log_id,
                AttendanceLog.date == today_start
            )
            
            if not log:
                log = AttendanceLog(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    employee_id=log_id,
                    date=today_start,
                    source=AttendanceSource.manual,
                    status=AttendanceStatus.present
                )
                await log.insert()

        # Apply updates
        if data.check_in_time is not None:
            log.check_in_at = data.check_in_time.replace(tzinfo=timezone.utc)
        if data.check_out_time is not None:
            log.check_out_at = data.check_out_time.replace(tzinfo=timezone.utc)
        
        if data.status is not None:
            log.status = data.status
        if data.is_wfh is not None:
            log.is_wfh = data.is_wfh
        if data.source is not None:
            log.source = data.source
            
        # Recalculate working hours or use provided value
        if data.working_hours is not None:
            log.working_hours = data.working_hours
        elif log.check_in_at and log.check_out_at:
            duration = (_ensure_utc(log.check_out_at) - _ensure_utc(log.check_in_at)).total_seconds() / 3600.0
            log.working_hours = round(duration, 2)

        # Enforce 9-hour threshold for Present status if checked out and not explicitly set by admin
        if data.status is None and log.check_out_at is not None:
            if log.working_hours >= 9.0:
                log.status = AttendanceStatus.present
            else:
                log.status = AttendanceStatus.absent

        # Track that this was an admin override
        log.is_regularised = True
        log.regularised_by = admin_id
        log.regularised_at = datetime.now(timezone.utc)
        
        # Append to notes instead of overwriting
        existing_notes = log.notes or ""
        log.notes = f"{existing_notes} | Admin Override: {data.admin_notes}".strip(" |")

        await log.save()
        return log

    @staticmethod
    async def get_shifts(tenant_id: UUID) -> List[Shift]:
        """Fetch all configured shifts for a tenant"""
        return await Shift.find(Shift.tenant_id == tenant_id).to_list()

    @staticmethod
    async def update_shift(tenant_id: UUID, shift_id: UUID, data: ShiftCreateRequest) -> Shift:
        """Update a shift configuration"""
        shift = await Shift.find_one(Shift.id == shift_id, Shift.tenant_id == tenant_id)
        if not shift:
            raise ValueError("Shift configuration not found")
        
        shift.name = data.name
        shift.shift_type = data.shift_type
        shift.start_time = data.start_time
        shift.end_time = data.end_time
        shift.break_duration_mins = data.break_duration_mins
        shift.is_break_paid = data.is_break_paid
        shift.overtime_after_hrs = data.overtime_after_hrs
        shift.ot_rate_multiplier = data.ot_rate_multiplier
        shift.working_days = data.working_days
        shift.grace_period_mins = data.grace_period_mins
        shift.applicable_locations = data.applicable_locations
        shift.updated_at = datetime.utcnow()
        
        await shift.save()
        return shift

    @staticmethod
    async def delete_shift(tenant_id: UUID, shift_id: UUID) -> bool:
        """Delete a shift configuration"""
        shift = await Shift.find_one(Shift.id == shift_id, Shift.tenant_id == tenant_id)
        if not shift:
            raise ValueError("Shift configuration not found")
        await shift.delete()
        return True

    @staticmethod
    async def get_global_policy(tenant_id: UUID) -> GlobalAttendancePolicy:
        """Fetch tenant's global attendance policies, creating default one if not exists"""
        policy = await GlobalAttendancePolicy.find_one(GlobalAttendancePolicy.tenant_id == tenant_id)
        if not policy:
            policy = GlobalAttendancePolicy(
                tenant_id=tenant_id,
                weekly_offs=[5, 6], # Default: Sat, Sun
                late_marking_rule="3 Lates = 1 Half Day",
                grace_period_mins=15,
                ot_multiplier=1.5
            )
            await policy.insert()
        return policy

    @staticmethod
    async def update_global_policy(tenant_id: UUID, data: GlobalPolicyUpdateRequest) -> GlobalAttendancePolicy:
        """Update global attendance policy"""
        policy = await AttendanceService.get_global_policy(tenant_id)
        policy.weekly_offs = data.weekly_offs
        policy.late_marking_rule = data.late_marking_rule
        policy.grace_period_mins = data.grace_period_mins
        policy.ot_multiplier = data.ot_multiplier
        policy.updated_at = datetime.utcnow()
        await policy.save()
        return policy

    @staticmethod
    async def assign_shift(tenant_id: UUID, data: ShiftAssignRequest, admin_id: UUID) -> dict:
        """Assign shift directly to selected employees with overlap conflict checks"""
        from Models.employee import Employee
        
        # 1. Update Employee default shift fields in custom_fields_json
        employees = await Employee.find({"_id": {"$in": data.employee_ids}, "tenant_id": tenant_id}).to_list()
        for emp in employees:
            if not emp.custom_fields_json:
                emp.custom_fields_json = {}
            emp.custom_fields_json["default_shift_id"] = str(data.shift_id)
            await emp.save()

        # 2. Add Roster Assignments over the date range
        shift_id = data.shift_id
        start_date = data.start_date
        end_date = data.end_date
        
        current_date = start_date
        conflicts = []
        
        # Fetch shift configuration for working days definition
        shift_config = await Shift.find_one(Shift.id == shift_id, Shift.tenant_id == tenant_id)
        working_days = shift_config.working_days if shift_config else [0,1,2,3,4] # Monday-Friday
        
        # Ensure a Roster Draft exists for this week
        roster_draft = await RosterDraft.find_one(
            RosterDraft.tenant_id == tenant_id,
            RosterDraft.week_start == datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        )
        if not roster_draft:
            roster_draft = RosterDraft(
                tenant_id=tenant_id,
                week_start=datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc),
                created_by=admin_id
            )
            await roster_draft.insert()
            
        while current_date <= end_date:
            day_start = datetime.combine(current_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            day_of_week = current_date.weekday() # 0=Monday, 6=Sunday
            is_weekend = day_of_week not in working_days
            
            for emp_id in data.employee_ids:
                # Conflict validation check
                existing = await RosterAssignment.find_one(
                    RosterAssignment.tenant_id == tenant_id,
                    RosterAssignment.employee_id == emp_id,
                    RosterAssignment.date == day_start
                )
                if existing:
                    conflicts.append({
                        "employee_id": str(emp_id),
                        "date": current_date.isoformat(),
                        "existing_shift_id": str(existing.shift_id)
                    })
                    existing.shift_id = shift_id
                    existing.is_holiday = is_weekend
                    existing.notes = "Weekend OFF" if is_weekend else None
                    await existing.save()
                else:
                    assignment = RosterAssignment(
                        tenant_id=tenant_id,
                        roster_id=roster_draft.id,
                        employee_id=emp_id,
                        date=day_start,
                        shift_id=shift_id,
                        is_holiday=is_weekend,
                        notes="Weekend OFF" if is_weekend else None
                    )
                    await assignment.insert()
                    
            current_date += timedelta(days=1)
            
        return {
            "message": "Shift policy mapped successfully",
            "employees_assigned": len(employees),
            "conflicts_resolved": len(conflicts),
            "conflicts_log": conflicts
        }

    @staticmethod
    async def generate_weekly_roster(tenant_id: UUID, week_start: date, admin_id: UUID) -> dict:
        """Batch generate weekly Roster Draft and Assignments for active employees"""
        from Models.employee import Employee
        
        start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
        
        employees = await Employee.find(
            Employee.tenant_id == tenant_id,
            Employee.employment_status == "active"
        ).to_list()
        
        shifts = await AttendanceService.get_shifts(tenant_id)
        if not shifts:
            # Seed default shift if none exists
            default_shift = Shift(
                tenant_id=tenant_id,
                name="General Shift",
                shift_type=ShiftType.fixed,
                start_time="09:00",
                end_time="18:00",
                break_duration_mins=60,
                grace_period_mins=15,
                working_days=[0,1,2,3,4] # Mon-Fri
            )
            await default_shift.insert()
            shifts = [default_shift]
            
        default_shift = shifts[0]
        
        # Clear existing drafts/assignments for this week start to avoid duplicates
        existing_drafts = await RosterDraft.find(RosterDraft.tenant_id == tenant_id, RosterDraft.week_start == start_dt).to_list()
        for draft in existing_drafts:
            await RosterAssignment.find(RosterAssignment.roster_id == draft.id).delete()
            await draft.delete()
            
        roster_draft = RosterDraft(
            tenant_id=tenant_id,
            week_start=start_dt,
            created_by=admin_id
        )
        await roster_draft.insert()
        
        assignments_count = 0
        for emp in employees:
            emp_shift_id = default_shift.id
            cf_shift = emp.custom_fields_json.get("default_shift_id") if emp.custom_fields_json else None
            if cf_shift:
                try:
                    emp_shift_uuid = UUID(cf_shift)
                    shift_exists = next((s for s in shifts if s.id == emp_shift_uuid), None)
                    if shift_exists:
                        emp_shift_id = emp_shift_uuid
                except:
                    pass
            
            shift_config = next((s for s in shifts if s.id == emp_shift_id), default_shift)
            working_days = shift_config.working_days
            
            for offset in range(7):
                day_date = week_start + timedelta(days=offset)
                day_start = datetime.combine(day_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                day_of_week = day_date.weekday()
                is_weekend = day_of_week not in working_days
                
                assignment = RosterAssignment(
                    tenant_id=tenant_id,
                    roster_id=roster_draft.id,
                    employee_id=emp.id,
                    date=day_start,
                    shift_id=emp_shift_id,
                    is_holiday=is_weekend,
                    notes="Weekend OFF" if is_weekend else None
                )
                await assignment.insert()
                assignments_count += 1
                
        return {
            "message": "Auto-Roster generated successfully!",
            "week_start": week_start.isoformat(),
            "roster_id": str(roster_draft.id),
            "staff_count": len(employees),
            "assignments_seeded": assignments_count
        }

    @staticmethod
    async def get_weekly_roster(tenant_id: UUID, week_start: date) -> dict:
        """Fetch weekly Roster Assignments sheet merged with employee profiles"""
        from Models.employee import Employee, Department
        
        start_dt = datetime.combine(week_start, datetime.min.time()).replace(tzinfo=timezone.utc)
        
        draft = await RosterDraft.find_one(RosterDraft.tenant_id == tenant_id, RosterDraft.week_start == start_dt)
        if not draft:
            return {"week_start": week_start.isoformat(), "draft_id": None, "assignments": []}
            
        assignments = await RosterAssignment.find(
            RosterAssignment.tenant_id == tenant_id,
            RosterAssignment.roster_id == draft.id
        ).to_list()
        
        employees = await Employee.find(
            Employee.tenant_id == tenant_id,
            Employee.employment_status == "active"
        ).to_list()
        
        # Fetch all departments for this tenant to map names dynamically
        departments = await Department.find(Department.tenant_id == tenant_id).to_list()
        dept_map = {dept.id: dept.name for dept in departments}
        
        roster_list = []
        for emp in employees:
            emp_assigns = [a for a in assignments if a.employee_id == emp.id]
            
            days_schedule = {}
            for offset in range(7):
                day_date = week_start + timedelta(days=offset)
                day_start = datetime.combine(day_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                
                matched = next((a for a in emp_assigns if a.date == day_start), None)
                if matched:
                    days_schedule[offset] = {
                        "assignment_id": str(matched.id),
                        "shift_id": str(matched.shift_id),
                        "is_holiday": matched.is_holiday,
                        "is_leave": matched.is_leave,
                        "notes": matched.notes
                    }
                else:
                    days_schedule[offset] = None
                    
            emp_dept = dept_map.get(emp.department_id, "General") if emp.department_id else "General"
            
            roster_list.append({
                "employee_id": str(emp.id),
                "name": f"{emp.first_name} {emp.last_name}".strip(),
                "department": emp_dept,
                "schedule": days_schedule
            })
            
        return {
            "week_start": week_start.isoformat(),
            "draft_id": str(draft.id),
            "assignments": roster_list
        }

    @staticmethod
    async def get_compliance_rules(tenant_id: UUID) -> List[dict]:
        """Get compliance rules by region for attendance management"""
        # This is a static dataset of common compliance rules by region
        # In production, this could be stored in database and managed by admin
        
        compliance_data = [
            {
                "region": "India",
                "max_working_hours_per_day": 9,
                "max_working_hours_per_week": 48,
                "min_rest_hours_between_shifts": 12,
                "overtime_threshold_hours": 9,
                "weekly_off_days": 1,
                "annual_leave_entitlement": 21,
                "sick_leave_entitlement": 12,
                "maternity_leave_days": 182,
                "paternity_leave_days": 15,
                "grace_period_mins": 15,
                "late_arrival_threshold_mins": 30,
                "regulatory_body": "Ministry of Labour & Employment",
                "compliance_notes": "Factories Act 1948, Shops and Establishments Act"
            },
            {
                "region": "United Kingdom",
                "max_working_hours_per_day": 8,
                "max_working_hours_per_week": 48,
                "min_rest_hours_between_shifts": 11,
                "overtime_threshold_hours": 8,
                "weekly_off_days": 1,
                "annual_leave_entitlement": 28,
                "sick_leave_entitlement": 28,
                "maternity_leave_days": 365,
                "paternity_leave_days": 14,
                "grace_period_mins": 10,
                "late_arrival_threshold_mins": 15,
                "regulatory_body": "HSE (Health and Safety Executive)",
                "compliance_notes": "Working Time Regulations 1998"
            },
            {
                "region": "United States",
                "max_working_hours_per_day": 8,
                "max_working_hours_per_week": 40,
                "min_rest_hours_between_shifts": 8,
                "overtime_threshold_hours": 8,
                "weekly_off_days": 2,
                "annual_leave_entitlement": 10,
                "sick_leave_entitlement": 10,
                "maternity_leave_days": 84,
                "paternity_leave_days": 0,
                "grace_period_mins": 5,
                "late_arrival_threshold_mins": 10,
                "regulatory_body": "Department of Labor",
                "compliance_notes": "Fair Labor Standards Act (FLSA)"
            },
            {
                "region": "European Union",
                "max_working_hours_per_day": 8,
                "max_working_hours_per_week": 48,
                "min_rest_hours_between_shifts": 11,
                "overtime_threshold_hours": 8,
                "weekly_off_days": 1,
                "annual_leave_entitlement": 20,
                "sick_leave_entitlement": 90,
                "maternity_leave_days": 98,
                "paternity_leave_days": 10,
                "grace_period_mins": 10,
                "late_arrival_threshold_mins": 15,
                "regulatory_body": "European Commission",
                "compliance_notes": "Working Time Directive 2003/88/EC"
            },
            {
                "region": "Australia",
                "max_working_hours_per_day": 8,
                "max_working_hours_per_week": 38,
                "min_rest_hours_between_shifts": 10,
                "overtime_threshold_hours": 8,
                "weekly_off_days": 2,
                "annual_leave_entitlement": 20,
                "sick_leave_entitlement": 10,
                "maternity_leave_days": 365,
                "paternity_leave_days": 14,
                "grace_period_mins": 10,
                "late_arrival_threshold_mins": 15,
                "regulatory_body": "Fair Work Commission",
                "compliance_notes": "Fair Work Act 2009"
            },
            {
                "region": "Singapore",
                "max_working_hours_per_day": 8,
                "max_working_hours_per_week": 44,
                "min_rest_hours_between_shifts": 8,
                "overtime_threshold_hours": 8,
                "weekly_off_days": 1,
                "annual_leave_entitlement": 7,
                "sick_leave_entitlement": 14,
                "maternity_leave_days": 112,
                "paternity_leave_days": 14,
                "grace_period_mins": 10,
                "late_arrival_threshold_mins": 15,
                "regulatory_body": "Ministry of Manpower (MOM)",
                "compliance_notes": "Employment Act"
            }
        ]
        
        return compliance_data
