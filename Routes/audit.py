from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from typing import Optional, List
from datetime import datetime, timedelta, timezone
import logging

from Models.login_security import LoginEvent, LoginEventType
from Models.security_event import SecurityEvent, EventSeverity
from Utility.auth_helpers import get_current_user, verify_tenant_admin
from Utility.rate_limiter import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# LOGIN EVENTS / AUDIT LOG ENDPOINTS
# ============================================

@router.get(
    "/api/audit/login-events",
    status_code=status.HTTP_200_OK,
    summary="Get login events",
    description="Get login events for current user or all users (admin only)"
)
@limiter.limit("100/hour")
async def get_login_events(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID (admin only)"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    flagged_only: bool = Query(False, description="Show only flagged events"),
    days: int = Query(30, description="Number of days to look back (max 90)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Items per page"),
    current_user: dict = Depends(get_current_user)
):
    """
    Get login events (audit log)
    
    **Permissions:**
    - Regular users: Can only see their own login events
    - Tenant Admin: Can see all login events for their tenant
    
    **Filters:**
    - user_id: Filter by specific user (admin only)
    - event_type: login_success, login_failed, mfa_success, etc.
    - flagged_only: Show only suspicious/flagged events
    - days: Look back period (default 30, max 90)
    
    **Response includes:**
    - Event type and timestamp
    - IP address and location
    - Device fingerprint
    - Risk score and flagged status
    - Failure reason (if applicable)
    """
    try:
        import uuid
        
        # Limit days to max 90
        days = min(days, 90)
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Build query
        filters = [
            LoginEvent.tenant_id == uuid.UUID(current_user["tid"]),
            LoginEvent.created_at >= since_date
        ]
        
        # Filter by user_id
        if user_id:
            # Check if current user is admin
            if current_user.get("user_type") not in ["tenant_admin", "platform_admin"]:
                # Non-admin can only see their own events
                user_id = current_user["sub"]
            
            filters.append(LoginEvent.user_id == uuid.UUID(user_id))
        else:
            # If no user_id specified and not admin, show only own events
            if current_user.get("user_type") not in ["tenant_admin", "platform_admin"]:
                filters.append(LoginEvent.user_id == uuid.UUID(current_user["sub"]))
        
        # Filter by event type
        if event_type:
            try:
                event_enum = LoginEventType[event_type]
                filters.append(LoginEvent.event_type == event_enum)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event_type: {event_type}"
                )
        
        # Filter flagged only
        if flagged_only:
            filters.append(LoginEvent.flagged == True)
        
        # Get total count
        total = await LoginEvent.count({"$and": filters} if len(filters) > 1 else filters[0])
        
        # Apply pagination and ordering
        skip = (page - 1) * page_size
        events = await LoginEvent.find(
            {"$and": filters} if len(filters) > 1 else filters[0],
            skip=skip,
            limit=page_size,
            sort=[("created_at", -1)]
        ).to_list()
        
        # Format response
        events_list = []
        for event in events:
            events_list.append({
                "id": str(event.id),
                "user_id": str(event.user_id) if event.user_id else None,
                "event_type": event.event_type.value,
                "ip_address": str(event.ip_address) if event.ip_address else None,
                "user_agent": event.user_agent,
                "device_fingerprint": event.device_fingerprint,
                "location": event.location_json,
                "failure_reason": event.failure_reason,
                "risk_score": event.risk_score,
                "flagged": event.flagged,
                "created_at": event.created_at.isoformat()
            })
        
        return {
            "events": events_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Get login events failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve login events"
        )


@router.get(
    "/api/audit/login-events/suspicious",
    status_code=status.HTTP_200_OK,
    summary="Get suspicious login events",
    description="Get flagged/suspicious login events (admin only)"
)
@limiter.limit("50/hour")
async def get_suspicious_login_events(
    request: Request,
    days: int = Query(7, description="Number of days to look back"),
    current_user: dict = Depends(verify_tenant_admin)
):
    """
    Get suspicious/flagged login events
    
    **Permissions:** Tenant Admin only
    
    **Shows:**
    - High risk score events (> 70)
    - Impossible travel detections
    - Multiple failed login attempts
    - Account lockouts
    
    **Use for:**
    - Security monitoring dashboard
    - Alerting system
    - Compliance reporting
    """
    try:
        import uuid
        
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Query flagged events
        events = await LoginEvent.find(
            LoginEvent.tenant_id == uuid.UUID(current_user["tid"]),
            LoginEvent.created_at >= since_date,
            LoginEvent.flagged == True,
            sort=[("created_at", -1)]
        ).to_list()
        
        # Format response
        events_list = []
        for event in events:
            events_list.append({
                "id": str(event.id),
                "user_id": str(event.user_id) if event.user_id else None,
                "event_type": event.event_type.value,
                "ip_address": str(event.ip_address) if event.ip_address else None,
                "location": event.location_json,
                "failure_reason": event.failure_reason,
                "risk_score": event.risk_score,
                "created_at": event.created_at.isoformat()
            })
        
        return {
            "suspicious_events": events_list,
            "total": len(events_list),
            "period_days": days
        }
        
    except Exception as e:
        logger.error(f"Get suspicious events failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve suspicious events"
        )


