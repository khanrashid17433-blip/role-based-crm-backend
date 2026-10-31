from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
import os

from Services.invitation_service import InvitationService
from Schema.invitation import (
    InviteEmployeeRequest,
    InviteEmployeeResponse,
    ValidateInviteTokenRequest,
    ValidateInviteTokenResponse,
    AcceptInviteRequest,
    AcceptInviteResponse,
    RevokeInviteRequest
)
from Schema.tenant_user import UserResponse, TenantResponse
from Utility.auth_helpers import extract_ip_address, get_current_user
from Utility.rate_limiter import limiter
from Utility.email_service import send_invitation_email

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# INVITATION ENDPOINTS
# ============================================

@router.post(
    "/api/invitations/invite",
    status_code=status.HTTP_201_CREATED,
    summary="Invite employee",
    description="Invite an employee to join the tenant (Tenant Admin or HR Admin)"
)
@limiter.limit("20/hour")
async def invite_employee(
    request: Request,
    invite_data: InviteEmployeeRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Invite employee to join tenant
    
    **Permissions:** Tenant Admin, HR Admin, or any user with invite permissions
    
    **Rate Limit:** 20 invitations per hour per user
    
    **Flow:**
    1. Validate inviter has permission (Tenant Admin, HR Admin)
    2. Check email doesn't already exist
    3. Generate invitation token (7-day expiry)
    4. Send invitation email with link
    5. Log security event
    
    **Use Cases:**
    - During onboarding (Step 3: Team Invites) - Tenant Admin invites initial team
    - After onboarding - Tenant Admin or HR Admin can invite more employees anytime
    
    **Invitation Email:**
    - Subject: "You're invited to join {company} HRMS"
    - Link: /accept-invite?token={token}
    - Expires in 7 days
    """
    try:
        ip_address = extract_ip_address(request)
        
        # Create invitation
        invitation = await InvitationService.create_invitation(
            tenant_id=current_user["tid"],
            invited_by=current_user["sub"],
            email=invite_data.email,
            first_name=invite_data.first_name,
            last_name=invite_data.last_name,
            role=invite_data.role,
            phone=invite_data.phone,
            personal_details=invite_data.personal_details,
            notification_prefs=invite_data.notification_prefs,
            ip_address=ip_address
        )
        
        # Send invitation email
        plain_token = getattr(invitation, '_plain_token', None)
        if plain_token:
            # Get tenant and inviter details for email
            from Models.tenant_user import Tenant, User
            
            # Get tenant
            tenant = await Tenant.find_one(Tenant.id == current_user["tid"])
            
            # Get inviter
            inviter = await User.find_one(User.id == current_user["sub"])
            
            # Build invitation URL
            frontend_url = os.getenv("FRONTEND_URL", " https://bidentate-anathematically-stanley.ngrok-free.dev")
            invitation_url = f"{frontend_url}/accept-invite?token={plain_token}"
            
            # Send email
            email_sent = send_invitation_email(
                to_email=invite_data.email,
                invitation_url=invitation_url,
                invited_by_name=f"{inviter.first_name} {inviter.last_name}" if inviter else "Team",
                role=invite_data.role,
                company_name=tenant.name if tenant else "the platform"
            )
            
            if email_sent:
                logger.info(f"Invitation email sent successfully to {invite_data.email}")
            else:
                logger.error(f"Failed to send invitation email to {invite_data.email}")
        else:
            logger.warning(f"No plain token available for invitation {invitation.id}")
        
        return InviteEmployeeResponse(
            message=f"Invitation sent to {invite_data.email}",
            invitation_id=str(invitation.id),
            email=invitation.email,
            expires_at=invitation.expires_at
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Invite employee failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send invitation. Please try again."
        )


@router.get(
    "/api/invitations/validate",
    status_code=status.HTTP_200_OK,
    summary="Validate invitation token",
    description="Validate invitation token and get pre-filled data"
)
async def validate_invitation_token(
    token: str
):
    """
    Validate invitation token
    
    **Flow:**
    1. Hash token and lookup in database
    2. Check status (pending, accepted, expired, revoked)
    3. Check expiry (7 days)
    4. Return pre-filled data (name, email, company, role)
    
    **Response:**
    - valid: true/false
    - Pre-filled data if valid
    - Error message if invalid
    """
    try:
        data = await InvitationService.validate_invitation_token(
            token=token
        )
        
        return ValidateInviteTokenResponse(**data)
        
    except ValueError as e:
        return ValidateInviteTokenResponse(
            valid=False,
            message=str(e)
        )
    except Exception as e:
        logger.error(f"Validate invitation failed: {str(e)}", exc_info=True)
        return ValidateInviteTokenResponse(
            valid=False,
            message="Failed to validate invitation token"
        )


@router.post(
    "/api/invitations/accept",
    status_code=status.HTTP_200_OK,
    summary="Accept invitation",
    description="Accept invitation and create employee account"
)
@limiter.limit("5/hour")
async def accept_invitation(
    request: Request,
    accept_data: AcceptInviteRequest
):
    """
    Accept invitation and create employee account
    
    **Rate Limit:** 5 attempts per hour per IP
    
    **Flow:**
    1. Validate invitation token
    2. Validate passwords match
    3. Create user account with provided data
    4. Mark invitation as accepted
    5. Issue access + refresh tokens
    6. Log security event
    
    **Optional Steps:**
    - Upload profile photo
    - Update personal details
    - Set up MFA (if tenant requires or user opts in)
    - Set notification preferences
    
    **Response:**
    - access_token (15 min expiry)
    - refresh_token (7 days)
    - user object
    - tenant object
    - mfa_setup_required (if tenant policy requires MFA)
    """
    try:
        # Validate passwords match
        if accept_data.password != accept_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        ip_address = extract_ip_address(request)
        user_agent = request.headers.get("User-Agent")
        
        # Accept invitation
        result = await InvitationService.accept_invitation(
            token=accept_data.token,
            password=accept_data.password,
            preferred_name=accept_data.preferred_name,
            phone=accept_data.phone,
            avatar_url=accept_data.avatar_url,
            personal_details=accept_data.personal_details,
            setup_mfa=accept_data.setup_mfa,
            mfa_type=accept_data.mfa_type,
            notification_prefs=accept_data.notification_prefs,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Convert models to response schemas
        user_response = UserResponse(
            id=str(result["user"].id),
            tenant_id=str(result["user"].tenant_id),
            email=result["user"].email,
            email_verified=result["user"].email_verified,
            first_name=result["user"].first_name,
            last_name=result["user"].last_name,
            display_name=result["user"].display_name,
            phone=result["user"].phone,
            phone_verified=result["user"].phone_verified,
            avatar_url=result["user"].avatar_url,
            auth_provider=result["user"].auth_provider.value,
            status=result["user"].status.value,
            user_type=result["user"].user_type.value,
            role=result["user"].role,
            last_login_at=result["user"].last_login_at,
            mfa_enabled=result["user"].mfa_enabled,
            mfa_type=result["user"].mfa_type.value if result["user"].mfa_type else None,
            timezone=result["user"].timezone,
            locale=result["user"].locale,
            force_password_change=result["user"].force_password_change,
            created_at=result["user"].created_at,
            updated_at=result["user"].updated_at
        )
        
        tenant_response = TenantResponse(
            id=str(result["tenant"].id),
            name=result["tenant"].name,
            slug=result["tenant"].slug,
            subdomain=result["tenant"].subdomain,
            status=result["tenant"].status.value,
            plan_id=str(result["tenant"].plan_id) if result["tenant"].plan_id else None,
            primary_region=result["tenant"].primary_region.value,
            primary_currency=result["tenant"].primary_currency,
            company_size=result["tenant"].company_size.value if result["tenant"].company_size else None,
            industry=result["tenant"].industry,
            trial_ends_at=result["tenant"].trial_ends_at,
            billing_cycle=result["tenant"].billing_cycle.value,
            fiscal_year_start=result["tenant"].fiscal_year_start,
            date_format=result["tenant"].date_format,
            timezone=result["tenant"].timezone,
            logo_url=result["tenant"].logo_url,
            brand_color=result["tenant"].brand_color,
            onboarding_completed=result["tenant"].onboarding_completed,
            onboarding_step=result["tenant"].onboarding_step,
            settings_json=result["tenant"].settings_json,
            created_at=result["tenant"].created_at,
            updated_at=result["tenant"].updated_at
        )
        
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "message": "Account created successfully! Welcome to the team.",
                "access_token": result["tokens"]["access_token"],
                "refresh_token": result["tokens"]["refresh_token"],
                "token_type": "bearer",
                "expires_in": 86400,
                "user": user_response.model_dump(mode='json'),
                "tenant": tenant_response.model_dump(mode='json'),
                "mfa_setup_required": result.get("mfa_setup_required", False)
            }
        )
        
        # Set refresh token as httpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=result["tokens"]["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=604800  # 7 days
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Accept invitation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation. Please try again."
        )


@router.post(
    "/api/invitations/revoke",
    status_code=status.HTTP_200_OK,
    summary="Revoke invitation",
    description="Revoke pending invitation (Tenant Admin or HR Admin)"
)
async def revoke_invitation(
    request: Request,
    revoke_data: RevokeInviteRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke pending invitation
    
    **Permissions:** Tenant Admin or HR Admin
    
    **Flow:**
    1. Validate user has permission
    2. Check invitation is pending
    3. Mark as revoked
    4. Log security event
    
    **Reasons for revocation:**
    - Employee declined offer
    - Position filled by someone else
    - Invitation sent to wrong email
    - Security concern
    """
    try:
        import uuid
        invitation_id = uuid.UUID(revoke_data.invitation_id)
        ip_address = extract_ip_address(request)
        
        await InvitationService.revoke_invitation(
            invitation_id=invitation_id,
            revoked_by=current_user["sub"],
            reason=revoke_data.reason,
            ip_address=ip_address
        )
        
        return {
            "message": "Invitation revoked successfully",
            "invitation_id": revoke_data.invitation_id
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Revoke invitation failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke invitation. Please try again."
        )
