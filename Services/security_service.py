import uuid
from typing import Optional, Dict, Any
import logging

from Models.security_event import SecurityEvent, EventSeverity

logger = logging.getLogger(__name__)


class SecurityService:
    """Service for logging security events (append-only audit log)"""
    
    @staticmethod
    async def log_event(
        event_type: str,
        severity: EventSeverity = EventSeverity.info,
        tenant_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        actor_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecurityEvent:
        """
        Log a security event (append-only)
        
        Args:
            event_type: Event type (e.g., account_locked, password_changed)
            severity: Event severity (info, warning, critical)
            tenant_id: Tenant UUID (nullable for pre-tenant events)
            user_id: User UUID (nullable)
            actor_id: Actor UUID (who performed the action)
            ip_address: IP address
            user_agent: User agent string
            metadata: Event-specific metadata (old_value, new_value, reason, etc.)
            
        Returns:
            SecurityEvent object
            
        Note:
            This table is APPEND-ONLY. Updates and deletes are blocked at both
            the application level (SQLAlchemy events) and database level (triggers).
        """
        event = SecurityEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=metadata or {}
        )
        
        await event.insert()
        
        logger.info(
            f"Security event logged: {event_type} "
            f"(severity={severity.value}, user={user_id}, actor={actor_id})"
        )
        
        return event
    
    @staticmethod
    async def log_account_locked(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        ip_address: Optional[str] = None,
        reason: str = "too_many_failed_attempts"
    ):
        """Log account locked event"""
        return await SecurityService.log_event(
            event_type="account_locked",
            severity=EventSeverity.warning,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=user_id,
            ip_address=ip_address,
            metadata={"reason": reason}
        )
    
    @staticmethod
    async def log_password_changed(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        ip_address: Optional[str] = None,
        forced: bool = False
    ):
        """Log password changed event"""
        return await SecurityService.log_event(
            event_type="password_changed",
            severity=EventSeverity.info,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=actor_id,
            ip_address=ip_address,
            metadata={"forced": forced}
        )
    
    @staticmethod
    async def log_mfa_enabled(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        mfa_type: str,
        ip_address: Optional[str] = None
    ):
        """Log MFA enabled event"""
        return await SecurityService.log_event(
            event_type="mfa_enabled",
            severity=EventSeverity.info,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=user_id,
            ip_address=ip_address,
            metadata={"mfa_type": mfa_type}
        )
    
    @staticmethod
    async def log_mfa_disabled(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        ip_address: Optional[str] = None,
        reason: Optional[str] = None
    ):
        """Log MFA disabled event"""
        return await SecurityService.log_event(
            event_type="mfa_disabled",
            severity=EventSeverity.warning,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=actor_id,
            ip_address=ip_address,
            metadata={"reason": reason}
        )
    
    @staticmethod
    async def log_sso_config_changed(
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        ip_address: Optional[str] = None,
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None
    ):
        """Log SSO configuration changed event"""
        return await SecurityService.log_event(
            event_type="sso_config_changed",
            severity=EventSeverity.warning,
            tenant_id=tenant_id,
            user_id=None,
            actor_id=actor_id,
            ip_address=ip_address,
            metadata={"old_value": old_value, "new_value": new_value}
        )
    
    @staticmethod
    async def log_admin_role_granted(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        role: str,
        ip_address: Optional[str] = None
    ):
        """Log admin role granted event"""
        return await SecurityService.log_event(
            event_type="admin_role_granted",
            severity=EventSeverity.warning,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=actor_id,
            ip_address=ip_address,
            metadata={"role": role}
        )
    
    @staticmethod
    async def log_session_family_revoked(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        family_id: uuid.UUID,
        reason: str,
        ip_address: Optional[str] = None
    ):
        """Log session family revoked event (token reuse detected)"""
        return await SecurityService.log_event(
            event_type="session_family_revoked",
            severity=EventSeverity.critical,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=None,
            ip_address=ip_address,
            metadata={"family_id": str(family_id), "reason": reason}
        )
    
    @staticmethod
    async def log_suspicious_login(
        user_id: uuid.UUID,
        tenant_id: uuid.UUID,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        reason: str = "impossible_travel",
        risk_score: int = 0
    ):
        """Log suspicious login event"""
        return await SecurityService.log_event(
            event_type="suspicious_login",
            severity=EventSeverity.critical,
            tenant_id=tenant_id,
            user_id=user_id,
            actor_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"reason": reason, "risk_score": risk_score}
        )
    
    @staticmethod
    async def log_data_export(
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        export_type: str,
        record_count: int,
        ip_address: Optional[str] = None
    ):
        """Log data export event"""
        return await SecurityService.log_event(
            event_type="data_export",
            severity=EventSeverity.warning,
            tenant_id=tenant_id,
            user_id=None,
            actor_id=actor_id,
            ip_address=ip_address,
            metadata={"export_type": export_type, "record_count": record_count}
        )
    
    @staticmethod
    async def log_bulk_delete(
        tenant_id: uuid.UUID,
        actor_id: uuid.UUID,
        entity_type: str,
        affected_records: int,
        ip_address: Optional[str] = None
    ):
        """Log bulk delete event"""
        return await SecurityService.log_event(
            event_type="bulk_delete",
            severity=EventSeverity.critical,
            tenant_id=tenant_id,
            user_id=None,
            actor_id=actor_id,
            ip_address=ip_address,
            metadata={"entity_type": entity_type, "affected_records": affected_records}
        )
