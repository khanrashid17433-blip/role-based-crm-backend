import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from beanie.operators import In

from Models.crm_task import CrmTask
from Models.tenant_user import User

logger = logging.getLogger(__name__)

class TaskService:
    
    @staticmethod
    async def create_task(data: dict, user_id: UUID, tenant_id: UUID) -> CrmTask:
        """Create a new task"""
        task = CrmTask(
            tenant_id=tenant_id,
            title=data.get("title"),
            description=data.get("description"),
            type=data.get("type", "task"),
            priority=data.get("priority", "medium"),
            status=data.get("status", "not_started"),
            owner_id=UUID(data["owner_id"]) if data.get("owner_id") else user_id,
            assigned_to=UUID(data["assigned_to"]) if data.get("assigned_to") else None,
            lead_id=UUID(data["lead_id"]) if data.get("lead_id") else None,
            contact_id=UUID(data["contact_id"]) if data.get("contact_id") else None,
            deal_id=UUID(data["deal_id"]) if data.get("deal_id") else None,
            company_id=UUID(data["company_id"]) if data.get("company_id") else None,
            due_date=data.get("due_date"),
            due_time=data.get("due_time"),
            reminder_time=data.get("reminder_time"),
            reminder_type=data.get("reminder_type"),
            repeat=data.get("repeat"),
            notes=data.get("notes"),
            estimated_time=data.get("estimated_time"),
            checklist=data.get("checklist", []),
            attachments=data.get("attachments", []),
            created_by=user_id,
            updated_by=user_id
        )
        created = await task.insert()
        return created

    @staticmethod
    async def get_task(task_id: UUID, tenant_id: UUID) -> Optional[CrmTask]:
        """Get a single task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        return task

    @staticmethod
    async def update_task(task_id: UUID, data: dict, tenant_id: UUID, user_id: UUID) -> Optional[CrmTask]:
        """Update a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        update_fields = [
            "title", "description", "type", "priority", "status",
            "due_date", "due_time", "reminder_time", "reminder_type",
            "repeat", "notes", "estimated_time", "checklist"
        ]
        
        for field in update_fields:
            if field in data and data[field] is not None:
                setattr(task, field, data[field])
        
        # Handle UUID fields
        uuid_fields = ["owner_id", "assigned_to", "lead_id", "contact_id", "deal_id", "company_id"]
        for field in uuid_fields:
            if field in data and data[field]:
                setattr(task, field, UUID(data[field]))
            elif field in data and data[field] is None:
                setattr(task, field, None)
        
        task.updated_by = user_id
        task.updated_at = datetime.utcnow()
        
        # If status changed to completed, set completed_at
        if data.get("status") == "completed" and task.status != "completed":
            task.completed_at = datetime.utcnow()
        elif data.get("status") and data["status"] != "completed":
            task.completed_at = None
        
        await task.save()
        return task

    @staticmethod
    async def complete_task(task_id: UUID, tenant_id: UUID) -> Optional[CrmTask]:
        """Mark task as completed"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def update_task_status(task_id: UUID, status: str, tenant_id: UUID) -> Optional[CrmTask]:
        """Update task status"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        task.status = status
        task.updated_at = datetime.utcnow()
        if status == "completed":
            task.completed_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def update_task_priority(task_id: UUID, priority: str, tenant_id: UUID) -> Optional[CrmTask]:
        """Update task priority"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        task.priority = priority
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def delete_task(task_id: UUID, tenant_id: UUID) -> bool:
        """Delete a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return False
        await task.delete()
        return True

    @staticmethod
    async def archive_task(task_id: UUID, tenant_id: UUID) -> Optional[CrmTask]:
        """Archive a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        task.archived_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def duplicate_task(task_id: UUID, tenant_id: UUID, user_id: UUID) -> Optional[CrmTask]:
        """Duplicate a task"""
        original = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not original:
            return None
        
        new_task = CrmTask(
            tenant_id=tenant_id,
            title=f"{original.title} (Copy)",
            description=original.description,
            type=original.type,
            priority=original.priority,
            status="not_started",
            owner_id=original.owner_id or user_id,
            assigned_to=original.assigned_to,
            lead_id=original.lead_id,
            contact_id=original.contact_id,
            deal_id=original.deal_id,
            company_id=original.company_id,
            due_date=original.due_date,
            due_time=original.due_time,
            notes=original.notes,
            estimated_time=original.estimated_time,
            checklist=[{**item, "completed": False} for item in (original.checklist or [])],
            created_by=user_id,
            updated_by=user_id
        )
        created = await new_task.insert()
        return created

    @staticmethod
    async def get_tasks(
        tenant_id: UUID,
        filters: dict = None,
        page: int = 1,
        limit: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Tuple[List[CrmTask], int]:
        """Get tasks with filtering and pagination"""
        query = {"tenant_id": tenant_id, "archived_at": None}
        
        if filters:
            for key in ["status", "priority", "type"]:
                if filters.get(key):
                    query[key] = filters[key]
            
            for key in ["owner_id", "assigned_to", "lead_id", "contact_id", "deal_id", "company_id"]:
                if filters.get(key):
                    query[key] = UUID(filters[key])
            
            # Date range
            if filters.get("due_date_from") or filters.get("due_date_to"):
                due_date_query = {}
                if filters.get("due_date_from"):
                    due_date_query["$gte"] = filters["due_date_from"]
                if filters.get("due_date_to"):
                    due_date_query["$lte"] = filters["due_date_to"]
                if due_date_query:
                    query["due_date"] = due_date_query
            
            # Associated type filter
            if filters.get("associated_type"):
                atype = filters["associated_type"].lower()
                if atype == "lead":
                    query["lead_id"] = {"$ne": None}
                elif atype == "contact":
                    query["contact_id"] = {"$ne": None}
                elif atype == "deal":
                    query["deal_id"] = {"$ne": None}
                elif atype == "company":
                    query["company_id"] = {"$ne": None}
            
            # Search
            if filters.get("search"):
                search = filters["search"]
                query["$or"] = [
                    {"title": {"$regex": search, "$options": "i"}},
                ]
        
        sort_direction = 1 if sort_order == "asc" else -1
        skip = (page - 1) * limit
        
        total = await CrmTask.find(query).count()
        tasks = await CrmTask.find(query).sort((sort_by, sort_direction)).skip(skip).limit(limit).to_list()
        
        return tasks, total

    @staticmethod
    async def get_task_counts(tenant_id: UUID, user_id: UUID = None) -> Dict[str, int]:
        """Get task counts for dashboard cards"""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        week_end = today_start + timedelta(days=7)
        
        base_query = {"tenant_id": tenant_id, "archived_at": None}
        
        if user_id:
            base_query["$or"] = [{"owner_id": user_id}, {"assigned_to": user_id}]
        
        total = await CrmTask.find(base_query).count()
        
        pending_query = {**base_query, "status": {"$in": ["not_started", "in_progress", "waiting"]}}
        pending = await CrmTask.find(pending_query).count()
        
        completed_query = {**base_query, "status": "completed"}
        completed = await CrmTask.find(completed_query).count()
        
        overdue_query = {
            **base_query,
            "due_date": {"$lt": now},
            "status": {"$ne": "completed"}
        }
        overdue = await CrmTask.find(overdue_query).count()
        
        due_today_query = {
            **base_query,
            "due_date": {"$gte": today_start, "$lt": today_end},
            "status": {"$ne": "completed"}
        }
        due_today = await CrmTask.find(due_today_query).count()
        
        due_week_query = {
            **base_query,
            "due_date": {"$gte": today_start, "$lt": week_end},
            "status": {"$ne": "completed"}
        }
        due_week = await CrmTask.find(due_week_query).count()
        
        high_priority_query = {
            **base_query,
            "priority": {"$in": ["high", "urgent"]},
            "status": {"$ne": "completed"}
        }
        high_priority = await CrmTask.find(high_priority_query).count()
        
        my_tasks_query = {}
        if user_id:
            my_tasks_query = {
                "tenant_id": tenant_id,
                "archived_at": None,
                "$or": [{"owner_id": user_id}, {"assigned_to": user_id}],
                "status": {"$ne": "completed"}
            }
            my_tasks = await CrmTask.find(my_tasks_query).count()
        else:
            my_tasks = 0
        
        return {
            "total": total,
            "pending": pending,
            "completed": completed,
            "overdue": overdue,
            "due_today": due_today,
            "due_week": due_week,
            "high_priority": high_priority,
            "my_tasks": my_tasks
        }

    @staticmethod
    async def add_comment(task_id: UUID, tenant_id: UUID, user_id: UUID, text: str, mentions: list = None, parent_id: str = None) -> Optional[CrmTask]:
        """Add a comment to a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        from uuid import uuid4
        comment = {
            "id": str(uuid4()),
            "text": text,
            "user_id": str(user_id),
            "mentions": mentions or [],
            "parent_id": parent_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if not task.comments:
            task.comments = []
        task.comments.append(comment)
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def delete_comment(task_id: UUID, comment_id: str, tenant_id: UUID) -> Optional[CrmTask]:
        """Delete a comment from a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        task.comments = [c for c in (task.comments or []) if c.get("id") != comment_id]
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def update_comment(task_id: UUID, comment_id: str, tenant_id: UUID, text: str) -> Optional[CrmTask]:
        """Update a comment text"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        for comment in (task.comments or []):
            if comment.get("id") == comment_id:
                comment["text"] = text
                comment["updated_at"] = datetime.utcnow().isoformat()
                break
        
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def add_attachment(task_id: UUID, tenant_id: UUID, file_name: str, file_url: str, file_size: str = None, file_type: str = None) -> Optional[CrmTask]:
        """Add an attachment to a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        attachment = {
            "id": str(UUID.v4()),
            "file_name": file_name,
            "file_url": file_url,
            "file_size": file_size,
            "file_type": file_type,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        if not task.attachments:
            task.attachments = []
        task.attachments.append(attachment)
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def delete_attachment(task_id: UUID, attachment_id: str, tenant_id: UUID) -> Optional[CrmTask]:
        """Delete an attachment from a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        task.attachments = [a for a in (task.attachments or []) if a.get("id") != attachment_id]
        task.updated_at = datetime.utcnow()
        await task.save()
        return task

    @staticmethod
    async def update_checklist(task_id: UUID, tenant_id: UUID, checklist: list) -> Optional[CrmTask]:
        """Update checklist items for a task"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        task.checklist = checklist
        task.updated_at = datetime.utcnow()
        await task.save()
        return task
    
    @staticmethod
    async def auto_create_task(tenant_id: UUID, title: str, task_type: str, priority: str,
                               due_date: datetime, owner_id: UUID, created_by: UUID,
                               lead_id: UUID = None, deal_id: UUID = None,
                               contact_id: UUID = None, company_id: UUID = None) -> CrmTask:
        """Auto-create a task from other CRM actions (demo, meeting, proposal, etc.)"""
        task = CrmTask(
            tenant_id=tenant_id,
            title=title,
            type=task_type,
            priority=priority,
            status="not_started",
            owner_id=owner_id,
            assigned_to=owner_id,
            lead_id=lead_id,
            deal_id=deal_id,
            contact_id=contact_id,
            company_id=company_id,
            due_date=due_date,
            created_by=created_by,
            updated_by=created_by
        )
        created = await task.insert()
        return created

    @staticmethod
    async def get_workspace_task(task_id: UUID, tenant_id: UUID) -> Optional[Dict[str, Any]]:
        """Get full task workspace data with associated records"""
        task = await CrmTask.find_one(CrmTask.id == task_id, CrmTask.tenant_id == tenant_id)
        if not task:
            return None
        
        result = {
            "task": task.dict(),
            "owner": None,
            "assigned_user": None,
            "lead": None,
            "contact": None,
            "deal": None
        }
        
        # Get associated records
        if task.lead_id:
            from Models.crm import CrmLead
            lead = await CrmLead.find_one(CrmLead.id == task.lead_id)
            if lead:
                result["lead"] = {"id": str(lead.id), "first_name": lead.first_name, "last_name": lead.last_name, "company_name": lead.company_name}
        
        if task.contact_id:
            from Models.crm_contacts import CrmContact
            contact = await CrmContact.find_one(CrmContact.id == task.contact_id)
            if contact:
                result["contact"] = {"id": str(contact.id), "first_name": contact.first_name, "last_name": contact.last_name}
        
        if task.deal_id:
            from Models.crm import CrmDeal
            deal = await CrmDeal.find_one(CrmDeal.id == task.deal_id)
            if deal:
                result["deal"] = {"id": str(deal.id), "deal_name": deal.deal_name, "stage": deal.stage.value if hasattr(deal.stage, 'value') else deal.stage}
        
        # Get owner info
        if task.owner_id:
            owner = await User.find_one(User.id == task.owner_id)
            if owner:
                result["owner"] = {"id": str(owner.id), "name": f"{owner.first_name} {owner.last_name}", "email": owner.email}
        
        if task.assigned_to and task.assigned_to != task.owner_id:
            assigned = await User.find_one(User.id == task.assigned_to)
            if assigned:
                result["assigned_user"] = {"id": str(assigned.id), "name": f"{assigned.first_name} {assigned.last_name}", "email": assigned.email}
        
        return result