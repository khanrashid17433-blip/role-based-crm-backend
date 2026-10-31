from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional
from uuid import UUID, uuid4
from datetime import datetime
import io
import csv
import logging

from Models.crm_contacts import (
    CrmContact, CrmCompany, CrmTimeline, CrmContactNote,
    CrmContactCall, CrmContactMeeting, CrmContactEmail
)
from Models.crm_task import CrmTask
from Models.crm import Priority, CrmDeal
from Schema.crm_contacts import (
    CrmContactCreate, CrmContactUpdate, ContactSearchRequest,
    ContactFilterRequest, BulkUpdateRequest, MergeRequest,
    CrmContactNoteCreate, CrmContactCallCreate, CrmContactMeetingCreate,
    CrmContactEmailCreate
)
from Utility.auth_helpers import get_current_user, verify_platform_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm", tags=["CRM Contacts"])

# Helper function to log timeline activity
async def log_activity(contact_id: UUID, activity_type: str, description: str, performed_by: Optional[UUID] = None, metadata: dict = None):
    timeline_event = CrmTimeline(
        contact_id=contact_id,
        activity_type=activity_type,
        description=description,
        performed_by=performed_by,
        metadata=metadata or {}
    )
    await timeline_event.insert()
    
    # Update last activity on contact
    contact = await CrmContact.get(contact_id)
    if contact:
        contact.last_activity_at = datetime.utcnow()
        await contact.save()

# =========================================================
# CONTACTS CRUD
# =========================================================

