from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from datetime import date
try:
    from beanie.odm.utils.encoder import ENCODERS_BY_TYPE
    ENCODERS_BY_TYPE[date] = lambda v: v.isoformat()
except ImportError:
    from beanie.odm.utils.encoder import DEFAULT_CUSTOM_ENCODERS
    DEFAULT_CUSTOM_ENCODERS[date] = lambda v: v.isoformat()

from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# MongoDB configuration
MONGODB_URL = os.getenv("MONGODB_URL")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")

# Global MongoDB client
mongodb_client: AsyncIOMotorClient = None


async def get_db():
    return mongodb_client[MONGODB_DB_NAME]


async def init_db():
    """Initialize MongoDB connection and Beanie ODM"""
    global mongodb_client
    
    # Import all models here to avoid circular imports
    from Models.plan import Plan
    from Models.tenant_registration import TenantRegistration
    from Models.email_verification_token import EmailVerificationToken
    from Models.tenant_user import Tenant, User
    from Models.login_security import (
        TrustedDevice, RefreshToken, LoginEvent, 
        PasswordHistory, SSOConfiguration, MagicLinkToken
    )
    from Models.onboarding import TenantOnboarding, UserInvitation
    from Models.security_event import SecurityEvent
    from Models.employee import (
        Employee, Department, JobTitle, WorkLocation,
        EmployeeJobHistory, EmployeeDocument, EmployeeNote, EmergencyContact,
        Announcement, Payslip, Recognition
    )
    from Models.billing import (
        TenantSubscription, BillingEvent, Invoice, Refund, TenantModule, SSOConfiguration as BillingSSOConfiguration
    )
    from Models.crm import (
        CrmLead, CrmDeal, CrmActivity, CrmProposal, CrmClient,
        CrmPipeline, CrmDealStageHistory, CrmDealAuditLog
    )
    from Models.crm_task import CrmTask
    from Models.crm_contacts import (
        CrmContact, CrmCompany, CrmTimeline, CrmContactNote,
        CrmContactCall, CrmContactMeeting, CrmContactEmail
    )
    from Models.crm_deal_activities import (
        CrmDealNote, CrmDealCall, CrmDealMeeting, CrmDealTask,
        CrmDealDocument, CrmDealActivityFeed
    )
    from Models.crm_deal_associations import (
        CrmDealContact, CrmDealTeam, CrmDealLineItem
    )
    from Models.attendance import (
        Shift, AttendanceRawLog, AttendanceLog, AttendanceDevice, AttendanceGeoFence,
        AttendanceRegularisation, AttendanceQrSession, OvertimeApproval,
        ShiftSwap, WtrOptOut, RosterDraft, RosterAssignment, GlobalAttendancePolicy
    )
    from Models.pm import (
        Project, ProjectMember, ProjectMilestone,
        Task, TaskWatcher, TaskSubtask, TaskAttachment, TaskTimeEntry, TaskLabel, TaskLabelAssignment
    )
    from Models.note import Note, NoteMention, NoteAttachment, NoteReaction, NoteEdit
    from Models.assignment import AssignmentHistory, WorkloadSnapshot, ClientAccountTeam, AutoAssignmentRule
    from Models.leave import LeavePolicy
    from Models.employeeleave import LeaveApplication
    from Models.leave_assignment import LeaveAssignment
    from Models.payroll import EmployeePayrollConfig, PayrollRun, Payslip as PayrollPayslip
    from Models.holiday import Holiday
    from Models.role import Role
    from Models.job import JobRequisition
    from Models.job_posting import JobPosting
    from Models.announcement import CompanyAnnouncement, CompanyAnnouncementReadStatus
    from Models.platform_settings import PlatformSettings
    from Models.audit_log import SettingsAuditLog
    from Models.ticket import Ticket

    
    # Create MongoDB client
    mongodb_client = AsyncIOMotorClient(MONGODB_URL)
    
    # Get database
    db = mongodb_client[MONGODB_DB_NAME]
    
    # Initialize Beanie with all document models
    await init_beanie(
        database=db,
        document_models=[
            Plan,
            TenantRegistration,
            EmailVerificationToken,
            Tenant,
            User,
            TrustedDevice,
            RefreshToken,
            LoginEvent,
            PasswordHistory,
            SSOConfiguration,
            MagicLinkToken,
            TenantOnboarding,
            UserInvitation,
            SecurityEvent,
            Employee,
            Department,
            JobTitle,
            WorkLocation,
            EmployeeJobHistory,
            EmployeeDocument,
            EmployeeNote,
            EmergencyContact,
            Announcement,
            Payslip,
            Recognition,
            # Billing models
            TenantSubscription,
            BillingEvent,
            Invoice,
            Refund,
            TenantModule,
            BillingSSOConfiguration,
            # CRM models
            CrmLead,
            CrmDeal,
            CrmActivity,
            CrmTask,
            CrmProposal,
            CrmClient,
            CrmPipeline,
            CrmDealStageHistory,
            CrmDealAuditLog,
            CrmContact,
            CrmCompany,
            CrmTimeline,
            CrmContactNote,
            CrmContactCall,
            CrmContactMeeting,
            CrmContactEmail,
            # Deal Activity models
            CrmDealNote,
            CrmDealCall,
            CrmDealMeeting,
            CrmDealTask,
            CrmDealDocument,
            CrmDealActivityFeed,
            # Deal Association models
            CrmDealContact,
            CrmDealTeam,
            CrmDealLineItem,
            # Attendance models
            Shift,
            AttendanceRawLog,
            AttendanceLog,
            AttendanceDevice,
            AttendanceGeoFence,
            AttendanceRegularisation,
            AttendanceQrSession,
            OvertimeApproval,
            ShiftSwap,
            WtrOptOut,
            RosterDraft,
            RosterAssignment,
            GlobalAttendancePolicy,
            # PM models
            Project,
            ProjectMember,
            ProjectMilestone,
            Task,
            TaskWatcher,
            TaskSubtask,
            TaskAttachment,
            TaskTimeEntry,
            TaskLabel,
            TaskLabelAssignment,
            # Note models
            Note,
            NoteMention,
            NoteAttachment,
            NoteReaction,
            NoteEdit,
            # Assignment models
            AssignmentHistory,
            WorkloadSnapshot,
            ClientAccountTeam,
            AutoAssignmentRule,
            LeavePolicy,
            LeaveApplication,
            LeaveAssignment,
            # Payroll models
            EmployeePayrollConfig,
            PayrollRun,
            PayrollPayslip,
            # Holiday model
            Holiday,
            # Role model
            Role,
            # Job model
            JobRequisition,
            JobPosting,
            # Company announcements
            CompanyAnnouncement,
            CompanyAnnouncementReadStatus,
            # Settings
            PlatformSettings,
            SettingsAuditLog,
            Ticket
        ]
        
    )
    
    print(f"MongoDB initialized successfully! Connected to: {MONGODB_DB_NAME}")


async def close_db():
    """Close MongoDB connections"""
    global mongodb_client
    if mongodb_client:
        mongodb_client.close()
        print("MongoDB connections closed!")