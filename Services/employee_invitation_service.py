from typing import Optional, Dict, Any
from uuid import UUID
import secrets
import hashlib
from datetime import datetime, timedelta

from Services.employee_service import EmployeeService
from Models.employee import Employee, EmploymentStatus
from Models.onboarding import UserInvitation
from Models.enums import InvitationStatus
from Models.tenant_user import User, UserType, UserStatus
from Schema.employee import EmployeeCreateSchema
from Schema.invitation import InvitationCreateSchema
from Utility.exceptions import ValidationError, NotFoundError, ConflictError
from Utility.email_service import EmailService

class EmployeeInvitationService:
    def __init__(self):
        self.employee_service = EmployeeService()
        self.email_service = EmailService()

    async def create_invitation(self, invitation_data: InvitationCreateSchema, tenant_id: UUID, 
                         invited_by: UUID) -> UserInvitation:
        """Create a new invitation"""
        
        # Check plan limit for admin users if inviting an admin
        is_admin = False
        if invitation_data.user_type in [UserType.admin_user, UserType.tenant_admin] or invitation_data.role in ['admin', 'super_admin']:
            is_admin = True
            
        if is_admin:
            from Models.tenant_user import Tenant
            from Models.plan import Plan
            tenant = await Tenant.find_one(Tenant.id == tenant_id)
            if tenant and tenant.plan_id:
                plan = await Plan.find_one(Plan.id == tenant.plan_id)
                if plan and plan.max_admin_users != -1:
                    # Count current admins (active users)
                    current_admins = await User.find(
                        User.tenant_id == tenant_id,
                        {"$or": [{"user_type": UserType.admin_user}, {"user_type": UserType.tenant_admin}, {"role": "admin"}]}
                    ).count()
                    
                    # Also count pending admin invitations
                    pending_admin_invites = await UserInvitation.find(
                        UserInvitation.tenant_id == tenant_id,
                        UserInvitation.status == "pending",
                        {"$or": [{"user_type": UserType.admin_user.value}, {"user_type": UserType.tenant_admin.value}, {"role": "admin"}]}
                    ).count()
                    
                    if (current_admins + pending_admin_invites) >= plan.max_admin_users:
                        raise ConflictError(f"Admin user limit reached. Your plan allows a maximum of {plan.max_admin_users} admin users.")

        # Check if user already exists
        existing_user = await User.find_one(
            User.email == invitation_data.email,
            User.tenant_id == tenant_id
        )
        
        if existing_user:
            raise ConflictError("User with this email already exists")
        
        # Check if pending invitation exists
        existing_invitation = await UserInvitation.find_one(
            UserInvitation.email == invitation_data.email,
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.status == "pending",
            UserInvitation.expires_at > datetime.utcnow()
        )
        
        if existing_invitation:
            raise ConflictError("Pending invitation already exists for this email")
        
        # Generate token
        plain_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
        
        # Create invitation
        invitation = UserInvitation(
            tenant_id=tenant_id,
            invited_by=invited_by,
            email=invitation_data.email.lower().strip(),
            first_name=invitation_data.first_name,
            last_name=invitation_data.last_name,
            phone=invitation_data.phone,
            role=invitation_data.role,
            user_type=invitation_data.user_type.value if invitation_data.user_type else "employee",
            employee_id=invitation_data.employee_id,
            token_hash=token_hash,
            status="pending",
            expires_at=datetime.utcnow() + timedelta(days=7),
            personal_details_json=invitation_data.personal_details or {},
            notification_prefs_json=invitation_data.notification_prefs or {}
        )
        
        await invitation.insert()
        
        # Store plain token for email
        invitation.token = plain_token
        
        return invitation

    async def get_invitation_by_token(self, token: str) -> Optional[UserInvitation]:
        """Get invitation by token"""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        return await UserInvitation.find_one(
            UserInvitation.token_hash == token_hash
        )

    async def accept_invitation(self, token: str) -> UserInvitation:
        """Mark invitation as accepted"""
        invitation = await self.get_invitation_by_token(token)
        if not invitation:
            raise NotFoundError("Invalid invitation token")
        
        invitation.status = "accepted"
        invitation.accepted_at = datetime.utcnow()
        await invitation.save()
        
        return invitation

    async def invite_employee(self, employee_data: EmployeeCreateSchema, tenant_id: UUID, 
                       invited_by: UUID, send_invitation: bool = True) -> Dict[str, Any]:
        """
        Create employee record and send invitation email
        
        Args:
            employee_data: Employee creation data
            tenant_id: Tenant ID
            invited_by: User ID who is inviting
            send_invitation: Whether to send invitation email
            
        Returns:
            Dict containing employee and invitation details
        """
        try:
            # Validate email is provided for invitation
            if send_invitation and not employee_data.email_work:
                raise ValidationError("Work email is required to send invitation")
            
            # Check if user with this email already exists
            if employee_data.email_work:
                existing_user = await User.find_one(
                    User.email == employee_data.email_work
                )
                
                if existing_user:
                    # Check if user belongs to same tenant
                    if existing_user.tenant_id == tenant_id:
                        # Check if already linked to an employee
                        existing_employee = await Employee.find_one(
                            Employee.user_id == existing_user.id
                        )
                        if existing_employee:
                            raise ConflictError("User is already linked to an employee")
                        
                        # Link existing user to new employee record
                        employee = await self.employee_service.create_employee(
                            employee_data, tenant_id, invited_by
                        )
                        employee = await self.employee_service.link_user_to_employee(
                            employee.id, existing_user.id, tenant_id
                        )
                        
                        return {
                            "employee": employee,
                            "invitation": None,
                            "message": "Employee created and linked to existing user account"
                        }
                    else:
                        raise ConflictError("User with this email exists in another tenant")
            
            # Create employee record
            employee = await self.employee_service.create_employee(
                employee_data, tenant_id, invited_by
            )
            
            invitation = None
            if send_invitation and employee_data.email_work:
                # Create invitation
                invitation_data = InvitationCreateSchema(
                    email=employee_data.email_work,
                    first_name=employee_data.first_name,
                    last_name=employee_data.last_name,
                    role="employee",
                    user_type=UserType.employee,
                    employee_id=employee.id
                )
                
                invitation = await self.create_invitation(
                    invitation_data, tenant_id, invited_by
                )
                
                # Send invitation email
                try:
                    await self._send_employee_invitation_email(employee, invitation, tenant_id)
                except Exception as e:
                    # Log email error but don't fail the entire process
                    print(f"Failed to send invitation email: {str(e)}")
            
            return {
                "employee": employee,
                "invitation": invitation,
                "message": "Employee created successfully" + 
                          (" and invitation sent" if invitation else "")
            }
            
        except Exception as e:            raise e

    async def accept_employee_invitation(self, invitation_token: str, password: str, 
                                 additional_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Accept employee invitation and create user account
        
        Args:
            invitation_token: Invitation token
            password: User's chosen password
            additional_info: Additional user information
            
        Returns:
            Dict containing user and employee details
        """
        try:
            # Get invitation
            invitation = await self.get_invitation_by_token(invitation_token)
            if not invitation:
                raise NotFoundError("Invalid or expired invitation")
            
            if invitation.status != "pending":
                raise ValidationError("Invitation has already been processed")
            
            # Get employee record
            employee = None
            if invitation.employee_id:
                employee = await self.employee_service.get_employee_by_id(
                    invitation.employee_id, invitation.tenant_id
                )
                if not employee:
                    raise NotFoundError("Employee record not found")
            
            # Create user account
            from Utility.auth_helpers import hash_password
            
            user = User(
                tenant_id=invitation.tenant_id,
                email=invitation.email,
                first_name=invitation.first_name,
                last_name=invitation.last_name,
                password_hash=hash_password(password),
                user_type=UserType.employee,
                role=invitation.role,
                status=UserStatus.ACTIVE,
                email_verified=True,
                email_verified_at=datetime.utcnow(),
                created_by=invitation.invited_by
            )
            
            # Add additional info if provided
            if additional_info:
                for key, value in additional_info.items():
                    if hasattr(user, key):
                        setattr(user, key, value)
            
            await user.insert()
            
            # Link user to employee if employee record exists
            if employee:
                employee = await self.employee_service.link_user_to_employee(
                    employee.id, user.id, invitation.tenant_id
                )
            
            # Mark invitation as accepted
            await self.accept_invitation(invitation_token)
            
            return {
                "user": user,
                "employee": employee,
                "message": "Invitation accepted successfully"
            }
            
        except Exception as e:            raise e

    async def create_employee_manually(self, employee_data: EmployeeCreateSchema, 
                                tenant_id: UUID, created_by: UUID) -> Employee:
        """
        Create employee manually without invitation (for existing users or manual entry)
        
        Args:
            employee_data: Employee creation data
            tenant_id: Tenant ID
            created_by: User ID who is creating the employee
            
        Returns:
            Created employee
        """
        try:
            # Create employee record
            employee = await self.employee_service.create_employee(
                employee_data, tenant_id, created_by
            )
            
            # If work email is provided, try to link to existing user
            if employee_data.email_work:
                existing_user = await User.find_one(
                    User.email == employee_data.email_work,
                    User.tenant_id == tenant_id
                )
                
                if existing_user:
                    # Check if user is not already linked to another employee
                    existing_employee = await Employee.find_one(
                        Employee.user_id == existing_user.id
                    )
                    
                    if not existing_employee:
                        employee = await self.employee_service.link_user_to_employee(
                            employee.id, existing_user.id, tenant_id
                        )
            
            return employee
            
        except Exception as e:            raise e

    async def get_employee_invitation_status(self, employee_id: UUID, tenant_id: UUID) -> Dict[str, Any]:
        """
        Get invitation status for an employee
        
        Args:
            employee_id: Employee ID
            tenant_id: Tenant ID
            
        Returns:
            Dict containing invitation status information
        """
        employee = await self.employee_service.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        # Check if employee has a user account
        has_user_account = employee.user_id is not None
        
        # Check for pending invitations
        pending_invitation = None
        if employee.email_work:
            pending_invitation = await UserInvitation.find_one(
                UserInvitation.email == employee.email_work,
                UserInvitation.tenant_id == tenant_id,
                UserInvitation.status == "pending",
                UserInvitation.employee_id == employee_id
            )
        
        return {
            "employee_id": employee_id,
            "has_user_account": has_user_account,
            "employment_status": employee.employment_status,
            "pending_invitation": pending_invitation is not None,
            "invitation_sent_at": pending_invitation.created_at if pending_invitation else None,
            "can_send_invitation": not has_user_account and employee.email_work and not pending_invitation
        }

    async def resend_employee_invitation(self, employee_id: UUID, tenant_id: UUID, 
                                 resent_by: UUID) -> Dict[str, Any]:
        """
        Resend invitation to an employee
        
        Args:
            employee_id: Employee ID
            tenant_id: Tenant ID
            resent_by: User ID who is resending
            
        Returns:
            Dict containing resend status
        """
        employee = await self.employee_service.get_employee_by_id(employee_id, tenant_id)
        if not employee:
            raise NotFoundError("Employee not found")
        
        if not employee.email_work:
            raise ValidationError("Employee does not have a work email")
        
        if employee.user_id:
            raise ValidationError("Employee already has a user account")
        
        # Check for existing pending invitation
        existing_invitation = await UserInvitation.find_one(
            UserInvitation.email == employee.email_work,
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.status == "pending",
            UserInvitation.employee_id == employee_id
        )
        
        if existing_invitation:
            # Update invitation with new token and expiry
            existing_invitation.token_hash = hashlib.sha256(secrets.token_urlsafe(32).encode()).hexdigest()
            existing_invitation.expires_at = datetime.utcnow() + timedelta(days=7)
            existing_invitation.updated_at = datetime.utcnow()
            await existing_invitation.save()
            
            # Send invitation email
            try:
                await self._send_employee_invitation_email(employee, existing_invitation, tenant_id)
                return {
                    "message": "Invitation resent successfully",
                    "invitation_id": existing_invitation.id
                }
            except Exception as e:
                raise ValidationError(f"Failed to send invitation email: {str(e)}")
        else:
            # Create new invitation
            invitation_data = InvitationCreateSchema(
                email=employee.email_work,
                first_name=employee.first_name,
                last_name=employee.last_name,
                role="employee",
                user_type=UserType.employee,
                employee_id=employee.id
            )
            
            invitation = await self.create_invitation(
                invitation_data, tenant_id, resent_by
            )
            
            # Send invitation email
            try:
                await self._send_employee_invitation_email(employee, invitation, tenant_id)
                return {
                    "message": "New invitation sent successfully",
                    "invitation_id": invitation.id
                }
            except Exception as e:
                raise ValidationError(f"Failed to send invitation email: {str(e)}")

    async def _send_employee_invitation_email(self, employee: Employee, invitation: UserInvitation, 
                                      tenant_id: UUID):
        """
        Send invitation email to employee
        
        Args:
            employee: Employee record
            invitation: Invitation record
            tenant_id: Tenant ID
        """
        # Get tenant information
        from Models.tenant_user import Tenant
        tenant = await Tenant.find_one(Tenant.id == tenant_id)
        
        if not tenant:
            raise ValidationError("Tenant not found")
        
        # Prepare email data
        email_data = {
            "to_email": employee.email_work,
            "to_name": f"{employee.first_name} {employee.last_name}",
            "subject": f"Welcome to {tenant.name} - Complete Your Account Setup",
            "template": "employee_invitation",
            "template_data": {
                "employee_name": f"{employee.first_name} {employee.last_name}",
                "company_name": tenant.name,
                "employee_number": employee.employee_number,
                "invitation_token": invitation.token,
                "invitation_url": f"{self._get_frontend_url()}/accept-invitation/{invitation.token}",
                "expires_at": invitation.expires_at.strftime("%B %d, %Y at %I:%M %p"),
                "support_email": "support@company.com"  # Configure this
            }
        }
        
        # Send email
        self.email_service.send_email(email_data)

    def _get_frontend_url(self) -> str:
        """Get frontend URL from environment or config"""
        import os
        return os.getenv("FRONTEND_URL", "http://localhost:3000")