from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Optional, Any, Dict
import logging
from uuid import UUID

from Services.onboarding_service import OnboardingService
from Schema.onboarding import (
    OnboardingProgressResponse,
    DetailedOnboardingProgressResponse,
    InvitationListResponse,
    InvitationResponse,
    Step3TeamInvitesResponse,
    InvitationMemberResponse
)
from Utility.auth_helpers import get_current_user, verify_tenant_admin, verify_platform_admin
from Utility.rate_limiter import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/onboarding")


# ============================================
# ONBOARDING PROGRESS
# ============================================

@router.get(
    "/progress",
    response_model=OnboardingProgressResponse,
    summary="Get onboarding progress",
    description="Get current onboarding step and completion status"
)
async def get_onboarding_progress(
    request: Request,
    current_user = Depends(get_current_user)
):
    """Get current onboarding progress for the user's tenant"""
    try:
        onboarding = await OnboardingService.get_onboarding_progress(UUID(current_user.get('tid')))
        
        if not onboarding:
            # Create initial onboarding record
            onboarding = await OnboardingService.create_onboarding_record(UUID(current_user.get('tid')))
        
        return OnboardingProgressResponse(
            tenant_id=str(onboarding.tenant_id),
            current_step=onboarding.current_step,
            is_completed=onboarding.is_completed,
            step_1_completed=onboarding.step_1_company_profile is not None,
            step_2_completed=onboarding.step_2_entity is not None,
            step_3_completed=onboarding.step_3_team_invites is not None,
            step_4_completed=onboarding.step_4_payroll_config is not None,
            step_5_completed=onboarding.step_5_leave_policy is not None,
            step_6_completed=onboarding.is_completed
        )
    except Exception as e:
        logger.error(f"Failed to get onboarding progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve onboarding progress"
        )


@router.get(
    "/progress/detailed",
    response_model=DetailedOnboardingProgressResponse,
    summary="Get detailed onboarding progress",
    description="Get complete onboarding data with step details for dashboard display"
)
async def get_detailed_onboarding_progress(
    request: Request,
    current_user = Depends(get_current_user)
):
    """
    Get detailed onboarding progress with all step data.
    
    This endpoint returns the actual data entered in each step,
    which can be used to display the company's setup in their dashboard.
    Includes full member list for step 3 team invitations.
    """
    try:
        tenant_id = UUID(current_user.get('tid'))
        onboarding = await OnboardingService.get_onboarding_progress(tenant_id)
        
        if not onboarding:
            # Create initial onboarding record
            onboarding = await OnboardingService.create_onboarding_record(tenant_id)
        
        # Get full team invites with member details
        step_3_data = None
        if onboarding.step_3_team_invites is not None:
            step_3_data = await OnboardingService.get_team_invites_with_details(tenant_id)
        
        return DetailedOnboardingProgressResponse(
            tenant_id=str(onboarding.tenant_id),
            current_step=onboarding.current_step,
            is_completed=onboarding.is_completed,
            completed_at=onboarding.step_6_completion.get('completed_at') if onboarding.step_6_completion else None,
            step_1_completed=onboarding.step_1_company_profile is not None,
            step_2_completed=onboarding.step_2_entity is not None,
            step_3_completed=onboarding.step_3_team_invites is not None,
            step_4_completed=onboarding.step_4_payroll_config is not None,
            step_5_completed=onboarding.step_5_leave_policy is not None,
            step_6_completed=onboarding.is_completed,
            # Include actual step data for dashboard display
            step_1_company_profile=onboarding.step_1_company_profile,
            step_2_entity=onboarding.step_2_entity,
            step_3_team_invites=step_3_data,  # Include full member details
            step_4_payroll_config=onboarding.step_4_payroll_config,
            step_5_leave_policy=onboarding.step_5_leave_policy,
            step_6_completion=onboarding.step_6_completion
        )
    except Exception as e:
        logger.error(f"Failed to get detailed onboarding progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve detailed onboarding progress"
        )


