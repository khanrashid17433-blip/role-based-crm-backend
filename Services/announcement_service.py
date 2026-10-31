from uuid import UUID
from datetime import datetime, timezone, timedelta
from Models.announcement import CompanyAnnouncement, CompanyAnnouncementReadStatus
from Schema.announcement import AnnouncementCreate, AnnouncementResponse, AnnouncementStats, AnnouncementsListResponse
from Models.tenant_user import User
from Models.employee import Employee

class AnnouncementService:
    @staticmethod
    async def create_announcement(tenant_id: UUID, user_id: UUID, data: AnnouncementCreate) -> AnnouncementResponse:
        # Fetch author details
        author_name = "Admin"
        try:
            author = await User.get(user_id)
            if author:
                if author.display_name:
                    author_name = author.display_name
                elif author.first_name:
                    author_name = f"{author.first_name} {author.last_name}".strip()
        except Exception:
            pass

        announcement = CompanyAnnouncement(
            tenant_id=tenant_id,
            title=data.title,
            content=data.content,
            type=data.type,
            author_id=user_id,
            author_name=author_name
        )
        await announcement.insert()
        
        return AnnouncementResponse(
            id=str(announcement.id),
            title=announcement.title,
            content=announcement.content,
            type=announcement.type,
            author_id=str(announcement.author_id),
            author_name=announcement.author_name,
            created_at=announcement.created_at,
            is_read=True # Creator inherently read it
        )

    @staticmethod
    async def get_announcements_for_employee(tenant_id: UUID, employee_id: UUID) -> AnnouncementsListResponse:
        from Models.note import Note
        
        # Fetch all standard announcements
        announcements = await CompanyAnnouncement.find(CompanyAnnouncement.tenant_id == tenant_id).sort(-CompanyAnnouncement.created_at).to_list()
        
        # Fetch all users in this tenant who have administrative or HR roles
        admin_users = await User.find({
            "tenant_id": tenant_id,
            "$or": [
                {"role": {"$in": ["admin", "hr_admin", "hr_manager", "hr", "tenant_admin", "super_admin", "platform_admin"]}},
                {"user_type": {"$in": ["platform_admin", "tenant_admin", "admin_user"]}}
            ]
        }).to_list()
        admin_user_ids = {u.id for u in admin_users}
        
        # Mapping user_id to display name
        user_names = {}
        for u in admin_users:
            name = "Admin"
            if u.display_name:
                name = u.display_name
            elif u.first_name:
                name = f"{u.first_name} {u.last_name}".strip()
            user_names[u.id] = name
            
        # Retrieve all top-level, non-deleted notes created by these admin/HR users for the specific project resource
        notes = []
        if admin_user_ids:
            notes = await Note.find({
                "tenant_id": tenant_id,
                "resource_type": "project",
                "resource_id": UUID("00000000-0000-0000-0000-000000000021"),
                "parent_note_id": None,
                "author_id": {"$in": list(admin_user_ids)},
                "is_deleted": False
            }).to_list()
            
        read_statuses = await CompanyAnnouncementReadStatus.find(CompanyAnnouncementReadStatus.employee_id == employee_id).to_list()
        read_announcement_ids = {str(rs.announcement_id) for rs in read_statuses}
        
        # Identify note_ids that are already linked to CompanyAnnouncement to avoid duplicates
        existing_note_ids = {ann.note_id for ann in announcements if ann.note_id is not None}
        
        combined = []
        for ann in announcements:
            is_read = str(ann.id) in read_announcement_ids
            combined.append({
                "id": ann.id,
                "title": ann.title,
                "content": ann.content,
                "type": ann.type,
                "author_id": ann.author_id,
                "author_name": ann.author_name,
                "created_at": ann.created_at,
                "is_read": is_read
            })
            
        for note in notes:
            if note.id in existing_note_ids:
                continue
            is_read = str(note.id) in read_announcement_ids
            
            # Derive title from the first line
            body_plain_clean = note.body_plain.strip() if note.body_plain else ""
            first_line = body_plain_clean.split('\n')[0].strip() if body_plain_clean else "Announcement"
            title = first_line[:200] if len(first_line) > 0 else "Announcement"
            
            author_name = user_names.get(note.author_id, "Admin")
            
            combined.append({
                "id": note.id,
                "title": title,
                "content": body_plain_clean or note.body_html,
                "type": note.note_type,
                "author_id": note.author_id,
                "author_name": author_name,
                "created_at": note.created_at,
                "is_read": is_read
            })
            
        # Sort combined list by created_at descending
        combined.sort(key=lambda x: x["created_at"], reverse=True)
        
        now = datetime.utcnow()
        one_week_ago = now - timedelta(days=7)
        
        total = len(combined)
        unread = 0
        important = 0
        this_week = 0
        
        response_list = []
        
        for item in combined:
            if not item["is_read"]:
                unread += 1
            if str(item["type"]).lower() == "important":
                important += 1
            
            # Make created_at naive for simple comparison if it's aware
            ann_created = item["created_at"].replace(tzinfo=None) if item["created_at"].tzinfo else item["created_at"]
            
            if ann_created >= one_week_ago:
                this_week += 1
                
            response_list.append(AnnouncementResponse(
                id=str(item["id"]),
                title=item["title"],
                content=item["content"],
                type=item["type"],
                author_id=str(item["author_id"]),
                author_name=item["author_name"],
                created_at=item["created_at"],
                is_read=item["is_read"]
            ))
            
        stats = AnnouncementStats(
            total=total,
            unread=unread,
            important=important,
            this_week=this_week
        )
        
        return AnnouncementsListResponse(stats=stats, announcements=response_list)

    @staticmethod
    async def mark_as_read(announcement_id: UUID, employee_id: UUID) -> bool:
        existing = await CompanyAnnouncementReadStatus.find_one(
            CompanyAnnouncementReadStatus.announcement_id == announcement_id,
            CompanyAnnouncementReadStatus.employee_id == employee_id
        )
        if not existing:
            status = CompanyAnnouncementReadStatus(
                announcement_id=announcement_id,
                employee_id=employee_id
            )
            await status.insert()
        return True
