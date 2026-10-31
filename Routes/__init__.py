from fastapi import APIRouter
from Routes.plan import router as plan_router
from Routes.auth import router as auth_router
from Routes.tenents import router as superadmin_router
from Routes.onboarding import router as onboarding_router
from Routes.invitation import router as invitation_router
from Routes.audit import router as audit_router
from Routes.trial import router as trial_router
from Routes.employee import router as employee_router
from Routes.user import router as user_router
from Routes.billing import router as billing_router
from Routes.crm import router as crm_router
from Routes.crm_contacts import router as crm_contacts_router
from Routes.attendance import router as attendance_router, compat_router as attendance_compat_router
from Routes.pm import router as pm_router
from Routes.note import router as note_router, compat_router as note_compat_router
from Routes.assignment import router as assignment_router
from Routes.dashboard import router as dashboard_router
from Routes.leave import router as leave_router
from Routes.employeeleave import router as employeeleave_router
from Routes.leave_assignment import router as leave_assignment_router
from Routes.payroll import router as payroll_router
from Routes.holiday import router as holiday_router
from Routes.role import router as role_router
from Routes.job import router as job_router
from Routes.job_posting import router as job_posting_router
from Routes.hr_dashboard import router as hr_dashboard_router
from Routes.admin_dashboard import router as admin_dashboard_router
from Routes.announcement import router as announcement_router
from Routes.ticket import router as ticket_router
from Routes.deal_workspace import router as deal_workspace_router
from Routes.deal_associations import router as deal_associations_router
from Routes.crm_tasks import router as crm_tasks_router
# Create main router
api_router = APIRouter()

# Include routers with tags
api_router.include_router(plan_router, tags=["Plans"])
api_router.include_router(auth_router, tags=["Authentication"])
api_router.include_router(user_router, tags=["User Profile"])
api_router.include_router(invitation_router, tags=["Invitations"])
api_router.include_router(superadmin_router, tags=["Tenents"])
api_router.include_router(dashboard_router, tags=["Super Admin Dashboard"])
api_router.include_router(onboarding_router, tags=["Onboarding"])
api_router.include_router(audit_router, tags=["Audit Logs"])
api_router.include_router(trial_router, tags=["Trial Management"])
from Routes.employee_self_service import router as employee_self_service_router
api_router.include_router(employee_router, tags=["Employee Management"])
api_router.include_router(employee_self_service_router)
api_router.include_router(billing_router, tags=["Billing & Subscriptions"])
api_router.include_router(crm_router, tags=["CRM"])
api_router.include_router(crm_contacts_router)
api_router.include_router(attendance_router, tags=["Attendance"])
api_router.include_router(attendance_compat_router)
api_router.include_router(pm_router, tags=["Project & Task Management"])
api_router.include_router(note_router, tags=["Unified Notes"])
api_router.include_router(note_compat_router)
api_router.include_router(assignment_router, tags=["Team Assignment & Workload"])
api_router.include_router(leave_router, tags=["Leave Management"])
api_router.include_router(employeeleave_router, tags=["Employee Leave Management"])
api_router.include_router(leave_assignment_router, tags=["Leave Policy Assignment"])
api_router.include_router(payroll_router, tags=["Payroll Management"])
api_router.include_router(holiday_router, tags=["Holiday Management"])
api_router.include_router(role_router, tags=["Roles & Permissions"])
api_router.include_router(job_router, tags=["Job Requisition"])
api_router.include_router(job_posting_router, tags= ["job posting"])
api_router.include_router(hr_dashboard_router, tags=["HR Dashboard"])
api_router.include_router(admin_dashboard_router, tags=["Admin Dashboard"])
api_router.include_router(announcement_router, tags=["Announcements"])
api_router.include_router(ticket_router)
api_router.include_router(deal_workspace_router)
api_router.include_router(deal_associations_router, tags=["Deal Associations"])
api_router.include_router(crm_tasks_router, tags=["CRM Tasks"])
__all__ = ["api_router"]
