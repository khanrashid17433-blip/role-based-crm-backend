import secrets
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import logging

from Models.onboarding import UserInvitation
from Models.tenant_user import User, Tenant, UserStatus, UserType, AuthProvider
from Models.security_event import SecurityEvent, EventSeverity
from Services.auth_service import create_token_pair, create_refresh_token_opaque, hash_token
from Models.login_security import RefreshToken
from Utility.auth_helpers import hash_password

logger = logging.getLogger(__name__)


class InvitationService:
    """Service for managing employee invitations"""
    
    @staticmethod
    async def create_invitation(
        tenant_id: uuid.UUID,
        invited_by: uuid.UUID,
        email: str,
        first_name: str,
        last_name: str,
        role: str,
        phone: Optional[str] = None,
        personal_details: Optional[Dict[str, Any]] = None,
        notification_prefs: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> UserInvitation:
        """
        Create employee invitation
        
        Args:
            db: Database session
            tenant_id: Tenant UUID
            invited_by: User UUID of inviter
            email: Employee email
            first_name: First name
            last_name: Last name
            role: Role (hr_admin, payroll_admin, etc.)
            phone: Phone number
            personal_details: Pre-filled personal details
            notification_prefs: Default notification preferences
            ip_address: IP address of inviter
            
        Returns:
            UserInvitation object
            
        Raises:
            ValueError: If email already exists or invitation already pending
        """
        # Normalize email
        normalized_email = email.lower().strip()
        
        # Check if user already exists
        existing_user = await User.find_one(
            User.email == normalized_email,
            User.tenant_id == tenant_id,
            User.deleted_at == None
        )
        if existing_user:
            raise ValueError(
                f"A user with email {email} already exists in your organization. "
                "Please check if they are already part of your team."
            )
        
        # Check if pending invitation exists
        existing_invite = await UserInvitation.find_one(
            UserInvitation.email == normalized_email,
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.status == "pending",
            UserInvitation.expires_at > datetime.now(timezone.utc)
        )
        if existing_invite:
            raise ValueError(
                f"An invitation has already been sent to {email}. "
                "Please wait for them to accept, or revoke the previous invitation to send a new one."
            )
        
        # Generate invitation token
        plain_token = secrets.token_urlsafe(32)  # 43-char URL-safe string
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        
        # Create invitation
        invitation = UserInvitation(
            tenant_id=tenant_id,
            invited_by=invited_by,
            email=normalized_email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            token_hash=token_hash,
            status="pending",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),  # 7 days
            personal_details_json=personal_details or {},
            notification_prefs_json=notification_prefs or {},
            invite_ip=ip_address
        )
        
        await invitation.insert()
        
        # Store plain token temporarily for email sending
        invitation._plain_token = plain_token
        
        # Log security event
        security_event = SecurityEvent(
            tenant_id=tenant_id,
            user_id=None,
            event_type="employee_invited",
            severity=EventSeverity.info,
            actor_id=invited_by,
            ip_address=ip_address,
            metadata_json={
                "invitation_id": str(invitation.id),
                "email": normalized_email,
                "role": role
            }
        )
        await security_event.insert()
        
        logger.info(f"Invitation created for {email} by user {invited_by}")
        
        return invitation
    
    @staticmethod
    async def validate_invitation_token(
        token: str
    ) -> Dict[str, Any]:
        """
        Validate invitation token and return pre-filled data
        
        Args:
            db: Database session
            token: Invitation token from email
            
        Returns:
            Dictionary with invitation data
            
        Raises:
            ValueError: If token is invalid, expired, or already used
        """
        # Hash token
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Find invitation
        invitation = await UserInvitation.find_one(
            UserInvitation.token_hash == token_hash
        )
        
        if not invitation:
            raise ValueError("Invalid invitation token")
        
        # Check status
        if invitation.status == "accepted":
            raise ValueError("Invitation already accepted")
        
        if invitation.status == "revoked":
            raise ValueError("Invitation has been revoked")
        
        if invitation.status == "expired":
            raise ValueError("Invitation has expired")
        
        # Check expiry
        if invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            invitation.status = "expired"
            await invitation.save()
            raise ValueError("Invitation has expired")
        
        # Get tenant info
        tenant = await Tenant.find_one(Tenant.id == invitation.tenant_id)
        
        return {
            "valid": True,
            "invitation_id": str(invitation.id),
            "email": invitation.email,
            "first_name": invitation.first_name,
            "last_name": invitation.last_name,
            "phone": invitation.phone,
            "company_name": tenant.name if tenant else None,
            "role": invitation.role,
            "personal_details": invitation.personal_details_json,
            "notification_prefs": invitation.notification_prefs_json
        }
    
    @staticmethod
    async def accept_invitation(
        token: str,
        password: str,
        preferred_name: Optional[str] = None,
        phone: Optional[str] = None,
        avatar_url: Optional[str] = None,
        personal_details: Optional[Dict[str, Any]] = None,
        setup_mfa: bool = False,
        mfa_type: Optional[str] = None,
        notification_prefs: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Accept invitation and create user account
        
        Args:
            db: Database session
            token: Invitation token
            password: New password
            preferred_name: Preferred name
            phone: Updated phone
            avatar_url: Profile photo URL
            personal_details: Updated personal details
            setup_mfa: Whether to set up MFA
            mfa_type: MFA type (totp or email_otp)
            notification_prefs: Notification preferences
            ip_address: IP address
            user_agent: User agent
            
        Returns:
            Dictionary with user, tenant, and tokens
            
        Raises:
            ValueError: If token is invalid or user creation fails
        """
        # Validate token
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        invitation = await UserInvitation.find_one(
            UserInvitation.token_hash == token_hash
        )
        
        if not invitation:
            raise ValueError("Invalid invitation token")
        
        if invitation.status != "pending":
            raise ValueError(f"Invitation is {invitation.status}")
        
        if invitation.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            invitation.status = "expired"
            await invitation.save()
            raise ValueError("Invitation has expired")
        
        # Get tenant
        tenant = await Tenant.find_one(Tenant.id == invitation.tenant_id)
        
        if not tenant:
            raise ValueError("Tenant not found")
        
        # Check if user already exists with this email
        existing_user = await User.find_one(
            User.email == invitation.email,
            User.deleted_at == None
        )
        
        if existing_user:
            # User already exists - mark invitation as invalid and provide helpful message
            invitation.status = "expired"
            invitation.revoke_reason = "User account already exists"
            await invitation.save()
            
            raise ValueError(
                f"An account with email {invitation.email} already exists. "
                "If this is you, please login instead. "
                "If you forgot your password, use the 'Forgot Password' option."
            )
        
        # Hash password
        password_hash = hash_password(password)
        
        # Create user
        user = User(
            tenant_id=tenant.id,
            email=invitation.email,
            email_verified=True,  # Email verified via invitation
            email_verified_at=datetime.now(timezone.utc),
            first_name=invitation.first_name,
            last_name=invitation.last_name,
            display_name=preferred_name or f"{invitation.first_name} {invitation.last_name}",
            phone=phone or invitation.phone,
            avatar_url=avatar_url,
            password_hash=password_hash,
            auth_provider=AuthProvider.local,
            status=UserStatus.active,
            user_type=UserType.employee,  # Default to employee
            role=invitation.role,  # Set role from invitation
            mfa_enabled=setup_mfa,
            mfa_type=mfa_type if setup_mfa else None,
            created_by=invitation.invited_by
        )
        await user.insert()

        # Link to Employee record if exists
        if invitation.employee_id:
            from Models.employee import Employee
            employee = await Employee.find_one(Employee.id == invitation.employee_id)
            if employee:
                employee.user_id = user.id
                employee.updated_at = datetime.utcnow()
                await employee.save()
                logger.info(f"Linked user {user.id} to employee {employee.id}")
        
        # Update invitation
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)
        invitation.accept_ip = ip_address
        invitation.created_user_id = user.id
        await invitation.save()
        
        # Create access token
        tokens = create_token_pair(
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            email=user.email,
            user_type=user.user_type.value,
            role=user.role
        )
        
        # Create refresh token
        refresh_token_plain, expires_at = create_refresh_token_opaque(remember_me=False)
        refresh_token_hash = hash_token(refresh_token_plain)
        
        family_id = uuid.uuid4()
        refresh_token_record = RefreshToken(
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=refresh_token_hash,
            family_id=family_id,
            parent_token_id=None,
            device_fingerprint=None,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        await refresh_token_record.insert()        # Log security event
        security_event = SecurityEvent(
            tenant_id=tenant.id,
            user_id=user.id,
            event_type="invitation_accepted",
            severity=EventSeverity.info,
            actor_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json={
                "invitation_id": str(invitation.id),
                "role": invitation.role
            }
        )
        await security_event.insert()
        
        logger.info(f"Invitation accepted and user created: {user.email}")
        
        # Add refresh token to response
        tokens["refresh_token"] = refresh_token_plain
        
        return {
            "user": user,
            "tenant": tenant,
            "tokens": tokens,
            "mfa_setup_required": setup_mfa and not user.mfa_secret
        }
    
    @staticmethod
    async def revoke_invitation(
        invitation_id: uuid.UUID,
        revoked_by: uuid.UUID,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Revoke invitation
        
        Args:
            db: Database session
            invitation_id: Invitation UUID
            revoked_by: User UUID who is revoking
            reason: Reason for revocation
            ip_address: IP address
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If invitation not found or already processed
        """
        invitation = await UserInvitation.find_one(UserInvitation.id == invitation_id)
        
        if not invitation:
            raise ValueError("Invitation not found")
        
        if invitation.status != "pending":
            raise ValueError(f"Cannot revoke invitation with status: {invitation.status}")
        
        invitation.status = "revoked"
        invitation.revoked_at = datetime.now(timezone.utc)
        invitation.revoked_by = revoked_by
        invitation.revoke_reason = reason
        await invitation.save()
        
        # Log security event
        security_event = SecurityEvent(
            tenant_id=invitation.tenant_id,
            user_id=None,
            event_type="invitation_revoked",
            severity=EventSeverity.warning,
            actor_id=revoked_by,
            ip_address=ip_address,
            metadata_json={
                "invitation_id": str(invitation.id),
                "email": invitation.email,
                "reason": reason
            }
        )
        await security_event.insert()
        
        logger.info(f"Invitation {invitation_id} revoked by {revoked_by}")
        
        return True
