from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from uuid import UUID
from enum import Enum

class EmploymentStatusEnum(str, Enum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    NOTICE_PERIOD = "notice_period"
    TERMINATED = "terminated"
    ALUMNI = "alumni"
    PENDING_START = "pending_start"

class EmploymentTypeEnum(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    ZERO_HOURS = "zero_hours"
    INTERN = "intern"
    GIG = "gig"

class GenderEnum(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NON_BINARY = "non_binary"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"
    SELF_DESCRIBE = "self_describe"

class TerminationReasonEnum(str, Enum):
    RESIGNATION = "resignation"
    REDUNDANCY = "redundancy"
    DISMISSAL = "dismissal"
    END_OF_CONTRACT = "end_of_contract"
    RETIREMENT = "retirement"

class JobLevelEnum(str, Enum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    HEAD = "head"

class LocationTypeEnum(str, Enum):
    OFFICE = "office"
    REMOTE = "remote"
    HYBRID = "hybrid"

class DocumentTypeEnum(str, Enum):
    CONTRACT = "contract"
    ID_PROOF = "id_proof"
    VISA = "visa"
    PASSPORT = "passport"
    CERTIFICATE = "certificate"
    OTHER = "other"

# Address Schema
class AddressSchema(BaseModel):
    line1: str
    line2: Optional[str] = None
    city: str
    state: str
    postal_code: str
    country: str

# Employee Document Schemas
class EmployeeDocumentCreateSchema(BaseModel):
    document_type: DocumentTypeEnum
    file_url: str
    file_name: str = Field(..., min_length=1, max_length=255)
    expiry_date: Optional[datetime] = None

class EmployeeDocumentResponseSchema(BaseModel):
    id: UUID
    employee_id: UUID
    document_type: DocumentTypeEnum
    file_url: str
    file_name: str
    expiry_date: Optional[datetime]
    uploaded_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# Employee Schemas
class EmployeeCreateSchema(BaseModel):
    entity_id: Optional[UUID] = None
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    preferred_name: Optional[str] = Field(None, max_length=100)
    pronouns: Optional[str] = Field(None, max_length=50)
    email_work: Optional[EmailStr] = None
    email_personal: Optional[EmailStr] = None
    phone_work: Optional[str] = Field(None, max_length=20)
    phone_personal: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[datetime] = None
    gender: Optional[GenderEnum] = None
    nationality: Optional[str] = Field(None, max_length=2)
    country_of_residence: Optional[str] = Field(None, max_length=2)
    address_json: Optional[AddressSchema] = None
    employment_status: EmploymentStatusEnum = EmploymentStatusEnum.PENDING_START
    employment_type: EmploymentTypeEnum = EmploymentTypeEnum.FULL_TIME
    hire_date: Optional[datetime] = None
    probation_end_date: Optional[datetime] = None
    notice_period_days: Optional[int] = Field(30, ge=0)
    department_id: Optional[UUID] = None
    job_title_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    work_location_id: Optional[UUID] = None
    region: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    custom_fields_json: Optional[Dict[str, Any]] = None
    documents: Optional[List[EmployeeDocumentCreateSchema]] = None

class EmployeeUpdateSchema(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    preferred_name: Optional[str] = Field(None, max_length=100)
    pronouns: Optional[str] = Field(None, max_length=50)
    email_work: Optional[EmailStr] = None
    email_personal: Optional[EmailStr] = None
    phone_work: Optional[str] = Field(None, max_length=20)
    phone_personal: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[datetime] = None
    gender: Optional[GenderEnum] = None
    nationality: Optional[str] = Field(None, max_length=2)
    country_of_residence: Optional[str] = Field(None, max_length=2)
    address_json: Optional[AddressSchema] = None
    employment_status: Optional[EmploymentStatusEnum] = None
    employment_type: Optional[EmploymentTypeEnum] = None
    hire_date: Optional[datetime] = None
    probation_end_date: Optional[datetime] = None
    notice_period_days: Optional[int] = Field(None, ge=0)
    termination_date: Optional[datetime] = None
    termination_reason: Optional[TerminationReasonEnum] = None
    department_id: Optional[UUID] = None
    job_title_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    work_location_id: Optional[UUID] = None
    region: Optional[str] = Field(None, max_length=100)
    timezone: Optional[str] = Field(None, max_length=50)
    custom_fields_json: Optional[Dict[str, Any]] = None

class EmployeeResponseSchema(BaseModel):
    id: UUID
    tenant_id: UUID
    entity_id: Optional[UUID]
    employee_number: str
    user_id: Optional[UUID]
    first_name: str
    last_name: str
    preferred_name: Optional[str]
    pronouns: Optional[str]
    email_work: Optional[str]
    email_personal: Optional[str]
    phone_work: Optional[str]
    phone_personal: Optional[str]
    date_of_birth: Optional[datetime]
    gender: Optional[GenderEnum]
    nationality: Optional[str]
    country_of_residence: Optional[str]
    address_json: Optional[Dict[str, Any]]
    profile_photo_url: Optional[str]
    employment_status: EmploymentStatusEnum
    employment_type: EmploymentTypeEnum
    hire_date: Optional[datetime]
    probation_end_date: Optional[datetime]
    notice_period_days: Optional[int]
    termination_date: Optional[datetime]
    termination_reason: Optional[TerminationReasonEnum]
    department_id: Optional[UUID]
    job_title_id: Optional[UUID]
    manager_id: Optional[UUID]
    work_location_id: Optional[UUID]
    region: Optional[str]
    timezone: Optional[str]
    custom_fields_json: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: Optional[datetime]
    
    # Extra resolved fields for UI
    department_name: Optional[str] = None
    job_title: Optional[str] = None
    manager_name: Optional[str] = None
    system_role: Optional[str] = None
    user_type: Optional[str] = None
    documents: List[EmployeeDocumentResponseSchema] = Field(default_factory=list)

    class Config:
        from_attributes = True

# Department Schemas
class DepartmentCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    parent_id: Optional[UUID] = None
    head_id: Optional[UUID] = None
    cost_center_code: Optional[str] = Field(None, max_length=50)

class DepartmentUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    parent_id: Optional[UUID] = None
    head_id: Optional[UUID] = None
    cost_center_code: Optional[str] = Field(None, max_length=50)

class DepartmentResponseSchema(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    parent_id: Optional[UUID]
    head_id: Optional[UUID]
    cost_center_code: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# Job Title Schemas
class JobTitleCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    level: Optional[JobLevelEnum] = None
    job_family: Optional[str] = Field(None, max_length=100)

class JobTitleUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    level: Optional[JobLevelEnum] = None
    job_family: Optional[str] = Field(None, max_length=100)

class JobTitleResponseSchema(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    level: Optional[JobLevelEnum]
    job_family: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# Work Location Schemas
class WorkLocationCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    type: LocationTypeEnum = LocationTypeEnum.OFFICE
    address_json: Optional[AddressSchema] = None
    country: Optional[str] = Field(None, max_length=2)
    timezone: Optional[str] = Field(None, max_length=50)

class WorkLocationUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    type: Optional[LocationTypeEnum] = None
    address_json: Optional[AddressSchema] = None
    country: Optional[str] = Field(None, max_length=2)
    timezone: Optional[str] = Field(None, max_length=50)

class WorkLocationResponseSchema(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    type: LocationTypeEnum
    address_json: Optional[Dict[str, Any]]
    country: Optional[str]
    timezone: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# Employee Note Schemas
class EmployeeNoteCreateSchema(BaseModel):
    note_text: str = Field(..., min_length=1)
    is_private: bool = False

class EmployeeNoteResponseSchema(BaseModel):
    id: UUID
    employee_id: UUID
    note_text: str
    is_private: bool
    created_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True

# Emergency Contact Schemas
class EmergencyContactCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    relationship_type: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=1, max_length=20)
    email: Optional[EmailStr] = None
    is_primary: bool = False

class EmergencyContactUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    relationship_type: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, min_length=1, max_length=20)
    email: Optional[EmailStr] = None
    is_primary: Optional[bool] = None

class EmergencyContactResponseSchema(BaseModel):
    id: UUID
    employee_id: UUID
    name: str
    relationship_type: str
    phone: str
    email: Optional[str]
    is_primary: bool
    created_at: datetime

    class Config:
        from_attributes = True

# Job History Schemas
class JobHistoryCreateSchema(BaseModel):
    job_title_id: Optional[UUID] = None
    department_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    change_reason: Optional[str] = Field(None, max_length=500)

class JobHistoryResponseSchema(BaseModel):
    id: UUID
    employee_id: UUID
    job_title_id: Optional[UUID]
    department_id: Optional[UUID]
    manager_id: Optional[UUID]
    start_date: datetime
    end_date: Optional[datetime]
    change_reason: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

# List Response Schemas
class EmployeeListResponseSchema(BaseModel):
    employees: List[EmployeeResponseSchema]
    total: int
    page: int
    per_page: int
    total_pages: int

class DepartmentListResponseSchema(BaseModel):
    departments: List[DepartmentResponseSchema]
    total: int

class JobTitleListResponseSchema(BaseModel):
    job_titles: List[JobTitleResponseSchema]
    total: int

class WorkLocationListResponseSchema(BaseModel):
    work_locations: List[WorkLocationResponseSchema]
    total: int
