from typing import Dict, Any
from uuid import UUID
from datetime import datetime, timezone, date
from Models.employee import Employee, Department
from Models.tenant_user import Tenant
from Schema.admin_dashboard import AdminDashboardResponse

class AdminDashboardService:
    @staticmethod
    async def get_dashboard_stats(tenant_id: UUID) -> AdminDashboardResponse:
        # Fetch employees
        employees = await Employee.find(Employee.tenant_id == tenant_id).to_list()
        total_employees = len(employees)
        
        now = datetime.now(timezone.utc)
        today_date = now.date()
        
        active_today = 0
        for emp in employees:
            if hasattr(emp, 'employment_status') and emp.employment_status == "Active":
                active_today += 1
            elif not hasattr(emp, 'employment_status') or str(emp.employment_status).lower() == 'active':
                active_today += 1

        # For attendance stats (using active as present for basic mock, assuming others absent)
        # Real logic should query Attendance collection
        present_count = active_today
        absent_count = total_employees - present_count if total_employees > present_count else 0
        rate = round((present_count / total_employees * 100), 1) if total_employees > 0 else 0.0

        attendance_stats = {
            "present": present_count,
            "absent": absent_count,
            "late": 0,
            "onLeave": 0, # Should query leaves
            "total": total_employees,
            "rate": rate
        }

        # Departments
        departments = await Department.find(Department.tenant_id == tenant_id).to_list()
        dept_dict = {str(d.id): d.name for d in departments}
        dept_counts = {}
        for emp in employees:
            d_name = dept_dict.get(str(emp.department_id), "Unassigned") if emp.department_id else "Unassigned"
            dept_counts[d_name] = dept_counts.get(d_name, 0) + 1

        dept_stats = []
        for name, count in dept_counts.items():
            dept_stats.append({
                "name": name,
                "headcount": count,
                "onLeave": 0,
                "avgLeave": 0.0,
                "trend": "stable"
            })

        # Absent Employees Mock (or use real if available)
        absent_employees = []
        colors = ["bg-blue-500", "bg-pink-500", "bg-amber-500", "bg-violet-500", "bg-emerald-500", "bg-rose-500"]
        for i, emp in enumerate(employees):
            # Just take some employees as "absent" if they aren't active or just random for now
            if len(absent_employees) < 3: # Mock logic
                first = emp.first_name or ""
                last = emp.last_name or ""
                name = f"{first} {last}".strip()
                initials = f"{first[:1]}{last[:1]}".upper() if first or last else "NA"
                d_name = dept_dict.get(str(emp.department_id), "Unassigned") if emp.department_id else "Unassigned"
                absent_employees.append({
                    "id": str(emp.id),
                    "name": name,
                    "role": "Employee",
                    "dept": d_name,
                    "initials": initials,
                    "color": colors[i % len(colors)]
                })

        # Activities Mock
        activities = [
            {"id": "1", "user": "System Admin", "action": "checked dashboard", "time": "Just now", "avatar": "SA", "color": "bg-linear-to-br from-blue-500 to-blue-600", "icon": "CheckCircle2"}
        ]

        # Checklist Mock
        checklist = [
            {"task": "Add First Employee", "completed": total_employees > 0},
            {"task": "Configure Departments", "completed": len(departments) > 0},
            {"task": "Set Up Leave Policies", "completed": False},
            {"task": "Define Compliance Rules", "completed": False},
            {"task": "Invite Team Members", "completed": total_employees > 1},
            {"task": "Run First Payroll", "completed": False}
        ]

        # Compliance Mock
        compliance = [
             {"id": "1", "subject": "Review Pending Leaves", "time": "10:00 AM", "start": today_date.strftime("%d-%m-%Y"), "end": today_date.strftime("%d-%m-%Y"), "priority": "Medium", "audience": "HR Dept", "dot": "bg-blue-500"}
        ]
        
        # Schedule Mock
        schedule = [
            {"id": "1", "title": "Payroll Processing Due", "time": "In 3 days", "highlight": True}
        ]

        # CRM Stats Mock
        crm_stats = {
            "totalRevenue": "₹0",
            "revenueGrowth": 0.0,
            "pendingRevenue": "₹0",
            "collectedRevenue": "₹0",
            "totalLeads": 0,
            "newLeadsToday": 0,
            "leadConversionRate": 0.0,
            "winRateData": [0, 0, 0]
        }

        tenant = await Tenant.get(tenant_id)
        active_modules = tenant.modules if tenant and hasattr(tenant, 'modules') else []
        has_crm = any(m.get('id') == 'crm' for m in active_modules) if active_modules else False
        
        return {
            "attendance": attendance_stats,
            "departments": dept_stats,
            "schedule": schedule,
            "compliance": compliance,
            "absentEmployees": absent_employees,
            "activities": activities,
            "checklist": checklist,
            "crm_stats": crm_stats if has_crm else None
        }