@router.get(
    "/api/audit/login-events/stats",
    status_code=status.HTTP_200_OK,
    summary="Get login statistics",
    description="Get login statistics and metrics (admin only)"
)
@limiter.limit("50/hour")
async def get_login_stats(
    request: Request,
    days: int = Query(7, description="Number of days to analyze"),
    current_user: dict = Depends(verify_tenant_admin)
):
    """
    Get login statistics
    
    **Permissions:** Tenant Admin only
    
    **Metrics:**
    - Total logins (success/failed)
    - Failed login rate
    - MFA success rate
    - Suspicious activity count
    - Account lockouts
    - Unique users logged in
    
    **Use for:**
    - Security dashboard
    - Compliance reporting
    - Trend analysis
    """
    try:
        import uuid
        
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        tenant_id = uuid.UUID(current_user["tid"])
        
        # Total events
        total_events = await LoginEvent.count(
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.created_at >= since_date
        )
        
        # Successful logins
        successful_logins = await LoginEvent.count(
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.created_at >= since_date,
            LoginEvent.event_type == LoginEventType.login_success
        )
        
        # Failed logins
        failed_logins = await LoginEvent.count(
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.created_at >= since_date,
            LoginEvent.event_type == LoginEventType.login_failed
        )
        
        # Flagged events
        flagged_events = await LoginEvent.count(
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.created_at >= since_date,
            LoginEvent.flagged == True
        )
        
        # Account lockouts
        account_lockouts = await LoginEvent.count(
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.created_at >= since_date,
            LoginEvent.event_type == LoginEventType.account_locked
        )
        
        # Unique users - this will need aggregation in MongoDB
        unique_users = await LoginEvent.distinct(
            "user_id",
            LoginEvent.tenant_id == tenant_id,
            LoginEvent.created_at >= since_date,
            LoginEvent.user_id != None
        )
        
        # Calculate rates
        failed_rate = (failed_logins / total_events * 100) if total_events > 0 else 0
        unique_users_count = len(unique_users) if unique_users else 0
        
        return {
            "period_days": days,
            "total_events": total_events,
            "successful_logins": successful_logins,
            "failed_logins": failed_logins,
            "failed_login_rate": round(failed_rate, 2),
            "flagged_events": flagged_events,
            "account_lockouts": account_lockouts,
            "unique_users": unique_users_count,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get login stats failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve login statistics"
        )


# ============================================
# SECURITY EVENTS ENDPOINTS
# ============================================

@router.get(
    "/api/audit/security-events",
    status_code=status.HTTP_200_OK,
    summary="Get security events",
    description="Get security audit log (admin only)"
)
@limiter.limit("100/hour")
async def get_security_events(
    request: Request,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity: info, warning, critical"),
    days: int = Query(30, description="Number of days to look back"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(verify_tenant_admin)
):
    """
    Get security events (append-only audit log)
    
    **Permissions:** Tenant Admin only
    
    **Event Types:**
    - account_locked
    - password_changed
    - mfa_enabled/disabled
    - sso_config_changed
    - admin_role_granted
    - session_family_revoked
    - suspicious_login
    - data_export
    - bulk_delete
    
    **Severity Levels:**
    - info: Normal operations
    - warning: Potentially concerning
    - critical: Requires immediate attention
    """
    try:
        import uuid
        
        since_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Build query
        filters = [
            SecurityEvent.tenant_id == uuid.UUID(current_user["tid"]),
            SecurityEvent.created_at >= since_date
        ]
        
        # Filter by event type
        if event_type:
            filters.append(SecurityEvent.event_type == event_type)
        
        # Filter by severity
        if severity:
            try:
                severity_enum = EventSeverity[severity]
                filters.append(SecurityEvent.severity == severity_enum)
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid severity: {severity}"
                )
        
        # Get total count
        total = await SecurityEvent.count({"$and": filters} if len(filters) > 1 else filters[0])
        
        # Apply pagination and ordering
        skip = (page - 1) * page_size
        events = await SecurityEvent.find(
            {"$and": filters} if len(filters) > 1 else filters[0],
            skip=skip,
            limit=page_size,
            sort=[("created_at", -1)]
        ).to_list()
        
        # Format response
        events_list = []
        for event in events:
            events_list.append({
                "id": str(event.id),
                "event_type": event.event_type,
                "severity": event.severity.value,
                "user_id": str(event.user_id) if event.user_id else None,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "ip_address": str(event.ip_address) if event.ip_address else None,
                "metadata": event.metadata_json,
                "created_at": event.created_at.isoformat()
            })
        
        return {
            "events": events_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Get security events failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve security events"
        )
