from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging
import os
from uuid import UUID

from Models.note import Note, NoteMention, NoteReaction, NoteEdit
from Schema.note import NoteCreateRequest, NoteUpdateRequest, ReactionRequest

logger = logging.getLogger(__name__)

class NoteService:
    ALLOWED_NOTE_TYPES = {"general", "important", "client_communication", "internal_only", "announcement"}
    ALLOWED_VISIBILITY = {"internal", "client_visible"}
    ALLOWED_REACTIONS = {"\U0001F44D", "\u2705", "\U0001F6A8", "\u2753"}

    @staticmethod
    def _edit_window_minutes() -> int:
        try:
            return int(os.getenv("NOTE_EDIT_WINDOW_MINUTES", "15"))
        except ValueError:
            return 15

    @staticmethod
    def _validate_note_fields(note_type: str, visibility: str) -> None:
        if note_type not in NoteService.ALLOWED_NOTE_TYPES:
            raise ValueError("Invalid note type")
        if visibility not in NoteService.ALLOWED_VISIBILITY:
            raise ValueError("Invalid visibility")

    @staticmethod
    def _serialize_note(note: Note, replies=None, reactions=None, mentions=None, attachments=None, seen_count=0) -> Dict[str, Any]:
        return {
            "id": str(note.id),
            "tenant_id": str(note.tenant_id),
            "resource_type": note.resource_type,
            "resource_id": str(note.resource_id),
            "parent_note_id": str(note.parent_note_id) if note.parent_note_id else None,
            "author_id": str(note.author_id),
            "body_html": note.body_html,
            "body_plain": note.body_plain,
            "note_type": note.note_type,
            "visibility": note.visibility,
            "is_pinned": note.is_pinned,
            "is_deleted": note.is_deleted,
            "created_at": note.created_at.isoformat(),
            "updated_at": note.updated_at.isoformat(),
            "replies": replies or [],
            "reactions": reactions or [],
            "mentions": mentions or [],
            "attachments": attachments or [],
            "seen_count": seen_count,
            "can_edit_until": (
                note.created_at.timestamp() + (NoteService._edit_window_minutes() * 60)
            ),
        }
    
    @staticmethod
    async def create_note(tenant_id: UUID, author_id: UUID, data: NoteCreateRequest) -> Note:
        NoteService._validate_note_fields(data.note_type, data.visibility)
        
        # Enforce max 3 levels of threading
        if data.parent_note_id:
            parent = await Note.find_one(Note.id == data.parent_note_id)
            if not parent:
                from Models.ticket import Ticket, TicketComment, TicketActivity
                ticket = await Ticket.find_one(Ticket.id == data.parent_note_id)
                if ticket:
                    from Models.tenant_user import User
                    user_name = "Admin"
                    user_role = "Staff"
                    user_obj = await User.get(author_id)
                    if user_obj:
                        user_name = user_obj.display_name or f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.email
                        user_role = user_obj.role or "Staff"
                        
                    avatar_letter = "".join([part[0].upper() for part in user_name.split() if part])[:2]
                    if not avatar_letter:
                        avatar_letter = "U"
                        
                    comment = TicketComment(
                        sender=user_name,
                        role=user_role,
                        text=data.body_plain,
                        time=datetime.utcnow(),
                        avatar_letter=avatar_letter,
                        user_id=author_id
                    )
                    if not ticket.comments:
                        ticket.comments = []
                    ticket.comments.append(comment)
                    
                    ticket.activity.append(
                        TicketActivity(
                            action="Added comment from Notes System",
                            time=datetime.utcnow(),
                            user_name=user_name
                        )
                    )
                    await ticket.save()
                    
                    mock_note = Note(
                        id=author_id,
                        tenant_id=tenant_id,
                        resource_type=data.resource_type,
                        resource_id=data.resource_id,
                        parent_note_id=data.parent_note_id,
                        author_id=author_id,
                        body_html=data.body_html,
                        body_plain=data.body_plain,
                        note_type='general',
                        visibility='internal',
                        is_pinned=False
                    )
                    return mock_note
                else:
                    raise ValueError("Parent note not found")
                
            # If parent already has a parent, check depth.
            # Depth 1: No parent. Depth 2: Has parent. Depth 3: Parent has parent.
            if parent.parent_note_id:
                grandparent = await Note.find_one(Note.id == parent.parent_note_id)
                if grandparent and grandparent.parent_note_id:
                    raise ValueError("Maximum thread depth (3 levels) reached")

        note = Note(
            tenant_id=tenant_id,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            parent_note_id=data.parent_note_id,
            author_id=author_id,
            body_html=data.body_html,
            body_plain=data.body_plain,
            note_type=data.note_type,
            visibility=data.visibility,
            is_pinned=data.is_pinned
        )
        await note.insert()

        if data.note_type == "announcement":
            try:
                from Models.announcement import CompanyAnnouncement
                from Models.tenant_user import User
                
                author_name = "Admin"
                user_obj = await User.get(author_id)
                if user_obj:
                    if user_obj.display_name:
                        author_name = user_obj.display_name
                    elif user_obj.first_name:
                        author_name = f"{user_obj.first_name} {user_obj.last_name}".strip()
                
                body_plain_clean = data.body_plain.strip() if data.body_plain else ""
                first_line = body_plain_clean.split('\n')[0].strip() if body_plain_clean else "Announcement"
                title = first_line[:200] if len(first_line) > 0 else "Announcement"
                
                announcement = CompanyAnnouncement(
                    tenant_id=tenant_id,
                    title=title,
                    content=body_plain_clean or data.body_html,
                    type="general",
                    author_id=author_id,
                    author_name=author_name,
                    note_id=note.id
                )
                await announcement.insert()
            except Exception as e:
                logger.error(f"Failed to sync announcement from note: {e}", exc_info=True)
        
        for user_id in data.mentions:
            mention = NoteMention(
                note_id=note.id,
                mentioned_user_id=user_id,
                notified_at=datetime.utcnow()
            )
            await mention.insert()
            # Notification dispatchers can consume note_mentions.notified_at.
            
        return note

    @staticmethod
    async def update_note(tenant_id: UUID, note_id: UUID, author_id: UUID, data: NoteUpdateRequest) -> Note:
        note = await Note.find_one(
            Note.id == note_id,
            Note.tenant_id == tenant_id
        )
        if not note:
            raise ValueError("Note not found")
            
        if note.author_id != author_id:
            raise ValueError("Only the author can edit this note")

        if note.is_deleted:
            raise ValueError("Deleted notes cannot be edited")
            
        delta = datetime.utcnow() - note.created_at
        if delta.total_seconds() > (NoteService._edit_window_minutes() * 60):
            raise ValueError(f"Notes can only be edited within {NoteService._edit_window_minutes()} minutes of creation")

        next_note_type = data.note_type if data.note_type is not None else note.note_type
        next_visibility = data.visibility if data.visibility is not None else note.visibility
        NoteService._validate_note_fields(next_note_type, next_visibility)

        if data.body_html is not None and data.body_html != note.body_html:
            edit = NoteEdit(
                note_id=note.id,
                previous_html=note.body_html,
                edited_by=author_id
            )
            await edit.insert()

        if data.body_html is not None:
            note.body_html = data.body_html
        if data.body_plain is not None:
            note.body_plain = data.body_plain
        note.note_type = next_note_type
        note.visibility = next_visibility
        if data.is_pinned is not None:
            note.is_pinned = data.is_pinned
        note.updated_at = datetime.utcnow()
        await note.save()

        # Sync update with CompanyAnnouncement
        if next_note_type == "announcement":
            try:
                from Models.announcement import CompanyAnnouncement
                announcement = await CompanyAnnouncement.find_one(CompanyAnnouncement.note_id == note.id)
                body_plain_clean = (data.body_plain if data.body_plain is not None else note.body_plain).strip()
                first_line = body_plain_clean.split('\n')[0].strip() if body_plain_clean else "Announcement"
                title = first_line[:200] if len(first_line) > 0 else "Announcement"
                
                if announcement:
                    announcement.title = title
                    announcement.content = body_plain_clean or (data.body_html if data.body_html is not None else note.body_html)
                    await announcement.save()
                else:
                    from Models.tenant_user import User
                    author_name = "Admin"
                    user_obj = await User.get(author_id)
                    if user_obj:
                        if user_obj.display_name:
                            author_name = user_obj.display_name
                        elif user_obj.first_name:
                            author_name = f"{user_obj.first_name} {user_obj.last_name}".strip()
                    
                    announcement = CompanyAnnouncement(
                        tenant_id=tenant_id,
                        title=title,
                        content=body_plain_clean or (data.body_html if data.body_html is not None else note.body_html),
                        type="general",
                        author_id=author_id,
                        author_name=author_name,
                        note_id=note.id
                    )
                    await announcement.insert()
            except Exception as e:
                logger.error(f"Failed to sync updated announcement from note: {e}", exc_info=True)
        else:
            # If it was updated from announcement to something else, remove the announcement!
            try:
                from Models.announcement import CompanyAnnouncement
                announcement = await CompanyAnnouncement.find_one(CompanyAnnouncement.note_id == note.id)
                if announcement:
                    await announcement.delete()
            except Exception as e:
                logger.error(f"Failed to sync deleted announcement on note type update: {e}", exc_info=True)

        return note

    @staticmethod
    async def soft_delete_note(tenant_id: UUID, note_id: UUID, author_id: UUID) -> Note:
        note = await Note.find_one(
            Note.id == note_id,
            Note.tenant_id == tenant_id
        )
        if not note:
            raise ValueError("Note not found")
            
        if note.author_id != author_id:
            raise ValueError("Only the author can delete this note")
            
        note.is_deleted = True
        note.body_html = "<p>[Note deleted]</p>"
        note.body_plain = "[Note deleted]"
        note.is_pinned = False
        note.updated_at = datetime.utcnow()
        await note.save()

        # Delete synced announcement on soft delete
        try:
            from Models.announcement import CompanyAnnouncement
            announcement = await CompanyAnnouncement.find_one(CompanyAnnouncement.note_id == note.id)
            if announcement:
                await announcement.delete()
        except Exception as e:
            logger.error(f"Failed to sync soft deleted announcement: {e}", exc_info=True)

        return note

    @staticmethod
    async def add_reaction(tenant_id: UUID, note_id: UUID, user_id: UUID, data: ReactionRequest) -> NoteReaction:
        note = await Note.find_one(
            Note.id == note_id,
            Note.tenant_id == tenant_id
        )
        if not note:
            raise ValueError("Note not found")

        if data.emoji not in NoteService.ALLOWED_REACTIONS:
            raise ValueError("Unsupported reaction")
            
        existing = await NoteReaction.find_one(
            NoteReaction.note_id == note.id,
            NoteReaction.user_id == user_id,
            NoteReaction.emoji == data.emoji
        )
        if existing:
            return existing

        reaction = NoteReaction(
            note_id=note.id,
            user_id=user_id,
            emoji=data.emoji
        )
        await reaction.insert()
        return reaction

    @staticmethod
    async def get_notes_for_resource(tenant_id: UUID, resource_type: str, resource_id: UUID) -> List[Note]:
        """Fetch notes for a specific resource with replies, reactions, and mentions."""
        notes = await Note.find(
            Note.tenant_id == tenant_id,
            Note.resource_type == resource_type,
            Note.resource_id == resource_id
        ).sort("-is_pinned", "-created_at").to_list()

        notes_by_parent: Dict[Optional[UUID], List[Note]] = {}
        note_ids = [note.id for note in notes]
        for note in notes:
            notes_by_parent.setdefault(note.parent_note_id, []).append(note)

        reactions = await NoteReaction.find(
            {"note_id": {"$in": note_ids}}
        ).to_list() if note_ids else []
        mentions = await NoteMention.find(
            {"note_id": {"$in": note_ids}}
        ).to_list() if note_ids else []

        # Get note_ids of notes synced as CompanyAnnouncement to calculate total seen count
        from Models.announcement import CompanyAnnouncement, CompanyAnnouncementReadStatus
        synced_announcements = await CompanyAnnouncement.find({"note_id": {"$in": note_ids}}).to_list() if note_ids else []
        
        # Mapping note_id to CompanyAnnouncement.id
        note_to_announcement_id = {ann.note_id: ann.id for ann in synced_announcements}
        announcement_to_note_id = {ann.id: ann.note_id for ann in synced_announcements}
        
        all_target_ids = []
        for note_id in note_ids:
            all_target_ids.append(note_id)
            ann_id = note_to_announcement_id.get(note_id)
            if ann_id:
                all_target_ids.append(ann_id)
                
        read_statuses = await CompanyAnnouncementReadStatus.find({"announcement_id": {"$in": all_target_ids}}).to_list() if all_target_ids else []
        
        seen_count_by_note = {}
        for rs in read_statuses:
            if rs.announcement_id in note_ids:
                note_id = rs.announcement_id
            else:
                note_id = announcement_to_note_id.get(rs.announcement_id)
                
            if note_id:
                seen_count_by_note[note_id] = seen_count_by_note.get(note_id, 0) + 1

        reactions_by_note: Dict[UUID, List[Dict[str, Any]]] = {}
        for reaction in reactions:
            reactions_by_note.setdefault(reaction.note_id, []).append({
                "id": str(reaction.id),
                "emoji": reaction.emoji,
                "user_id": str(reaction.user_id),
                "created_at": reaction.created_at.isoformat(),
            })

        mentions_by_note: Dict[UUID, List[Dict[str, Any]]] = {}
        for mention in mentions:
            mentions_by_note.setdefault(mention.note_id, []).append({
                "id": str(mention.id),
                "mentioned_user_id": str(mention.mentioned_user_id),
                "notified_at": mention.notified_at.isoformat() if mention.notified_at else None,
            })

        def build_thread(note: Note, depth: int = 1) -> Dict[str, Any]:
            child_notes = notes_by_parent.get(note.id, []) if depth < 3 else []
            return NoteService._serialize_note(
                note,
                replies=[build_thread(child, depth + 1) for child in child_notes],
                reactions=reactions_by_note.get(note.id, []),
                mentions=mentions_by_note.get(note.id, []),
                seen_count=seen_count_by_note.get(note.id, 0)
            )

        serialized_notes = [build_thread(note) for note in notes_by_parent.get(None, [])]
        
        # If it is the default project resource, load tickets and merge them as notes!
        if resource_type == 'project' and str(resource_id) == '00000000-0000-0000-0000-000000000021':
            from Models.ticket import Ticket
            tickets = await Ticket.find(Ticket.tenant_id == tenant_id).sort(-Ticket.created_at).to_list()
            for ticket in tickets:
                replies = []
                for idx, c in enumerate(ticket.comments or []):
                    c_time = c.time if c.time else datetime.utcnow()
                    replies.append({
                        "id": f"{ticket.id}-comment-{idx}",
                        "tenant_id": str(tenant_id),
                        "resource_type": "project",
                        "resource_id": str(resource_id),
                        "parent_note_id": str(ticket.id),
                        "author_id": str(c.user_id),
                        "author_name": c.sender,
                        "body_html": f"<p>{c.text}</p>",
                        "body_plain": c.text,
                        "note_type": "general",
                        "visibility": "internal",
                        "is_pinned": False,
                        "is_deleted": False,
                        "created_at": c_time.isoformat(),
                        "updated_at": c_time.isoformat(),
                        "replies": [],
                        "reactions": [],
                        "mentions": [],
                        "seen_count": 0,
                        "can_edit_until": c_time.timestamp() + 15 * 60,
                        "is_ticket_comment": True,
                    })
                
                note_type = 'client_communication'
                if ticket.priority == 'High':
                    note_type = 'important'
                elif ticket.priority == 'Low':
                    note_type = 'general'
                
                serialized_notes.append({
                    "id": str(ticket.id),
                    "tenant_id": str(tenant_id),
                    "resource_type": "project",
                    "resource_id": str(resource_id),
                    "parent_note_id": None,
                    "author_id": str(ticket.employee_id),
                    "author_name": ticket.employee_name,
                    "body_html": f"<p><strong>[Support Ticket {ticket.ticket_seq_id}] {ticket.issue_type}:</strong> {ticket.description}</p>",
                    "body_plain": f"[Support Ticket {ticket.ticket_seq_id}] {ticket.issue_type}: {ticket.description}",
                    "note_type": note_type,
                    "visibility": "internal",
                    "is_pinned": False,
                    "is_deleted": False,
                    "created_at": ticket.created_at.isoformat(),
                    "updated_at": ticket.created_at.isoformat(),
                    "replies": replies,
                    "reactions": [],
                    "mentions": [],
                    "seen_count": 0,
                    "can_edit_until": ticket.created_at.timestamp() + 15 * 60,
                    "is_ticket": True,
                })
            
            # Sort combined list by created_at descending
            serialized_notes.sort(key=lambda n: n.get("created_at", ""), reverse=True)
            # Pinned notes should remain at the top
            serialized_notes.sort(key=lambda n: 1 if n.get("is_pinned", False) else 0, reverse=True)

        return serialized_notes

    @staticmethod
    async def get_stats(tenant_id: UUID) -> Dict[str, int]:
        week_start = datetime.utcnow() - timedelta(days=7)
        total_notes = await Note.find(Note.tenant_id == tenant_id).count()
        comments = await Note.find(Note.tenant_id == tenant_id, Note.parent_note_id != None).count()
        note_ids = [note.id for note in await Note.find(Note.tenant_id == tenant_id).to_list()]
        mentions = await NoteMention.find({"note_id": {"$in": note_ids}}).count() if note_ids else 0
        this_week = await Note.find(
            Note.tenant_id == tenant_id,
            Note.created_at >= week_start
        ).count()
        return {
            "total_notes": total_notes,
            "comments": comments,
            "mentions": mentions,
            "this_week": this_week,
        }
