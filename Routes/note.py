from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID
import logging

from Schema.note import NoteCreateRequest, NoteUpdateRequest, ReactionRequest
from Services.note_service import NoteService
from Utility.auth_helpers import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/notes", tags=["Unified Notes"])
compat_router = APIRouter(prefix="/api/notes", tags=["Unified Notes"])

@router.post("", summary="Create Note", status_code=status.HTTP_201_CREATED)
async def create_note(data: NoteCreateRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        
        # Restrict employee users from posting announcements/announcement notes
        user_type = current_user.get("user_type")
        role = current_user.get("role", "")
        if data.note_type == "announcement":
            if user_type == "employee" or role == "employee":
                raise HTTPException(status_code=403, detail="Employees are not allowed to create announcement notes.")
                
        note = await NoteService.create_note(tenant_id, user_id, data)
        return {"message": "Note created", "note": NoteService._serialize_note(note)}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create note: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.patch("/{note_id}", summary="Update Note")
async def update_note(note_id: str, data: NoteUpdateRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        
        # Restrict employee users from setting notes to announcement type
        user_type = current_user.get("user_type")
        role = current_user.get("role", "")
        if data.note_type == "announcement":
            if user_type == "employee" or role == "employee":
                raise HTTPException(status_code=403, detail="Employees are not allowed to set notes to announcement type.")
                
        note = await NoteService.update_note(tenant_id, UUID(note_id), user_id, data)
        return {"message": "Note updated", "note": NoteService._serialize_note(note)}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{note_id}", summary="Soft Delete Note")
async def delete_note(note_id: str, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        note = await NoteService.soft_delete_note(tenant_id, UUID(note_id), user_id)
        return {"message": "Note deleted", "note": NoteService._serialize_note(note)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{note_id}/reactions", summary="Add Reaction to Note")
async def add_reaction(note_id: str, data: ReactionRequest, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        user_id = UUID(current_user.get('sub'))
        reaction = await NoteService.add_reaction(tenant_id, UUID(note_id), user_id, data)
        return {"message": "Reaction added", "reaction_id": str(reaction.id)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stats", summary="Get Notes Stats")
async def get_notes_stats(current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        return await NoteService.get_stats(tenant_id)
    except Exception as e:
        logger.error(f"Failed to get notes stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/resource/{resource_type}/{resource_id}", summary="Get Notes for Resource")
async def get_resource_notes(resource_type: str, resource_id: str, current_user = Depends(get_current_user)):
    try:
        tenant_id = UUID(current_user.get('tid'))
        notes = await NoteService.get_notes_for_resource(tenant_id, resource_type, UUID(resource_id))
        return notes
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Compatibility routes for frontend (handles /api/notes)
compat_router.post("", summary="Create Note (Compatibility)", status_code=status.HTTP_201_CREATED)(create_note)
compat_router.patch("/{note_id}", summary="Update Note (Compatibility)")(update_note)
compat_router.delete("/{note_id}", summary="Soft Delete Note (Compatibility)")(delete_note)
compat_router.post("/{note_id}/reactions", summary="Add Reaction to Note (Compatibility)")(add_reaction)
compat_router.get("/stats", summary="Get Notes Stats (Compatibility)")(get_notes_stats)
compat_router.get("/resource/{resource_type}/{resource_id}", summary="Get Notes for Resource (Compatibility)")(get_resource_notes)
