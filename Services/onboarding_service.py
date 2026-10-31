from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from Models.onboarding import TenantOnboarding, UserInvitation
from Models.tenant_user import Tenant, TenantStatus
from Models.enums import UserRole, InvitationStatus
from Utility.auth_helpers import generate_verification_token, hash_token
from Utility.email_service import send_invitation_email

logger = logging.getLogger(__name__)


class OnboardingService:
    """Service for managing tenant onboarding"""
    
    @staticmethod
    async def get_onboarding_progress(tenant_id: UUID) -> Optional[TenantOnboarding]:
        """Get current onboarding progress"""
        return await TenantOnboarding.find_one(TenantOnboarding.tenant_id == tenant_id)
    
    @staticmethod
    async def create_onboarding_record(tenant_id: UUID) -> TenantOnboarding:
        """Create initial onboarding record"""
        onboarding = TenantOnboarding(
            tenant_id=tenant_id,
            current_step=0,
            is_completed=False
        )
        await onboarding.insert()
        return onboarding
    
    @staticmethod
    async def complete_step_1(
        tenant_id: UUID,
        user_id: UUID,
        data: Dict[str, Any]
    ) -> TenantOnboarding:
        """Complete Step 1: Company Profile"""
        
        # Get or create onboarding record
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        if not onboarding:
            onboarding = await OnboardingService.create_onboarding_record(tenant_id)
        
        # Save step data — use flag_modified so SQLAlchemy tracks JSONB mutation
        onboarding.step_1_company_profile = dict(data)
        onboarding.current_step = 1
        await onboarding.save()
        
        logger.info(f"Tenant {tenant_id} completed Step 1: Company Profile")
        return onboarding
    
    @staticmethod
    async def complete_step_2(
        tenant_id: UUID,
        user_id: UUID,
        data: Dict[str, Any]
    ) -> TenantOnboarding:
        """Complete Step 2: First Legal Entity"""
        
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        if not onboarding or onboarding.current_step < 1:
            raise ValueError("Complete Step 1 first")
        
        # Save step data — use flag_modified so SQLAlchemy tracks JSONB mutation
        onboarding.step_2_entity = dict(data)
        onboarding.current_step = 2
        await onboarding.save()
        
        logger.info(f"Tenant {tenant_id} completed Step 2: First Entity")
        return onboarding
    
    @staticmethod
    async def complete_step_3(
        tenant_id: UUID,
        user_id: UUID,
        data: Dict[str, Any],
        skip: bool = False
    ) -> Dict[str, Any]:
        """Complete Step 3: Team Invitations"""
        
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        if not onboarding or onboarding.current_step < 2:
            raise ValueError("Complete Step 2 first")
        
        invitations_sent = []
        
        if not skip and 'invitations' in data:
            for invite_data in data['invitations']:
                # Generate invitation token
                plain_token = generate_verification_token()
                token_hash = hash_token(plain_token)
                
                # Create invitation record
                invitation = UserInvitation(
                    tenant_id=tenant_id,
                    email=invite_data['email'].lower(),
                    first_name=invite_data.get('first_name'),
                    last_name=invite_data.get('last_name'),
                    role=invite_data['role'],
                    invited_by=user_id,
                    token_hash=token_hash,  # Fixed: was invitation_token_hash
                    status='pending',
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                    metadata_json={
                        'onboarding_invite': True
                    }
                )
                await invitation.insert()  # MISSING: Save invitation to database                # Send invitation email
                try:
                    frontend_url = "http://localhost:3000"  # Get from env
                    invite_url = f"{frontend_url}/accept-invite?token={plain_token}"
                    
                    email_sent = send_invitation_email(
                        to_email=invite_data['email'],
                        invitation_url=invite_url,
                        invited_by_name=f"{data.get('inviter_name', 'Team')}",
                        role=invite_data['role'],
                        company_name=data.get('company_name', 'the platform')
                    )
                    
                    if email_sent:
                        invitations_sent.append(invite_data['email'])
                        logger.info(f"Invitation sent to {invite_data['email']}")
                except Exception as e:
                    logger.error(f"Failed to send invitation to {invite_data['email']}: {str(e)}")
        
        # Save step data — use flag_modified so SQLAlchemy tracks JSONB mutation
        onboarding.step_3_team_invites = {
            'invitations_count': len(data.get('invitations', [])),
            'skipped': skip
        }
        onboarding.current_step = 3
        await onboarding.save()
        
        logger.info(f"Tenant {tenant_id} completed Step 3: Team Invitations")
        return {
            'onboarding': onboarding,
            'invitations_sent': invitations_sent,
            'total_invites': len(data.get('invitations', []))
        }
    
    @staticmethod
    async def complete_step_4(
        tenant_id: UUID,
        user_id: UUID,
        data: Dict[str, Any]
    ) -> TenantOnboarding:
        """Complete Step 4: Payroll Configuration"""
        
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        if not onboarding or onboarding.current_step < 3:
            raise ValueError("Complete Step 3 first")
        
        # Save step data
        onboarding.step_4_payroll_config = dict(data)
        onboarding.current_step = 4
        await onboarding.save()
        
        logger.info(f"Tenant {tenant_id} completed Step 4: Payroll Config")
        return onboarding
    
    @staticmethod
    async def complete_step_5(
        tenant_id: UUID,
        user_id: UUID,
        data: Dict[str, Any]
    ) -> TenantOnboarding:
        """Complete Step 5: Leave Policy"""
        
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        if not onboarding or onboarding.current_step < 4:
            raise ValueError("Complete Step 4 first")
        
        # Save step data
        onboarding.step_5_leave_policy = dict(data)
        onboarding.current_step = 5
        await onboarding.save()
        
        logger.info(f"Tenant {tenant_id} completed Step 5: Leave Policy")
        return onboarding
    
    @staticmethod
    async def complete_onboarding(
        tenant_id: UUID,
        user_id: UUID
    ) -> TenantOnboarding:
        """Complete Step 6: Mark onboarding as complete"""
        
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        if not onboarding or onboarding.current_step < 5:
            raise ValueError("Complete all previous steps first")
        
        # Mark as complete
        onboarding.current_step = 6
        onboarding.is_completed = True
        onboarding.step_6_completion = {
            'completed_at': datetime.now(timezone.utc).isoformat(),
            'completed_by': str(user_id)
        }
        await onboarding.save()
        
        # Also update tenant onboarding status
        tenant = await Tenant.find_one(Tenant.id == tenant_id)
        
        if tenant:
            tenant.onboarding_completed = True
            tenant.onboarding_step = 6
            await tenant.save()
        
        logger.info(f"Tenant {tenant_id} completed onboarding!")
        return onboarding
    
    @staticmethod
    async def get_invitations(
        tenant_id: UUID,
        status: Optional[str] = None
    ) -> List[UserInvitation]:
        """Get all invitations for a tenant"""
        
        filters = [UserInvitation.tenant_id == tenant_id]
        
        if status:
            filters.append(UserInvitation.status == status)
        
        return await UserInvitation.find(
            {"$and": filters} if len(filters) > 1 else filters[0],
            sort=[("created_at", -1)]
        ).to_list()
    
    @staticmethod
    async def get_team_invites_with_details(
        tenant_id: UUID
    ) -> Dict[str, Any]:
        """Get team invitations with member details for step 3"""
        
        # Fetch all invitations for this tenant
        invitations = await OnboardingService.get_invitations(tenant_id)
        
        # Get counts
        pending_count = len([inv for inv in invitations if inv.status == 'pending'])
        accepted_count = len([inv for inv in invitations if inv.status == 'accepted'])
        
        # Format invitation details
        members = []
        for inv in invitations:
            member = {
                "id": str(inv.id),
                "email": inv.email,
                "first_name": inv.first_name,
                "last_name": inv.last_name,
                "role": inv.role,
                "status": inv.status,
                "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
                "accepted_at": inv.accepted_at.isoformat() if inv.accepted_at else None,
                "resent_count": inv.resent_count,
                "last_resent_at": inv.last_resent_at.isoformat() if inv.last_resent_at else None
            }
            members.append(member)
        
        return {
            "skipped": False,
            "invitations_count": len(invitations),
            "pending_count": pending_count,
            "accepted_count": accepted_count,
            "members": members
        }
    
    @staticmethod
    async def accept_invitation(
        token: str,
        user_id: UUID
    ) -> UserInvitation:
        """Accept an invitation"""
        
        token_hash = hash_token(token)
        
        invitation = await UserInvitation.find_one(
            UserInvitation.token_hash == token_hash,
            UserInvitation.status == 'pending'
        )
        
        if not invitation:
            raise ValueError("Invalid or expired invitation")
        
        expires_at = invitation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if expires_at < datetime.now(timezone.utc):
            invitation.status = 'expired'
            await invitation.save()
            raise ValueError("Invitation has expired")
        
        # Mark as accepted
        invitation.status = 'accepted'
        invitation.accepted_at = datetime.now(timezone.utc)
        invitation.user_id = user_id
        await invitation.save()
        
        logger.info(f"Invitation accepted for {invitation.email}")
        return invitation
    
    @staticmethod
    async def resend_invitation(
        invitation_id: UUID
    ) -> UserInvitation:
        """Resend an invitation"""
        
        invitation = await UserInvitation.find_one(UserInvitation.id == invitation_id)
        
        if not invitation:
            raise ValueError("Invitation not found")
        
        if invitation.status != 'pending':
            raise ValueError("Can only resend pending invitations")
        
        # Generate new token
        plain_token = generate_verification_token()
        token_hash = hash_token(plain_token)
        
        invitation.token_hash = token_hash  # Fixed: was invitation_token_hash
        invitation.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        invitation.resent_count += 1
        invitation.last_resent_at = datetime.now(timezone.utc)
        await invitation.save()
        
        logger.info(f"Invitation resent to {invitation.email}")
        return invitation, plain_token