@router.get(
    "/progress/{tenant_id}",
    response_model=DetailedOnboardingProgressResponse,
    summary="Get tenant onboarding progress (Superadmin)",
    description="Get any tenant's onboarding progress (Platform admin only)"
)
async def get_tenant_onboarding_progress(
    request: Request,
    tenant_id: str,
    current_user = Depends(verify_platform_admin)
):
    """
    Get detailed onboarding progress for any tenant.
    
    **Requires:** Platform admin role
    
    This endpoint allows superadmins to view the onboarding status
    and setup details of any company in the system.
    """
    try:
        from uuid import UUID
        
        # Validate tenant_id format
        try:
            tenant_uuid = UUID(tenant_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant ID format"
            )
        
        onboarding = await OnboardingService.get_onboarding_progress(tenant_uuid)
        
        if not onboarding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Onboarding record not found for tenant {tenant_id}"
            )
        
        # Get full team invites with member details
        step_3_data = None
        if onboarding.step_3_team_invites is not None:
            step_3_data = await OnboardingService.get_team_invites_with_details(tenant_uuid)
        
        return DetailedOnboardingProgressResponse(
            tenant_id=str(onboarding.tenant_id),
            current_step=onboarding.current_step,
            is_completed=onboarding.is_completed,
            completed_at=onboarding.step_6_completion.get('completed_at') if onboarding.step_6_completion else None,
            step_1_completed=onboarding.step_1_company_profile is not None,
            step_2_completed=onboarding.step_2_entity is not None,
            step_3_completed=onboarding.step_3_team_invites is not None,
            step_4_completed=onboarding.step_4_payroll_config is not None,
            step_5_completed=onboarding.step_5_leave_policy is not None,
            step_6_completed=onboarding.is_completed,
            # Include actual step data for admin review
            step_1_company_profile=onboarding.step_1_company_profile,
            step_2_entity=onboarding.step_2_entity,
            step_3_team_invites=step_3_data,  # Include full member details
            step_4_payroll_config=onboarding.step_4_payroll_config,
            step_5_leave_policy=onboarding.step_5_leave_policy,
            step_6_completion=onboarding.step_6_completion
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tenant onboarding progress: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tenant onboarding progress"
        )


# ============================================
# PATCH: Update Onboarding Step (Single Endpoint)
# ============================================

