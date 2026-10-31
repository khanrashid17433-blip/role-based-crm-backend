from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
from datetime import date, datetime
import re
from beanie.operators import In

from Models.employee import (
    Employee, Department, JobTitle, WorkLocation, 
    EmployeeJobHistory, EmployeeDocument, EmployeeNote, EmergencyContact,
    EmploymentStatus, EmploymentType
)
from Models.tenant_user import User
from Schema.employee import (
    EmployeeCreateSchema, EmployeeUpdateSchema,
    DepartmentCreateSchema, DepartmentUpdateSchema,
    JobTitleCreateSchema, JobTitleUpdateSchema,
    WorkLocationCreateSchema, WorkLocationUpdateSchema,
    EmployeeDocumentCreateSchema, EmployeeDocumentResponseSchema, EmployeeNoteCreateSchema,
    EmergencyContactCreateSchema, EmergencyContactUpdateSchema,
    JobHistoryCreateSchema
)
from Utility.exceptions import ValidationError, NotFoundError, ConflictError

class EmployeeService:
    def __init__(self):
        pass

    async def generate_employee_number(self, tenant_id: UUID) -> str:
        """Generate unique employee number for tenant"""
        # Get the last employee number for this tenant
        last_employee = await Employee.find(
            Employee.tenant_id == tenant_id
        ).sort("-created_at").first_or_none()
        
        if last_employee and last_employee.employee_number:
            # Extract number from format EMP-{number}
            match = re.search(r'EMP-(\d+)', last_employee.employee_number)
            if match:
                next_number = int(match.group(1)) + 1
            else:
                next_number = 1
        else:
            next_number = 1
        
        return f"EMP-{next_number:06d}"

    async def create_employee(self, employee_data: EmployeeCreateSchema, tenant_id: UUID, created_by: UUID) -> Employee:
        """Create a new employee"""
        
        # Check plan limit for max employees
        from Models.tenant_user import Tenant
        from Models.plan import Plan
        from Models.employee import EmploymentStatus
        
        tenant = await Tenant.find_one(Tenant.id == tenant_id)
        if tenant and tenant.plan_id:
            plan = await Plan.find_one(Plan.id == tenant.plan_id)
            if plan and plan.max_employees != -1:
                # Count current non-terminated employees
                current_count = await Employee.find(
                    Employee.tenant_id == tenant_id,
                    Employee.employment_status != EmploymentStatus.TERMINATED
                ).count()
                if current_count >= plan.max_employees:
                    raise ConflictError(f"Employee limit reached. Your plan allows a maximum of {plan.max_employees} employees.")

        # Generate employee number
        employee_number = await self.generate_employee_number(tenant_id)
        
        # Validate manager exists if provided
        # Validate manager exists if provided
        if employee_data.manager_id and str(employee_data.manager_id) != "00000000-0000-0000-0000-000000000000":
            manager = await Employee.find_one(
                Employee.id == employee_data.manager_id,
                Employee.tenant_id == tenant_id
            )
            if not manager:
                raise ValidationError("Manager not found")
        
        # Validate department exists if provided
        if employee_data.department_id and str(employee_data.department_id) != "00000000-0000-0000-0000-000000000000":
            department = await Department.find_one(
                Department.id == employee_data.department_id,
                Department.tenant_id == tenant_id
            )
            if not department:
                raise ValidationError("Department not found")
        
        # Validate job title exists if provided
        if employee_data.job_title_id and str(employee_data.job_title_id) != "00000000-0000-0000-0000-000000000000":
            job_title = await JobTitle.find_one(
                JobTitle.id == employee_data.job_title_id,
                JobTitle.tenant_id == tenant_id
            )
            if not job_title:
                raise ValidationError("Job title not found")
        
        # Validate work location exists if provided
        if employee_data.work_location_id and str(employee_data.work_location_id) != "00000000-0000-0000-0000-000000000000":
            work_location = await WorkLocation.find_one(
                WorkLocation.id == employee_data.work_location_id,
                WorkLocation.tenant_id == tenant_id
            )
            if not work_location:
                raise ValidationError("Work location not found")
        
        # Create employee
        employee_payload = employee_data.dict(exclude_unset=True, exclude={"documents"})
        employee = Employee(
            tenant_id=tenant_id,
            employee_number=employee_number,
            created_by=created_by,
            **employee_payload
        )

        document_entries = []
        for document_data in employee_data.documents or []:
            document_id = uuid4()
            document_entries.append({
                "id": document_id,
                "employee_id": employee.id,
                "document_type": document_data.document_type.value if hasattr(document_data.document_type, "value") else document_data.document_type,
                "file_url": document_data.file_url,
                "file_name": document_data.file_name,
                "expiry_date": document_data.expiry_date,
                "uploaded_by": created_by,
                "created_at": datetime.utcnow(),
            })

        employee.documents = document_entries
        
        await employee.insert()

        # Store documents uploaded during employee creation
        for document_data, document_entry in zip(employee_data.documents or [], document_entries):
            document = EmployeeDocument(
                id=document_entry["id"],
                employee_id=employee.id,
                uploaded_by=created_by,
                **document_data.dict(exclude_unset=True)
            )
            await document.insert()
        
        # Create initial job history record
        if employee_data.hire_date:
            job_history = EmployeeJobHistory(
                employee_id=employee.id,
                job_title_id=employee_data.job_title_id,
                department_id=employee_data.department_id,
                manager_id=employee_data.manager_id,
                start_date=employee_data.hire_date,
                change_reason="Initial hire"
            )
            await job_history.insert()
        
        return employee

    async def get_employee_by_id(self, employee_id: UUID, tenant_id: UUID) -> Optional[Employee]:
        """Get employee by ID"""
        return await Employee.find_one(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id
        )

    async def get_employee_by_number(self, employee_number: str, tenant_id: UUID) -> Optional[Employee]:
        """Get employee by employee number"""
        return await Employee.find_one(
            Employee.employee_number == employee_number,
            Employee.tenant_id == tenant_id
        )

    async def get_employees(self, tenant_id: UUID, page: int = 1, per_page: int = 20, 
                     search: Optional[str] = None, department_id: Optional[UUID] = None,
                     employment_status: Optional[str] = None) -> Dict[str, Any]:
        """Get paginated list of employees with filters"""
        filters = [Employee.tenant_id == tenant_id]
        
        # Apply filters
        if search:
            # MongoDB text search or regex search
            search_filters = [
                {"first_name": {"$regex": search, "$options": "i"}},
                {"last_name": {"$regex": search, "$options": "i"}},
                {"preferred_name": {"$regex": search, "$options": "i"}},
                {"employee_number": {"$regex": search, "$options": "i"}},
                {"email_work": {"$regex": search, "$options": "i"}}
            ]
            filters.append({"$or": search_filters})
        
        if department_id:
            filters.append(Employee.department_id == department_id)
        
        if employment_status:
            filters.append(Employee.employment_status == employment_status)
        
        # Get total count
        total = await Employee.find({"$and": filters} if len(filters) > 1 else filters[0]).count()
        
        # Apply pagination
        skip = (page - 1) * per_page
        employees = await Employee.find(
            {"$and": filters} if len(filters) > 1 else filters[0],
            skip=skip,
            limit=per_page
        ).to_list()
        
        total_pages = (total + per_page - 1) // per_page
        
        # Resolve names for UI
        dept_ids = list(set(e.department_id for e in employees if e.department_id))
        title_ids = list(set(e.job_title_id for e in employees if e.job_title_id))
        mgr_ids = list(set(e.manager_id for e in employees if e.manager_id))
        
        depts = await Department.find(In(Department.id, dept_ids)).to_list() if dept_ids else []
        titles = await JobTitle.find(In(JobTitle.id, title_ids)).to_list() if title_ids else []
        mgrs = await Employee.find(In(Employee.id, mgr_ids)).to_list() if mgr_ids else []
        linked_user_ids = list(set(e.user_id for e in employees if e.user_id))
        linked_emails = list(set((e.email_work or "").lower().strip() for e in employees if e.email_work))
        linked_users = []
        if linked_user_ids:
            linked_users.extend(await User.find(In(User.id, linked_user_ids), User.tenant_id == tenant_id).to_list())
        if linked_emails:
            linked_users.extend(await User.find(In(User.email, linked_emails), User.tenant_id == tenant_id).to_list())
        
        dept_map = {d.id: d.name for d in depts}
        title_map = {t.id: t.name for t in titles}
        mgr_map = {m.id: f"{m.first_name} {m.last_name}".strip() for m in mgrs}
        user_by_id = {u.id: u for u in linked_users}
        user_by_email = {u.email.lower().strip(): u for u in linked_users if u.email}
        
        from Schema.employee import EmployeeResponseSchema
        
        resolved_employees = []
        employee_ids = [e.id for e in employees]
        docs = await EmployeeDocument.find(In(EmployeeDocument.employee_id, employee_ids)).to_list() if employee_ids else []
        docs_map: Dict[UUID, List[EmployeeDocumentResponseSchema]] = {}
        for doc in docs:
            docs_map.setdefault(doc.employee_id, []).append(EmployeeDocumentResponseSchema.from_orm(doc))

        for e in employees:
            emp_schema = EmployeeResponseSchema.from_orm(e)
            emp_schema.department_name = dept_map.get(e.department_id) if e.department_id else None
            emp_schema.job_title = title_map.get(e.job_title_id) if e.job_title_id else None
            emp_schema.manager_name = mgr_map.get(e.manager_id) if e.manager_id else None
            linked_user = user_by_id.get(e.user_id) if e.user_id else None
            if not linked_user and e.email_work:
                linked_user = user_by_email.get(e.email_work.lower().strip())
            if linked_user:
                emp_schema.system_role = linked_user.role
                emp_schema.user_type = linked_user.user_type.value if linked_user.user_type else None
            emp_schema.documents = docs_map.get(e.id, [])
            resolved_employees.append(emp_schema)
        
        return {
            "employees": resolved_employees,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        }

    async def update_employee(self, employee_id: UUID, employee_data: EmployeeUpdateSchema, 
                       tenant_id: UUID, updated_by: UUID) -> Employee:
        """Update employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        # Validate references if provided
        if employee_data.manager_id and employee_data.manager_id != employee.manager_id:
            if employee_data.manager_id == employee_id:
                raise ValidationError("Employee cannot be their own manager")
            manager = await Employee.find_one(
                Employee.id == employee_data.manager_id,
                Employee.tenant_id == tenant_id
            )
            if not manager:
                raise ValidationError("Manager not found")
        
        if employee_data.department_id and employee_data.department_id != employee.department_id:
            department = await Department.find_one(
                Department.id == employee_data.department_id,
                Department.tenant_id == tenant_id
            )
            if not department:
                raise ValidationError("Department not found")
        
        if employee_data.job_title_id and employee_data.job_title_id != employee.job_title_id:
            job_title = await JobTitle.find_one(
                JobTitle.id == employee_data.job_title_id,
                JobTitle.tenant_id == tenant_id
            )
            if not job_title:
                raise ValidationError("Job title not found")
        
        if employee_data.work_location_id and employee_data.work_location_id != employee.work_location_id:
            work_location = await WorkLocation.find_one(
                WorkLocation.id == employee_data.work_location_id,
                WorkLocation.tenant_id == tenant_id
            )
            if not work_location:
                raise ValidationError("Work location not found")
        
        # Check if organizational changes require job history entry
        org_changes = any([
            employee_data.job_title_id and employee_data.job_title_id != employee.job_title_id,
            employee_data.department_id and employee_data.department_id != employee.department_id,
            employee_data.manager_id and employee_data.manager_id != employee.manager_id
        ])
        
        # Update employee
        update_data = employee_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(employee, field, value)
        
        employee.updated_by = updated_by
        employee.updated_at = datetime.utcnow()
        await employee.save()
        
        # Create job history entry if organizational changes
        if org_changes:
            # End current job history record
            current_history = await EmployeeJobHistory.find_one(
                EmployeeJobHistory.employee_id == employee_id,
                EmployeeJobHistory.end_date == None
            )
            
            if current_history:
                current_history.end_date = date.today()
                await current_history.save()
            
            # Create new job history record
            new_history = EmployeeJobHistory(
                employee_id=employee_id,
                job_title_id=employee.job_title_id,
                department_id=employee.department_id,
                manager_id=employee.manager_id,
                start_date=date.today(),
                change_reason="Organizational change"
            )
            await new_history.insert()
        
        return employee

    async def delete_employee(self, employee_id: UUID, tenant_id: UUID, updated_by: Optional[UUID] = None) -> bool:
        """Soft delete employee by setting status to terminated"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")

        now = datetime.utcnow()
        update_data = {
            "employment_status": EmploymentStatus.TERMINATED.value,
            "termination_date": now,
            "updated_at": now,
        }
        if updated_by:
            update_data["updated_by"] = updated_by

        await Employee.find_one(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id
        ).update({"$set": update_data})
        
        return True

    async def link_user_to_employee(self, employee_id: UUID, user_id: UUID, tenant_id: UUID) -> Employee:
        """Link a user account to an employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        # Check if user exists and belongs to same tenant
        user = await User.find_one(
            User.id == user_id,
            User.tenant_id == tenant_id
        )
        if not user:
            raise NotFoundError("User not found")
        
        # Check if user is already linked to another employee
        existing_employee = await Employee.find_one(
            Employee.user_id == user_id,
            Employee.tenant_id == tenant_id
        )
        if existing_employee and existing_employee.id != employee_id:
            raise ConflictError("User is already linked to another employee")
        
        employee.user_id = user_id
        if employee.employment_status == EmploymentStatus.PENDING_START:
            employee.employment_status = EmploymentStatus.ACTIVE
        await employee.save()
        
        return employee

    # Department methods
    async def create_department(self, department_data: DepartmentCreateSchema, tenant_id: UUID) -> Department:
        """Create a new department"""
        # Validate parent department if provided
        if department_data.parent_id:
            parent = await Department.find_one(
                Department.id == department_data.parent_id,
                Department.tenant_id == tenant_id
            )
            if not parent:
                raise ValidationError("Parent department not found")
        
        # Validate head employee if provided
        if department_data.head_id:
            head = await Employee.find_one(
                Employee.id == department_data.head_id,
                Employee.tenant_id == tenant_id
            )
            if not head:
                raise ValidationError("Head employee not found")
        
        department = Department(
            tenant_id=tenant_id,
            **department_data.dict(exclude_unset=True)
        )
        
        await department.insert()
        return department

    async def get_departments(self, tenant_id: UUID) -> List[Department]:
        """Get all departments for tenant"""
        return await Department.find(Department.tenant_id == tenant_id).to_list()

    async def update_department(self, department_id: UUID, department_data: DepartmentUpdateSchema, 
                         tenant_id: UUID) -> Department:
        """Update department"""
        department = await Department.find_one(
            Department.id == department_id,
            Department.tenant_id == tenant_id
        )
        if not department:
            raise NotFoundError("Department not found")
        
        # Validate parent department if provided
        if department_data.parent_id:
            if department_data.parent_id == department_id:
                raise ValidationError("Department cannot be its own parent")
            parent = await Department.find_one(
                Department.id == department_data.parent_id,
                Department.tenant_id == tenant_id
            )
            if not parent:
                raise ValidationError("Parent department not found")
        
        # Validate head employee if provided
        if department_data.head_id:
            head = await Employee.find_one(
                Employee.id == department_data.head_id,
                Employee.tenant_id == tenant_id
            )
            if not head:
                raise ValidationError("Head employee not found")
        
        update_data = department_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(department, field, value)
        await department.save()
        
        return department

    # Job Title methods
    async def create_job_title(self, job_title_data: JobTitleCreateSchema, tenant_id: UUID) -> JobTitle:
        """Create a new job title"""
        job_title = JobTitle(
            tenant_id=tenant_id,
            **job_title_data.dict(exclude_unset=True)
        )
        
        await job_title.insert()
        return job_title

    async def get_job_titles(self, tenant_id: UUID) -> List[JobTitle]:
        """Get all job titles for tenant"""
        return await JobTitle.find(JobTitle.tenant_id == tenant_id).to_list()

    async def update_job_title(self, job_title_id: UUID, job_title_data: JobTitleUpdateSchema, 
                        tenant_id: UUID) -> JobTitle:
        """Update job title"""
        job_title = await JobTitle.find_one(
            JobTitle.id == job_title_id,
            JobTitle.tenant_id == tenant_id
        )
        if not job_title:
            raise NotFoundError("Job title not found")
        
        update_data = job_title_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(job_title, field, value)
        await job_title.save()
        
        return job_title

    # Work Location methods
    async def create_work_location(self, location_data: WorkLocationCreateSchema, tenant_id: UUID) -> WorkLocation:
        """Create a new work location"""
        work_location = WorkLocation(
            tenant_id=tenant_id,
            **location_data.dict(exclude_unset=True)
        )
        
        await work_location.insert()
        return work_location

    async def get_work_locations(self, tenant_id: UUID) -> List[WorkLocation]:
        """Get all work locations for tenant"""
        return await WorkLocation.find(WorkLocation.tenant_id == tenant_id).to_list()

    async def update_work_location(self, location_id: UUID, location_data: WorkLocationUpdateSchema, 
                           tenant_id: UUID) -> WorkLocation:
        """Update work location"""
        work_location = await WorkLocation.find_one(
            WorkLocation.id == location_id,
            WorkLocation.tenant_id == tenant_id
        )
        if not work_location:
            raise NotFoundError("Work location not found")
        
        update_data = location_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(work_location, field, value)
        await work_location.save()
        return work_location

    # Employee Document methods
    async def add_employee_document(self, employee_id: UUID, document_data: EmployeeDocumentCreateSchema, 
                            tenant_id: UUID, uploaded_by: UUID) -> EmployeeDocument:
        """Add document to employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        document = EmployeeDocument(
            employee_id=employee_id,
            uploaded_by=uploaded_by,
            **document_data.dict(exclude_unset=True)
        )
        
        await document.insert()

        employee.documents = employee.documents or []
        employee.documents.append({
            "id": document.id,
            "employee_id": employee_id,
            "document_type": document.document_type.value if hasattr(document.document_type, "value") else document.document_type,
            "file_url": document.file_url,
            "file_name": document.file_name,
            "expiry_date": document.expiry_date,
            "uploaded_by": uploaded_by,
            "created_at": document.created_at,
        })
        employee.updated_at = datetime.utcnow()
        employee.updated_by = uploaded_by
        await employee.save()

        return document

    async def get_employee_documents(self, employee_id: UUID, tenant_id: UUID) -> List[EmployeeDocument]:
        """Get all documents for employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        documents = await EmployeeDocument.find(
            EmployeeDocument.employee_id == employee_id
        ).to_list()

        if documents:
            return documents

        embedded_documents = []
        for item in employee.documents or []:
            try:
                embedded_documents.append(EmployeeDocument(
                    id=item.get("id", uuid4()),
                    employee_id=employee_id,
                    document_type=item.get("document_type", "other"),
                    file_url=item.get("file_url", ""),
                    file_name=item.get("file_name", "Uploaded File"),
                    expiry_date=item.get("expiry_date"),
                    uploaded_by=item.get("uploaded_by") or employee.created_by,
                    created_at=item.get("created_at") or employee.created_at,
                ))
            except Exception:
                continue

        return embedded_documents

    # Employee Note methods
    async def add_employee_note(self, employee_id: UUID, note_data: EmployeeNoteCreateSchema, 
                         tenant_id: UUID, created_by: UUID) -> EmployeeNote:
        """Add note to employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        note = EmployeeNote(
            employee_id=employee_id,
            created_by=created_by,
            **note_data.dict(exclude_unset=True)
        )
        
        await note.insert()
        return note

    async def get_employee_notes(self, employee_id: UUID, tenant_id: UUID, 
                          include_private: bool = False) -> List[EmployeeNote]:
        """Get notes for employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        filters = [EmployeeNote.employee_id == employee_id]
        
        if not include_private:
            filters.append(EmployeeNote.is_private == False)
        
        return await EmployeeNote.find(
            {"$and": filters} if len(filters) > 1 else filters[0],
            sort=[("created_at", -1)]
        ).to_list()

    # Emergency Contact methods
    async def add_emergency_contact(self, employee_id: UUID, contact_data: EmergencyContactCreateSchema, 
                            tenant_id: UUID) -> EmergencyContact:
        """Add emergency contact to employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        # If this is set as primary, unset other primary contacts
        if contact_data.is_primary:
            existing_primary = await EmergencyContact.find(
                EmergencyContact.employee_id == employee_id,
                EmergencyContact.is_primary == True
            ).to_list()
            
            for contact in existing_primary:
                contact.is_primary = False
                await contact.save()
        
        contact = EmergencyContact(
            employee_id=employee_id,
            **contact_data.dict(exclude_unset=True)
        )
        
        await contact.insert()
        return contact

    async def get_emergency_contacts(self, employee_id: UUID, tenant_id: UUID) -> List[EmergencyContact]:
        """Get emergency contacts for employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        return await EmergencyContact.find(
            EmergencyContact.employee_id == employee_id,
            sort=[("is_primary", -1)]
        ).to_list()

    async def update_emergency_contact(self, contact_id: UUID, contact_data: EmergencyContactUpdateSchema, 
                               employee_id: UUID, tenant_id: UUID) -> EmergencyContact:
        """Update emergency contact"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        contact = await EmergencyContact.find_one(
            EmergencyContact.id == contact_id,
            EmergencyContact.employee_id == employee_id
        )
        if not contact:
            raise NotFoundError("Emergency contact not found")
        
        # If this is set as primary, unset other primary contacts
        if contact_data.is_primary and not contact.is_primary:
            existing_primary = await EmergencyContact.find(
                EmergencyContact.employee_id == employee_id,
                EmergencyContact.is_primary == True
            ).to_list()
            
            for existing_contact in existing_primary:
                existing_contact.is_primary = False
                await existing_contact.save()
        
        update_data = contact_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(contact, field, value)
        await contact.save()
        return contact

    # Job History methods
    async def get_employee_job_history(self, employee_id: UUID, tenant_id: UUID) -> List[EmployeeJobHistory]:
        """Get job history for employee"""
        employee = await self.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        # MongoDB doesn't have joinedload, so we'll need to populate references manually
        # or use aggregation pipeline if needed
        return await EmployeeJobHistory.find(
            EmployeeJobHistory.employee_id == employee_id,
            sort=[("start_date", -1)]
        ).to_list()