@router.post("/contacts", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_contact(data: CrmContactCreate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    # Check email uniqueness
    existing_email = await CrmContact.find_one(
        CrmContact.tenant_id == tenant_id,
        CrmContact.email == data.email,
        CrmContact.is_deleted == False
    )
    if existing_email:
        raise HTTPException(status_code=400, detail="Contact with this email already exists")

    # Check phone uniqueness (if provided)
    if data.phone:
        existing_phone = await CrmContact.find_one(
            CrmContact.tenant_id == tenant_id,
            CrmContact.phone == data.phone,
            CrmContact.is_deleted == False
        )
        if existing_phone:
            raise HTTPException(status_code=400, detail="Contact with this phone number already exists")

    # Company Association
    company_id = data.company_id
    if not company_id and data.company_name:
        # Auto-create company if name is provided
        existing_company = await CrmCompany.find_one(
            CrmCompany.tenant_id == tenant_id,
            CrmCompany.name == data.company_name
        )
        if existing_company:
            company_id = existing_company.id
        else:
            new_company = CrmCompany(
                tenant_id=tenant_id,
                name=data.company_name
            )
            await new_company.insert()
            company_id = new_company.id

    contact = CrmContact(
        tenant_id=tenant_id,
        first_name=data.first_name,
        last_name=data.last_name,
        full_name=f"{data.first_name} {data.last_name or ''}".strip(),
        email=data.email,
        phone=data.phone,
        alternate_phone=data.alternate_phone,
        company_id=company_id,
        owner_id=data.owner_id or user_id,
        job_title=data.job_title,
        department=data.department,
        website=data.website,
        address=data.address,
        city=data.city,
        state=data.state,
        country=data.country,
        postal_code=data.postal_code,
        lead_status=data.lead_status,
        lifecycle_stage=data.lifecycle_stage,
        lead_source=data.lead_source,
        tags=data.tags,
        notes=data.notes,
        created_by=user_id,
        updated_by=user_id
    )

    await contact.insert()
    
    # Log timeline event
    await log_activity(
        contact_id=contact.id,
        activity_type="contact_created",
        description=f"Contact {contact.full_name} was created by {current_user.get('name', 'Admin')}",
        performed_by=user_id
    )

    # Log notes timeline event if notes provided
    if data.notes:
        note = CrmContactNote(
            contact_id=contact.id,
            tenant_id=tenant_id,
            body=data.notes,
            created_by=user_id
        )
        await note.insert()
        await log_activity(
            contact_id=contact.id,
            activity_type="note_added",
            description="Initial contact note added.",
            performed_by=user_id,
            metadata={"note_id": str(note.id)}
        )

    return {"message": "Contact created successfully", "contact_id": str(contact.id), "data": contact}

@router.get("/contacts", response_model=Dict[str, Any])
async def list_contacts(
    is_archived: bool = False,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    sort_by: str = "created_at",
    sort_order: str = "desc",
    current_user = Depends(verify_platform_admin)
):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    
    # Base query
    query = CrmContact.find(
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_archived == is_archived,
        CrmContact.is_deleted == False
    )

    # Sort
    sort_prefix = "-" if sort_order == "desc" else ""
    query = query.sort(f"{sort_prefix}{sort_by}")

    # Count & Paginate
    total_records = await query.count()
    skip = (page - 1) * limit
    records = await query.skip(skip).limit(limit).to_list()

    # Get associated company names
    response_data = []
    for r in records:
        company_name = None
        if r.company_id:
            company = await CrmCompany.get(r.company_id)
            if company:
                company_name = company.name
        
        contact_dict = r.dict()
        contact_dict["company_name"] = company_name
        contact_dict["id"] = str(r.id)
        response_data.append(contact_dict)

    return {
        "total_records": total_records,
        "page": page,
        "limit": limit,
        "data": response_data
    }

@router.get("/contacts/{id}", response_model=Dict[str, Any])
async def get_contact(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    contact = await CrmContact.find_one(
        CrmContact.id == id,
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_deleted == False
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
        
    company_name = None
    if contact.company_id:
        company = await CrmCompany.get(contact.company_id)
        if company:
            company_name = company.name

    contact_dict = contact.dict()
    contact_dict["company_name"] = company_name
    contact_dict["id"] = str(contact.id)
    return {"data": contact_dict}

@router.put("/contacts/{id}", response_model=Dict[str, Any])
async def update_contact(id: UUID, data: CrmContactUpdate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(
        CrmContact.id == id,
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_deleted == False
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Email uniqueness check
    if data.email and data.email != contact.email:
        existing_email = await CrmContact.find_one(
            CrmContact.tenant_id == tenant_id,
            CrmContact.email == data.email,
            CrmContact.is_deleted == False
        )
        if existing_email:
            raise HTTPException(status_code=400, detail="Email is already used by another contact")

    # Phone uniqueness check
    if data.phone and data.phone != contact.phone:
        existing_phone = await CrmContact.find_one(
            CrmContact.tenant_id == tenant_id,
            CrmContact.phone == data.phone,
            CrmContact.is_deleted == False
        )
        if existing_phone:
            raise HTTPException(status_code=400, detail="Phone number is already used by another contact")

    # Perform updates
    update_dict = data.dict(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(contact, key, value)
    
    contact.full_name = f"{contact.first_name} {contact.last_name or ''}".strip()
    contact.updated_at = datetime.utcnow()
    contact.updated_by = user_id
    
    await contact.save()
    
    # Log timeline event
    await log_activity(
        contact_id=contact.id,
        activity_type="contact_updated",
        description=f"Contact details updated by {current_user.get('name', 'Admin')}",
        performed_by=user_id,
        metadata={"updates": list(update_dict.keys())}
    )

    return {"message": "Contact updated successfully", "data": contact}

@router.delete("/contacts/{id}", response_model=Dict[str, Any])
async def delete_contact(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(
        CrmContact.id == id,
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_deleted == False
    )
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.is_deleted = True
    contact.updated_at = datetime.utcnow()
    contact.updated_by = user_id
    await contact.save()

    # Log timeline event
    await log_activity(
        contact_id=contact.id,
        activity_type="contact_deleted",
        description=f"Contact soft-deleted by {current_user.get('name', 'Admin')}",
        performed_by=user_id
    )

    return {"message": "Contact deleted successfully"}

# =========================================================
# ARCHIVE & RESTORE
# =========================================================

@router.patch("/contacts/archive", response_model=Dict[str, Any])
async def archive_contacts(ids: List[UUID], current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))
    
    count = 0
    for cid in ids:
        contact = await CrmContact.find_one(
            CrmContact.id == cid,
            CrmContact.tenant_id == tenant_id,
            CrmContact.is_deleted == False
        )
        if contact and not contact.is_archived:
            contact.is_archived = True
            contact.updated_at = datetime.utcnow()
            contact.updated_by = user_id
            await contact.save()
            await log_activity(
                contact_id=contact.id,
                activity_type="contact_archived",
                description="Contact archived.",
                performed_by=user_id
            )
            count += 1
            
    return {"message": f"{count} contacts archived successfully"}

@router.patch("/contacts/restore", response_model=Dict[str, Any])
async def restore_contacts(ids: List[UUID], current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))
    
    count = 0
    for cid in ids:
        contact = await CrmContact.find_one(
            CrmContact.id == cid,
            CrmContact.tenant_id == tenant_id
        )
        if contact:
            contact.is_archived = False
            contact.is_deleted = False
            contact.updated_at = datetime.utcnow()
            contact.updated_by = user_id
            await contact.save()
            await log_activity(
                contact_id=contact.id,
                activity_type="contact_restored",
                description="Contact restored.",
                performed_by=user_id
            )
            count += 1
            
    return {"message": f"{count} contacts restored successfully"}

# =========================================================
# SEARCH & FILTERS
# =========================================================

@router.post("/contacts/search", response_model=Dict[str, Any])
async def search_contacts(data: ContactSearchRequest, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    
    query_filter = {
        "tenant_id": tenant_id,
        "is_deleted": False
    }
    
    if data.search_query:
        # Case-insensitive substring search for name, email, or phone
        sq = {"$regex": data.search_query, "$options": "i"}
        query_filter["$or"] = [
            {"first_name": sq},
            {"last_name": sq},
            {"full_name": sq},
            {"email": sq},
            {"phone": sq}
        ]

    query = CrmContact.find(query_filter)
    
    sort_prefix = "-" if data.sort_order == "desc" else ""
    query = query.sort(f"{sort_prefix}{data.sort_by}")

    total_records = await query.count()
    skip = (data.page - 1) * data.limit
    records = await query.skip(skip).limit(data.limit).to_list()

    response_data = []
    for r in records:
        company_name = None
        if r.company_id:
            company = await CrmCompany.get(r.company_id)
            if company:
                company_name = company.name
        
        contact_dict = r.dict()
        contact_dict["company_name"] = company_name
        contact_dict["id"] = str(r.id)
        response_data.append(contact_dict)

    return {
        "total_records": total_records,
        "page": data.page,
        "limit": data.limit,
        "data": response_data
    }

@router.post("/contacts/filter", response_model=Dict[str, Any])
async def filter_contacts(data: ContactFilterRequest, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    
    query_filter = {
        "tenant_id": tenant_id,
        "is_deleted": False
    }
    
    if data.lifecycle_stage:
        query_filter["lifecycle_stage"] = data.lifecycle_stage
    if data.lead_status:
        query_filter["lead_status"] = data.lead_status
    if data.owner_id:
        query_filter["owner_id"] = data.owner_id
    if data.is_archived is not None:
        query_filter["is_archived"] = data.is_archived
    if data.tags:
        query_filter["tags"] = {"$all": data.tags}

    query = CrmContact.find(query_filter)
    
    sort_prefix = "-" if data.sort_order == "desc" else ""
    query = query.sort(f"{sort_prefix}{data.sort_by}")

    total_records = await query.count()
    skip = (data.page - 1) * data.limit
    records = await query.skip(skip).limit(data.limit).to_list()

    response_data = []
    for r in records:
        company_name = None
        if r.company_id:
            company = await CrmCompany.get(r.company_id)
            if company:
                company_name = company.name
        
        contact_dict = r.dict()
        contact_dict["company_name"] = company_name
        contact_dict["id"] = str(r.id)
        response_data.append(contact_dict)

    return {
        "total_records": total_records,
        "page": data.page,
        "limit": data.limit,
        "data": response_data
    }

# =========================================================
# BULK OPERATIONS
# =========================================================

@router.post("/contacts/bulk-delete", response_model=Dict[str, Any])
async def bulk_delete_contacts(ids: List[UUID], current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))
    
    count = 0
    for cid in ids:
        contact = await CrmContact.find_one(
            CrmContact.id == cid,
            CrmContact.tenant_id == tenant_id,
            CrmContact.is_deleted == False
        )
        if contact:
            contact.is_deleted = True
            contact.updated_at = datetime.utcnow()
            contact.updated_by = user_id
            await contact.save()
            await log_activity(
                contact_id=contact.id,
                activity_type="contact_deleted",
                description="Contact deleted via bulk action.",
                performed_by=user_id
            )
            count += 1
            
    return {"message": f"{count} contacts soft-deleted successfully"}

@router.post("/contacts/bulk-update", response_model=Dict[str, Any])
async def bulk_update_contacts(data: BulkUpdateRequest, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))
    
    count = 0
    for cid in data.ids:
        contact = await CrmContact.find_one(
            CrmContact.id == cid,
            CrmContact.tenant_id == tenant_id,
            CrmContact.is_deleted == False
        )
        if contact:
            for key, val in data.updates.items():
                if hasattr(contact, key):
                    setattr(contact, key, val)
            
            contact.full_name = f"{contact.first_name} {contact.last_name or ''}".strip()
            contact.updated_at = datetime.utcnow()
            contact.updated_by = user_id
            await contact.save()
            
            await log_activity(
                contact_id=contact.id,
                activity_type="contact_updated",
                description="Contact updated via bulk action.",
                performed_by=user_id,
                metadata={"bulk_updates": list(data.updates.keys())}
            )
            count += 1
            
    return {"message": f"{count} contacts updated successfully"}

# =========================================================
# MERGE CONTACTS
# =========================================================

@router.post("/contacts/merge", response_model=Dict[str, Any])
async def merge_contacts(data: MergeRequest, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    primary = await CrmContact.find_one(
        CrmContact.id == data.primary_id,
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_deleted == False
    )
    secondary = await CrmContact.find_one(
        CrmContact.id == data.secondary_id,
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_deleted == False
    )

    if not primary or not secondary:
        raise HTTPException(status_code=404, detail="Primary or secondary contact not found")

    # Merge secondary properties into primary if primary doesn't have them
    merged_fields = []
    for field in ["phone", "alternate_phone", "company_id", "owner_id", "job_title", "department", "website", "address", "city", "state", "country", "postal_code", "notes"]:
        primary_val = getattr(primary, field, None)
        secondary_val = getattr(secondary, field, None)
        if not primary_val and secondary_val:
            setattr(primary, field, secondary_val)
            merged_fields.append(field)

    # Merge tags
    new_tags = list(set(primary.tags + secondary.tags))
    if len(new_tags) > len(primary.tags):
        primary.tags = new_tags
        merged_fields.append("tags")

    primary.updated_at = datetime.utcnow()
    primary.updated_by = user_id
    await primary.save()

    # Re-associate activities, timeline, notes, tasks, emails, calls, meetings
    await CrmTimeline.find(CrmTimeline.contact_id == secondary.id).update({"$set": {"contact_id": primary.id}})
    await CrmContactNote.find(CrmContactNote.contact_id == secondary.id).update({"$set": {"contact_id": primary.id}})
    await CrmContactCall.find(CrmContactCall.contact_id == secondary.id).update({"$set": {"contact_id": primary.id}})
    await CrmContactMeeting.find(CrmContactMeeting.contact_id == secondary.id).update({"$set": {"contact_id": primary.id}})
    await CrmContactEmail.find(CrmContactEmail.contact_id == secondary.id).update({"$set": {"contact_id": primary.id}})
    await CrmTask.find(CrmTask.lead_id == secondary.id).update({"$set": {"lead_id": primary.id}})

    # Soft delete the secondary contact
    secondary.is_deleted = True
    secondary.updated_at = datetime.utcnow()
    secondary.updated_by = user_id
    await secondary.save()

    # Log timeline event on primary
    await log_activity(
        contact_id=primary.id,
        activity_type="contact_merged",
        description=f"Merged secondary contact {secondary.full_name} ({secondary.email}) into this contact.",
        performed_by=user_id,
        metadata={"secondary_id": str(secondary.id), "merged_fields": merged_fields}
    )
    
    # Log timeline event on secondary
    await log_activity(
        contact_id=secondary.id,
        activity_type="contact_deleted",
        description=f"Contact merged into primary contact {primary.full_name} ({primary.email}).",
        performed_by=user_id
    )

    return {"message": "Contacts merged successfully", "primary_contact": primary}

# =========================================================
# AUDIT LOGS / HISTORY
# =========================================================

@router.get("/contacts/history", response_model=Dict[str, Any])
async def get_contacts_history(
    contact_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1),
    current_user = Depends(verify_platform_admin)
):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    
    # Query timeline events for contacts belonging to this tenant
    # Since Beanie doesn't do complex joins directly, we first get tenant contacts
    contact_query = CrmContact.find(CrmContact.tenant_id == tenant_id)
    if contact_id:
        contact_query = contact_query.find(CrmContact.id == contact_id)
        
    contacts = await contact_query.to_list()
    contact_ids = [c.id for c in contacts]

    timeline_query = CrmTimeline.find(
        CrmTimeline.contact_id({"$in": contact_ids})
    ).sort("-created_at")

    total_records = await timeline_query.count()
    skip = (page - 1) * limit
    events = await timeline_query.skip(skip).limit(limit).to_list()

    contact_map = {c.id: c.full_name for c in contacts}
    response_data = []
    for e in events:
        evt_dict = e.dict()
        evt_dict["id"] = str(e.id)
        evt_dict["contact_name"] = contact_map.get(e.contact_id, "Unknown Contact")
        response_data.append(evt_dict)

    return {
        "total_records": total_records,
        "page": page,
        "limit": limit,
        "data": response_data
    }

# =========================================================
# CSV IMPORT & EXPORT
# =========================================================

@router.post("/contacts/import", response_model=Dict[str, Any])
async def import_contacts(file: UploadFile = File(...), current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    content = await file.read()
    file_io = io.StringIO(content.decode("utf-8"))
    reader = csv.DictReader(file_io)

    success_count = 0
    duplicate_count = 0
    error_count = 0

    for row in reader:
        email = row.get("email", "").strip().lower()
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        phone = row.get("phone", "").strip()
        
        if not email or not first_name:
            error_count += 1
            continue

        try:
            # Check unique email
            existing = await CrmContact.find_one(
                CrmContact.tenant_id == tenant_id,
                CrmContact.email == email,
                CrmContact.is_deleted == False
            )
            if existing:
                duplicate_count += 1
                continue

            company_name = row.get("company", "").strip()
            company_id = None
            if company_name:
                company = await CrmCompany.find_one(
                    CrmCompany.tenant_id == tenant_id,
                    CrmCompany.name == company_name
                )
                if company:
                    company_id = company.id
                else:
                    new_company = CrmCompany(tenant_id=tenant_id, name=company_name)
                    await new_company.insert()
                    company_id = new_company.id

            contact = CrmContact(
                tenant_id=tenant_id,
                first_name=first_name,
                last_name=last_name,
                full_name=f"{first_name} {last_name}".strip(),
                email=email,
                phone=phone or None,
                company_id=company_id,
                owner_id=user_id,
                job_title=row.get("job_title", "").strip() or None,
                department=row.get("department", "").strip() or None,
                website=row.get("website", "").strip() or None,
                lead_status=row.get("lead_status", "new").strip().lower(),
                lifecycle_stage=row.get("lifecycle_stage", "lead").strip().lower(),
                lead_source=row.get("lead_source", "import").strip().lower(),
                tags=[t.strip() for t in row.get("tags", "").split(";")] if row.get("tags") else [],
                created_by=user_id,
                updated_by=user_id
            )
            await contact.insert()
            await log_activity(
                contact_id=contact.id,
                activity_type="contact_created",
                description="Contact imported via CSV.",
                performed_by=user_id
            )
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to import row: {row} | Error: {str(e)}")
            error_count += 1

    return {
        "success_count": success_count,
        "duplicate_count": duplicate_count,
        "error_count": error_count,
        "message": f"Import completed: {success_count} success, {duplicate_count} skipped duplicates, {error_count} errors"
    }

@router.get("/contacts/export")
async def export_contacts(current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))

    contacts = await CrmContact.find(
        CrmContact.tenant_id == tenant_id,
        CrmContact.is_deleted == False
    ).to_list()

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Headers
    writer.writerow([
        "first_name", "last_name", "full_name", "email", "phone", 
        "company", "job_title", "department", "website", 
        "lead_status", "lifecycle_stage", "lead_source", "tags", "created_at"
    ])

    for c in contacts:
        company_name = ""
        if c.company_id:
            company = await CrmCompany.get(c.company_id)
            if company:
                company_name = company.name
                
        writer.writerow([
            c.first_name,
            c.last_name or "",
            c.full_name or "",
            c.email,
            c.phone or "",
            company_name,
            c.job_title or "",
            c.department or "",
            c.website or "",
            c.lead_status or "",
            c.lifecycle_stage or "",
            c.lead_source or "",
            ";".join(c.tags),
            c.created_at.isoformat()
        ])

    output.seek(0)
    response = StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=crm_contacts_export.csv"
    return response

# =========================================================
# TIMELINE & SUB-ACTIVITIES
# =========================================================

@router.get("/contacts/{id}/timeline", response_model=Dict[str, Any])
async def get_contact_timeline(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    timeline = await CrmTimeline.find(CrmTimeline.contact_id == id).sort("-created_at").to_list()
    return {"data": timeline}

@router.post("/contacts/{id}/notes", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_contact_note(id: UUID, data: CrmContactNoteCreate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    note = CrmContactNote(
        contact_id=id,
        tenant_id=tenant_id,
        body=data.body,
        created_by=user_id
    )
    await note.insert()
    
    await log_activity(
        contact_id=id,
        activity_type="note_added",
        description=f"New note added by {current_user.get('name', 'Admin')}",
        performed_by=user_id,
        metadata={"note_id": str(note.id), "body_preview": data.body[:100]}
    )

    return {"message": "Note added successfully", "data": note}

@router.get("/contacts/{id}/notes", response_model=Dict[str, Any])
async def get_contact_notes(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    notes = await CrmContactNote.find(
        CrmContactNote.contact_id == id,
        CrmContactNote.tenant_id == tenant_id
    ).sort("-created_at").to_list()
    return {"data": notes}

@router.put("/notes/{note_id}", response_model=Dict[str, Any])
async def update_note(note_id: UUID, data: CrmContactNoteCreate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    note = await CrmContactNote.find_one(CrmContactNote.id == note_id, CrmContactNote.tenant_id == tenant_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    note.body = data.body
    note.updated_at = datetime.utcnow()
    await note.save()
    
    await log_activity(
        contact_id=note.contact_id,
        activity_type="note_updated",
        description=f"Note updated by {current_user.get('name', 'Admin')}",
        performed_by=UUID(current_user.get('sub'))
    )
    return {"message": "Note updated successfully", "data": note}

@router.delete("/notes/{note_id}", response_model=Dict[str, Any])
async def delete_note(note_id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    note = await CrmContactNote.find_one(CrmContactNote.id == note_id, CrmContactNote.tenant_id == tenant_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    await note.delete()
    
    await log_activity(
        contact_id=note.contact_id,
        activity_type="note_deleted",
        description=f"Note deleted by {current_user.get('name', 'Admin')}",
        performed_by=UUID(current_user.get('sub'))
    )
    return {"message": "Note deleted successfully"}

@router.post("/contacts/{id}/calls", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def log_contact_call(id: UUID, data: CrmContactCallCreate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    call = CrmContactCall(
        contact_id=id,
        tenant_id=tenant_id,
        subject=data.subject,
        notes=data.notes,
        outcome=data.outcome,
        duration_seconds=data.duration_seconds,
        created_by=user_id
    )
    await call.insert()
    
    await log_activity(
        contact_id=id,
        activity_type="call_completed",
        description=f"Call logged: {data.subject} ({data.outcome})",
        performed_by=user_id,
        metadata={"call_id": str(call.id), "outcome": data.outcome, "duration": data.duration_seconds}
    )
    return {"message": "Call logged successfully", "data": call}

@router.get("/contacts/{id}/calls", response_model=Dict[str, Any])
async def get_contact_calls(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    calls = await CrmContactCall.find(
        CrmContactCall.contact_id == id,
        CrmContactCall.tenant_id == tenant_id
    ).sort("-created_at").to_list()
    return {"data": calls}

@router.post("/contacts/{id}/meetings", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def log_contact_meeting(id: UUID, data: CrmContactMeetingCreate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    meeting = CrmContactMeeting(
        contact_id=id,
        tenant_id=tenant_id,
        title=data.title,
        description=data.description,
        start_time=data.start_time,
        end_time=data.end_time,
        outcome=data.outcome,
        created_by=user_id
    )
    await meeting.insert()
    
    await log_activity(
        contact_id=id,
        activity_type="meeting_scheduled",
        description=f"Meeting logged: {data.title} ({data.outcome})",
        performed_by=user_id,
        metadata={"meeting_id": str(meeting.id), "outcome": data.outcome, "start": data.start_time.isoformat()}
    )
    return {"message": "Meeting logged successfully", "data": meeting}

@router.get("/contacts/{id}/meetings", response_model=Dict[str, Any])
async def get_contact_meetings(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    meetings = await CrmContactMeeting.find(
        CrmContactMeeting.contact_id == id,
        CrmContactMeeting.tenant_id == tenant_id
    ).sort("-created_at").to_list()
    return {"data": meetings}

@router.post("/contacts/{id}/tasks", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def create_contact_task(id: UUID, data: Dict[str, Any], current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Save as standard CrmTask
    due_date_parsed = None
    if data.get("due_date"):
        due_date_parsed = datetime.fromisoformat(data["due_date"].replace("Z", "+00:00"))

    task = CrmTask(
        tenant_id=tenant_id,
        lead_id=id,
        title=data["title"],
        description=data.get("description"),
        due_date=due_date_parsed,
        priority=Priority(data.get("priority", "warm")),
        assigned_to=UUID(data.get("assigned_to")) if data.get("assigned_to") else user_id,
        status="pending"
    )
    await task.insert()

    await log_activity(
        contact_id=id,
        activity_type="task_created",
        description=f"Task created: {task.title}",
        performed_by=user_id,
        metadata={"task_id": str(task.id), "due_date": due_date_parsed.isoformat() if due_date_parsed else None}
    )
    return {"message": "Task created successfully", "data": task}

@router.get("/contacts/{id}/tasks", response_model=Dict[str, Any])
async def get_contact_tasks(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    # First get the contact to find its lead_id
    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    lead_id = contact.lead_id if contact else None
    
    # Build OR query: match by contact_id or by lead_id
    query_filter = {"tenant_id": str(tenant_id), "$or": [{"contact_id": str(id)}]}
    if lead_id:
        query_filter["$or"].append({"lead_id": str(lead_id)})
    
    tasks = await CrmTask.find(
        CrmTask.tenant_id == tenant_id
    ).to_list()
    # Filter manually for contact_id OR lead_id
    filtered = [t for t in tasks if str(getattr(t, 'contact_id', None)) == str(id) or (lead_id and str(getattr(t, 'lead_id', None)) == str(lead_id))]
    filtered.sort(key=lambda t: t.created_at, reverse=True)
    return {"data": filtered}

@router.get("/contacts/{id}/deals", response_model=Dict[str, Any])
async def get_contact_deals(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    deals = []
    if contact.lead_id:
        deals = await CrmDeal.find(
            CrmDeal.lead_id == contact.lead_id,
            CrmDeal.tenant_id == tenant_id
        ).sort("-created_at").to_list()
    return {"data": deals}

@router.get("/contacts/{id}/documents", response_model=Dict[str, Any])
async def get_contact_documents(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    
    # Documents stored directly on the contact document (copied from lead on conversion)
    documents = contact.documents or []
    return {"data": documents}

@router.post("/contacts/{id}/emails", response_model=Dict[str, Any], status_code=status.HTTP_201_CREATED)
async def log_contact_email(id: UUID, data: CrmContactEmailCreate, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    user_id = UUID(current_user.get('sub'))

    contact = await CrmContact.find_one(CrmContact.id == id, CrmContact.tenant_id == tenant_id, CrmContact.is_deleted == False)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    email = CrmContactEmail(
        contact_id=id,
        tenant_id=tenant_id,
        subject=data.subject,
        body=data.body,
        direction=data.direction,
        created_by=user_id
    )
    await email.insert()
    
    await log_activity(
        contact_id=id,
        activity_type="email_sent" if data.direction == "outbound" else "email_received",
        description=f"Email {data.direction}: {data.subject}",
        performed_by=user_id,
        metadata={"email_id": str(email.id), "subject": data.subject}
    )
    return {"message": "Email logged successfully", "data": email}

@router.get("/contacts/{id}/emails", response_model=Dict[str, Any])
async def get_contact_emails(id: UUID, current_user = Depends(verify_platform_admin)):
    tenant_id = UUID(current_user.get('tid') or current_user.get('tenant_id'))
    emails = await CrmContactEmail.find(
        CrmContactEmail.contact_id == id,
        CrmContactEmail.tenant_id == tenant_id
    ).sort("-created_at").to_list()
    return {"data": emails}