@router.patch(
    "/progress",
    status_code=status.HTTP_200_OK,
    summary="Update onboarding progress",
    description="Update onboarding step and save data. Supports steps 1-6."
)
@limiter.limit("30/hour")
async def update_onboarding_progress(
    request: Request,
    current_user = Depends(verify_tenant_admin)
):
    """
    Update onboarding progress for any step.
    
    **Request Body:**
    ```json
    {
      "step": 1,
      "step_data": { ... step-specific data ... }
    }
    ```
    
    **Step 1 - Company Profile:**
    ```json
    {
      "step": 1,
      "step_data": {
        "company_legal_name": "Acme Corp",
        "address_line1": "123 Street",
        "city": "Mumbai",
        "state": "Maharashtra",
        "postal_code": "400001",
        "country": "India",
        "billing_contact_email": "admin@acme.com",
        "fiscal_year_start": 4
      }
    }
    ```
    
    **Step 2 - First Entity:**
    ```json
    {
      "step": 2,
      "step_data": {
        "entity_legal_name": "Acme Corp India",
        "entity_type": "limited_company",
        "country_of_incorporation": "IN",
        "tax_employer_id": "TAN12345E",
        "pay_frequency": "monthly",
        "currency": "INR"
      }
    }
    ```
    
    **Step 3 - Team Invitations:**
    ```json
    {
      "step": 3,
      "step_data": {
        "invitations": [
          {"email": "hr@acme.com", "role": "hr_admin", "first_name": "Jane"}
        ],
        "skip": false
      }
    }
    ```
    
    **Step 4 - Payroll Config:**
    ```json
    {
      "step": 4,
      "step_data": {
        "next_pay_date": "2026-05-01",
        "salary_structure_template": "india_ctc",
        "default_working_hours": 48,
        "overtime_rules": "factories_act"
      }
    }
    ```
    
    **Step 5 - Leave Policy:**
    ```json
    {
      "step": 5,
      "step_data": {
        "leave_policy_template": "india_statutory",
        "annual_leave_days": 21,
        "sick_leave_days": 10,
        "leave_year_start": 4,
        "carry_forward_limit": 10,
        "public_holidays": ["2026-01-26", "2026-08-15"]
      }
    }
    ```
    
    **Step 6 - Complete:**
    ```json
    {
      "step": 6,
      "step_data": {}
    }
    ```
    """
    try:
        # Parse request body
        # Parse request body safely
        try:
            body = await request.json()
        except Exception:
            body = {}
            
        # Get step from query params or body
        step_val = request.query_params.get('step') or body.get('step')
        try:
            step = int(step_val)
        except (TypeError, ValueError):
            step = None
            
        # If 'step_data' key exists, use it. Otherwise, assume the entire body is the data
        step_data = body.get('step_data') if 'step_data' in body else body
        
        if not step or step not in [1, 2, 3, 4, 5, 6]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid step number. Must be 1-6."
            )
        
        # Route to appropriate handler based on step
        if step == 1:
            onboarding = await OnboardingService.complete_step_1(
                tenant_id=UUID(current_user.get('tid')),
                user_id=UUID(current_user.get('sub')),
                data=step_data
            )
            
            return {
                "message": "Company profile saved successfully!",
                "current_step": onboarding.current_step,
                "next_step": "/onboarding/step-2",
                "progress": {
                    "step_1_completed": True,
                    "step_2_completed": onboarding.step_2_entity is not None,
                    "step_3_completed": onboarding.step_3_team_invites is not None,
                    "step_4_completed": onboarding.step_4_payroll_config is not None,
                    "step_5_completed": onboarding.step_5_leave_policy is not None,
                    "is_completed": onboarding.is_completed
                }
            }
        
        elif step == 2:
            onboarding = await OnboardingService.complete_step_2(
                tenant_id=UUID(current_user.get('tid')),
                user_id=UUID(current_user.get('sub')),
                data=step_data
            )
            
            return {
                "message": "Entity created successfully!",
                "current_step": onboarding.current_step,
                "next_step": "/onboarding/step-3",
                "progress": {
                    "step_1_completed": onboarding.step_1_company_profile is not None,
                    "step_2_completed": True,
                    "step_3_completed": onboarding.step_3_team_invites is not None,
                    "step_4_completed": onboarding.step_4_payroll_config is not None,
                    "step_5_completed": onboarding.step_5_leave_policy is not None,
                    "is_completed": onboarding.is_completed
                }
            }
        
        elif step == 3:
            result = await OnboardingService.complete_step_3(
                tenant_id=UUID(current_user.get('tid')),
                user_id=UUID(current_user.get('sub')),
                data={
                    **step_data,
                    'inviter_name': f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
                    'company_name': 'the platform'
                },
                skip=step_data.get('skip', False)
            )
            
            return {
                "message": f"Successfully sent {len(result['invitations_sent'])} invitations!",
                "current_step": result['onboarding'].current_step,
                "invitations_sent": result['invitations_sent'],
                "total_invites": result['total_invites'],
                "next_step": "/onboarding/step-4",
                "progress": {
                    "step_1_completed": result['onboarding'].step_1_company_profile is not None,
                    "step_2_completed": result['onboarding'].step_2_entity is not None,
                    "step_3_completed": True,
                    "step_4_completed": result['onboarding'].step_4_payroll_config is not None,
                    "step_5_completed": result['onboarding'].step_5_leave_policy is not None,
                    "is_completed": result['onboarding'].is_completed
                }
            }
        
        elif step == 4:
            onboarding = await OnboardingService.complete_step_4(
                tenant_id=UUID(current_user.get('tid')),
                user_id=UUID(current_user.get('sub')),
                data=step_data
            )
            
            return {
                "message": "Payroll configuration saved!",
                "current_step": onboarding.current_step,
                "next_step": "/onboarding/step-5",
                "progress": {
                    "step_1_completed": onboarding.step_1_company_profile is not None,
                    "step_2_completed": onboarding.step_2_entity is not None,
                    "step_3_completed": onboarding.step_3_team_invites is not None,
                    "step_4_completed": True,
                    "step_5_completed": onboarding.step_5_leave_policy is not None,
                    "is_completed": onboarding.is_completed
                }
            }
        
        elif step == 5:
            onboarding = await OnboardingService.complete_step_5(
                tenant_id=UUID(current_user.get('tid')),
                user_id=UUID(current_user.get('sub')),
                data=step_data
            )
            
            return {
                "message": "Leave policy configured!",
                "current_step": onboarding.current_step,
                "next_step": "/onboarding/complete",
                "progress": {
                    "step_1_completed": onboarding.step_1_company_profile is not None,
                    "step_2_completed": onboarding.step_2_entity is not None,
                    "step_3_completed": onboarding.step_3_team_invites is not None,
                    "step_4_completed": onboarding.step_4_payroll_config is not None,
                    "step_5_completed": True,
                    "is_completed": onboarding.is_completed
                }
            }
        
        elif step == 6:
            onboarding = await OnboardingService.complete_onboarding(
                tenant_id=UUID(current_user.get('tid')),
                user_id=UUID(current_user.get('sub'))
            )
            
            return {
                "message": "🎉 Welcome to the platform! Onboarding complete!",
                "is_completed": True,
                "redirect_to": "/dashboard",
                "progress": {
                    "step_1_completed": True,
                    "step_2_completed": True,
                    "step_3_completed": True,
                    "step_4_completed": True,
                    "step_5_completed": True,
                    "is_completed": True
                }
            }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update onboarding step {step}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update onboarding progress"
        )


