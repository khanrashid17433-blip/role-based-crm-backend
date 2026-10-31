from beanie import Document
from pydantic import Field
from datetime import datetime, date
from typing import Optional, Any, Union, Dict
from uuid import UUID, uuid4
import enum


class EmploymentStatus(str, enum.Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    NOTICE_PERIOD = "notice_period"
    TERMINATED = "terminated"
    ALUMNI = "alumni"
    PENDING_START = "pending_start"


class EmploymentType(str, enum.Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    ZERO_HOURS = "zero_hours"
    INTERN = "intern"
    GIG = "gig"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"
    SELF_DESCRIBE = "self_describe"


class TerminationReason(str, enum.Enum):
    RESIGNATION = "resignation"
    REDUNDANCY = "redundancy"
    DISMISSAL = "dismissal"
    END_OF_CONTRACT = "end_of_contract"
    RETIREMENT = "retirement"


class JobLevel(str, enum.Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    HEAD = "head"


class LocationType(str, enum.Enum):
    OFFICE = "office"
    REMOTE = "remote"
    HYBRID = "hybrid"


class DocumentType(str, enum.Enum):
    CONTRACT = "contract"
    ID_PROOF = "id_proof"
    VISA = "visa"
    PASSPORT = "passport"
    CERTIFICATE = "certificate"
    OTHER = "other"


class Employee(Document):
    """Employee model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    entity_id: Optional[UUID] = None  # Reference to tenant_entities
    employee_number: str = Field(..., max_length=50, unique=True)
    user_id: Optional[UUID] = None
    
    # Personal Information
    first_name: str = Field(..., max_length=100)
    last_name: str = Field(..., max_length=100)
    preferred_name: Optional[str] = Field(None, max_length=100)
    pronouns: Optional[str] = Field(None, max_length=50)
    
    # Contact Information
    email_work: Optional[str] = Field(None, max_length=255)
    email_personal: Optional[str] = Field(None, max_length=255)
    phone_work: Optional[str] = Field(None, max_length=20)
    phone_personal: Optional[str] = Field(None, max_length=20)
    
    # Personal Details
    date_of_birth: Optional[datetime] = None
    gender: Optional[Gender] = None
    nationality: Optional[str] = Field(None, max_length=2)  # ISO 3166-1 alpha-2
    country_of_residence: Optional[str] = Field(None, max_length=2)  # ISO 3166-1 alpha-2
    address_json: Optional[dict] = None
    profile_photo_url: Optional[str] = None
    
    # Employment Details
    employment_status: EmploymentStatus = Field(default=EmploymentStatus.PENDING_START)
    employment_type: EmploymentType = Field(default=EmploymentType.FULL_TIME)
    hire_date: Optional[datetime] = None
    probation_end_date: Optional[datetime] = None
    notice_period_days: int = Field(default=30)
    termination_date: Optional[datetime] = None
    termination_reason: Optional[TerminationReason] = None
    
    # Organizational Structure
    department_id: Optional[UUID] = None
    job_title_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    work_location_id: Optional[UUID] = None
    region: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    
    # Custom Fields
    custom_fields_json: Optional[dict] = None
    documents: Optional[list[dict]] = Field(default_factory=list)
    
    # Audit Fields
    created_by: Optional[UUID] = None
    updated_by: Optional[UUID] = None
    
    class Settings:
        name = "employees"
        indexes = [
            "tenant_id",
            "employee_number",
            "user_id",
            "department_id",
            "manager_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class Department(Document):
    """Department model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    name: str = Field(..., max_length=200)
    parent_id: Optional[UUID] = None
    head_id: Optional[UUID] = None
    cost_center_code: Optional[str] = Field(None, max_length=50)
    
    class Settings:
        name = "departments"
        indexes = [
            "tenant_id",
            "parent_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class JobTitle(Document):
    """Job Title model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    name: str = Field(..., max_length=200)
    level: Optional[JobLevel] = None
    job_family: Optional[str] = Field(None, max_length=100)
    
    class Settings:
        name = "job_titles"
        indexes = [
            "tenant_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class WorkLocation(Document):
    """Work Location model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    name: str = Field(..., max_length=200)
    type: LocationType = Field(default=LocationType.OFFICE)
    address_json: Optional[dict] = None
    country: Optional[str] = Field(None, max_length=2)  # ISO 3166-1 alpha-2
    timezone: Optional[str] = Field(None, max_length=50)
    
    class Settings:
        name = "work_locations"
        indexes = [
            "tenant_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class EmployeeJobHistory(Document):
    """Employee Job History model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    employee_id: UUID
    job_title_id: Optional[UUID] = None
    department_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    change_reason: Optional[str] = Field(None, max_length=500)
    
    class Settings:
        name = "employee_job_history"
        indexes = [
            "employee_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class EmployeeDocument(Document):
    """Employee Document model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    employee_id: UUID
    document_type: DocumentType
    file_url: str
    file_name: str = Field(..., max_length=255)
    expiry_date: Optional[datetime] = None
    uploaded_by: UUID
    
    class Settings:
        name = "employee_documents"
        indexes = [
            "employee_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class EmployeeNote(Document):
    """Employee Note model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    employee_id: UUID
    note_text: str
    is_private: bool = Field(default=False)
    created_by: UUID
    
    class Settings:
        name = "employee_notes"
        indexes = [
            "employee_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class EmergencyContact(Document):
    """Emergency Contact model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    employee_id: UUID
    name: str = Field(..., max_length=200)
    relationship_type: str = Field(..., max_length=100)
    phone: str = Field(..., max_length=20)
    email: Optional[str] = Field(None, max_length=255)
    is_primary: bool = Field(default=False)
    
    class Settings:
        name = "emergency_contacts"
        indexes = [
            "employee_id",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class Announcement(Document):
    """Company Announcement model"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    title: str = Field(..., max_length=500)
    tag: str = Field(..., max_length=100)

    class Settings:
        name = "announcements"
        indexes = [
            "tenant_id",
        ]

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class Payslip(Document):
    """Employee Payslip model"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    user_id: Optional[UUID] = None
    employee_id: Optional[UUID] = None
    payroll_run_id: Optional[UUID] = None
    region: Optional[str] = None
    month: Any = Field(...)
    year: Optional[int] = None
    net_pay: float
    gross_pay: Optional[float] = Field(default=0)
    gross: Optional[float] = Field(default=0)
    deductions: Optional[float] = Field(default=0)
    pay_period: Optional[str] = Field(default="", max_length=200)
    pay_date: Optional[datetime] = None
    status: Any = Field(default="paid")
    components: Optional[Dict[str, Any]] = Field(default_factory=dict)
    employee_name: Optional[str] = ""
    designation: Optional[str] = ""
    department: Optional[str] = ""

    class Settings:
        name = "payslips"
        indexes = [
            "tenant_id",
            "user_id",
            "employee_id",
        ]

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class Recognition(Document):
    """Employee Recognition model"""
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    tenant_id: UUID
    user_id: UUID
    kudos: str = Field(..., max_length=500)
    sender: str = Field(..., max_length=200)
    streak: str = Field(..., max_length=200)

    class Settings:
        name = "recognitions"
        indexes = [
            "tenant_id",
            "user_id",
        ]

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
