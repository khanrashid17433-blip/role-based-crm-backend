from typing import List
from Models.platform_settings import PlatformSettings
from Models.audit_log import SettingsAuditLog
from Schema.platform_settings import PlatformSettingsUpdate
from datetime import datetime

class PlatformSettingsService:
    @staticmethod
    async def get_settings() -> PlatformSettings:
        settings = await PlatformSettings.find_one()
        if not settings:
            settings = PlatformSettings()
            await settings.insert()
        return settings

    @staticmethod
    async def update_settings(data: PlatformSettingsUpdate, user_email: str, user_name: str) -> PlatformSettings:
        settings = await PlatformSettingsService.get_settings()
        
        # Track changes for audit log
        changes = []
        update_data = data.model_dump(exclude_unset=True)
        
        for key, value in update_data.items():
            if hasattr(settings, key):
                old_value = getattr(settings, key)
                if old_value != value:
                    setattr(settings, key, value)
                    changes.append(f"Changed {key}")
        
        if changes:
            settings.updated_at = datetime.utcnow()
            await settings.save()
            
            # Create audit log
            action_desc = ", ".join(changes)
            audit_log = SettingsAuditLog(
                user_email=user_email,
                user_name=user_name,
                action=f"Updated settings: {action_desc}"
            )
            await audit_log.insert()
            
        return settings

    @staticmethod
    async def get_audit_logs(limit: int = 50) -> List[SettingsAuditLog]:
        return await SettingsAuditLog.find_all().sort(-SettingsAuditLog.timestamp).limit(limit).to_list()