# ============================================
# INVITATIONS MANAGEMENT
# ============================================

@router.get(
    "/invitations",
    response_model=InvitationListResponse,
    summary="List team invitations",
    description="Get all pending and accepted invitations"
)
async def list_invitations(
    request: Request,
    status_filter: Optional[str] = None,
    current_user = Depends(verify_tenant_admin)
):
    """List all invitations for the tenant"""
    try:
        invitations = await OnboardingService.get_invitations(
            tenant_id=UUID(current_user.get('tid')),
            status=status_filter
        )
        
        invitation_responses = [
            InvitationResponse(
                id=str(inv.id),
                email=inv.email,
                first_name=inv.first_name,
                last_name=inv.last_name,
                role=inv.role if isinstance(inv.role, str) else inv.role.value,
                status=inv.status if isinstance(inv.status, str) else inv.status.value,
                expires_at=inv.expires_at.isoformat() if inv.expires_at else None,
                accepted_at=inv.accepted_at.isoformat() if inv.accepted_at else None
            )
            for inv in invitations
        ]
        
        return InvitationListResponse(
            invitations=invitation_responses,
            total=len(invitation_responses),
            pending_count=len([i for i in invitations if (i.status if isinstance(i.status, str) else i.status.value) == 'pending']),
            accepted_count=len([i for i in invitations if (i.status if isinstance(i.status, str) else i.status.value) == 'accepted'])
        )
    except Exception as e:
        logger.error(f"Failed to list invitations: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve invitations"
        )


@router.post(
    "/invitations/{invitation_id}/resend",
    status_code=status.HTTP_200_OK,
    summary="Resend invitation",
    description="Resend invitation email to a team member"
)
async def resend_invitation(
    request: Request,
    invitation_id: str,
    current_user = Depends(verify_tenant_admin)
):
    """Resend an invitation email"""
    try:
        from uuid import UUID
        invitation, plain_token = await OnboardingService.resend_invitation(
            invitation_id=UUID(invitation_id)
        )
        
        # Send email
        frontend_url = "http://localhost:3000"
        invite_url = f"{frontend_url}/accept-invite?token={plain_token}"
        
        from Utility.email_service import send_invitation_email
        email_sent = send_invitation_email(
            to_email=invitation.email,
            invitation_url=invite_url,
            invited_by_name=f"{current_user.get('first_name', '')} {current_user.get('last_name', '')}".strip(),
            role=invitation.role,  # Already a string, no need for .value
            company_name='the platform'
        )
        
        return {
            "message": f"Invitation resent to {invitation.email}",
            "email_sent": email_sent
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to resend invitation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend invitation"
        )
