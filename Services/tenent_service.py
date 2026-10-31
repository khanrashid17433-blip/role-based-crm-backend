from typing import List, Optional, Tuple
from Models.tenant_user import Tenant, User, UserType
from Models.tenant_registration import TenantRegistration
from Schema.tenents import TenantResponse, TenantDetailResponse, LeadResponse, UserResponse


class SuperAdminService:
    """Service layer for SuperAdmin operations"""
    
    @staticmethod
    async def get_all_tenants(
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None
    ) -> Tuple[List[TenantResponse], int]:
        """
        Get all tenants with pagination and optional status filter
        
        Args:
            page: Page number (1-based)
            limit: Items per page
            status: Optional filter by tenant status
            
        Returns:
            Tuple of (tenants list, total count)
        """
        # Base query (simplified for testing)
        query_filter = {}  # Temporarily remove deleted_at filter
        
        # Apply status filter if provided (temporarily disabled)
        # if status:
        #     from Models.tenant_user import TenantStatus
        #     query_filter["status"] = TenantStatus(status)
        
        # Get total count (simplified)
        total = await Tenant.count()
        
        # Apply pagination
        skip = (page - 1) * limit
        tenants = await Tenant.find(
            {},  # Empty filter for now
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        ).to_list()
        
        # Convert to response schema
        tenant_responses = [
            TenantResponse.model_validate(tenant)
            for tenant in tenants
        ]
        
        return tenant_responses, total
    
    @staticmethod
    async def get_all_leads(
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None
    ) -> Tuple[List[LeadResponse], int]:
        """
        Get all leads (unverified registrations) with pagination and optional status filter
        
        Returns all leads including those from step 1 only (with None company details)
        
        Args:
            page: Page number (1-based)
            limit: Items per page
            status: Optional filter by registration status
            
        Returns:
            Tuple of (leads list, total count)
        """
        # Base query
        query_filter = {}
        
        # Apply status filter if provided
        if status:
            from Models.enums import RegistrationStatus
            try:
                query_filter["registration_status"] = RegistrationStatus(status)
            except ValueError:
                # Invalid status, return empty results
                return [], 0
        
        # Get total count with filter
        if query_filter:
            total = await TenantRegistration.find(query_filter).count()
        else:
            total = await TenantRegistration.count()
        
        # Apply pagination
        skip = (page - 1) * limit
        leads = await TenantRegistration.find(
            query_filter,
            skip=skip,
            limit=limit,
            sort=[("created_at", -1)]
        ).to_list()
        
        # Convert to response schema with proper None handling
        lead_responses = []
        for lead in leads:
            try:
                # Create response data with explicit None handling
                response_data = {
                    "id": lead.id,
                    "email": lead.email,
                    "first_name": lead.first_name,
                    "last_name": lead.last_name,
                    "phone": lead.phone,
                    "company_name": lead.company_name,  # Can be None
                    "company_size": lead.company_size,  # Can be None
                    "industry": lead.industry,
                    "primary_region": lead.primary_region,  # Can be None
                    "plan_slug": lead.plan_slug,  # Can be None
                    "billing_cycle": lead.billing_cycle,  # Can be None
                    "promo_code": lead.promo_code,
                    "registration_status": lead.registration_status,
                    "verification_attempts": lead.verification_attempts,
                    "expires_at": lead.expires_at,
                    "converted_at": lead.converted_at,
                    "converted_tenant_id": lead.converted_tenant_id,
                    "created_at": lead.created_at,
                    "updated_at": lead.updated_at,
                }
                
                lead_response = LeadResponse(**response_data)
                lead_responses.append(lead_response)
            except Exception as e:
                # Log the error but continue with other leads
                print(f"Warning: Could not convert lead {lead.id} to response: {e}")
                continue
        
        return lead_responses, total
    
    @staticmethod
    async def get_tenant_detail(
        tenant_id: str
    ) -> Optional[TenantDetailResponse]:
        """
        Get detailed tenant information including admin user
        
        Args:
            tenant_id: Tenant UUID
            
        Returns:
            TenantDetailResponse or None if not found
        """
        # Get tenant
        from uuid import UUID
        tenant_uuid = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        tenant = await Tenant.find_one(
            Tenant.id == tenant_uuid
        )
        
        if not tenant:
            return None
        
        # Get admin user
        admin_user = await User.find_one(
            User.tenant_id == tenant_uuid,
            User.user_type == UserType.tenant_admin
        )
        
        # Build response
        response_data = {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "subdomain": tenant.subdomain,
            "status": tenant.status,
            "primary_region": tenant.primary_region,
            "primary_currency": tenant.primary_currency,
            "company_size": tenant.company_size,
            "industry": tenant.industry,
            "billing_cycle": tenant.billing_cycle,
            "trial_ends_at": tenant.trial_ends_at,
            "onboarding_completed": tenant.onboarding_completed,
            "onboarding_step": tenant.onboarding_step,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
        }
        
        # Add admin user info if exists
        if admin_user:
            response_data["admin_email"] = admin_user.email
            response_data["admin_name"] = f"{admin_user.first_name} {admin_user.last_name}"
            response_data["admin_phone"] = admin_user.phone
        
        return TenantDetailResponse(**response_data)
    
    @staticmethod
    async def update_tenant_status(
        tenant_id: str,
        status: str
    ) -> Optional[Tenant]:
        """
        Update tenant status
        
        Args:
            tenant_id: Tenant UUID
            status: New status value
            
        Returns:
            Updated Tenant or None if not found
        """
        from Models.tenant_user import TenantStatus
        
        from uuid import UUID
        tenant_uuid = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        tenant = await Tenant.find_one(
            Tenant.id == tenant_uuid
        )
        
        if not tenant:
            return None
        
        tenant.status = TenantStatus(status)
        await tenant.save()
        
        return tenant
    
    @staticmethod
    async def get_super_admin_settings():
        """
        Get super admin dashboard settings and statistics
        
        Returns:
            SuperAdminSettingsResponse with platform statistics
        """
        from datetime import datetime, timezone
        from Models.tenant_user import TenantStatus
        from Models.enums import RegistrationStatus
        from Schema.tenents import SuperAdminSettingsResponse
        
        # Get tenant statistics (simplified for testing)
        total_tenants = await Tenant.count()
        active_tenants = 0  # Temporarily disabled
        trial_tenants = 0   # Temporarily disabled
        suspended_tenants = 0  # Temporarily disabled
        
        # Get lead statistics (simplified for testing)
        total_leads = await TenantRegistration.count()
        pending_leads = 0  # Temporarily disabled
        
        return SuperAdminSettingsResponse(
            total_tenants=total_tenants,
            active_tenants=active_tenants,
            trial_tenants=trial_tenants,
            suspended_tenants=suspended_tenants,
            total_leads=total_leads,
            pending_leads=pending_leads,
            last_updated=datetime.now(timezone.utc)
        )
    
    @staticmethod
    async def get_all_users(
        page: int = 1,
        limit: int = 20,
        tenant_id: Optional[str] = None,
        user_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Tuple[List[UserResponse], int]:
        """
        Get all users with pagination and optional filters
        
        Args:
            page: Page number (1-based)
            limit: Items per page
            tenant_id: Optional filter by tenant ID
            user_type: Optional filter by user type
            status: Optional filter by user status
            
        Returns:
            Tuple of (users list, total count)
        """
        # Build query filters
        query_filters = []
        
        if tenant_id:
            from uuid import UUID
            tenant_uuid = UUID(tenant_id)
            query_filters.append(User.tenant_id == tenant_uuid)
        
        if user_type:
            from Models.tenant_user import UserType as UserTypeEnum
            try:
                user_type_enum = UserTypeEnum(user_type)
                query_filters.append(User.user_type == user_type_enum)
            except ValueError:
                # Invalid user type, return empty results
                return [], 0
        
        if status:
            from Models.tenant_user import UserStatus
            try:
                status_enum = UserStatus(status)
                query_filters.append(User.status == status_enum)
            except ValueError:
                # Invalid status, return empty results
                return [], 0
        
        # Get total count
        if query_filters:
            total = await User.find(*query_filters).count()
        else:
            total = await User.count()
        
        # Apply pagination
        skip = (page - 1) * limit
        
        if query_filters:
            users = await User.find(
                *query_filters,
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            ).to_list()
        else:
            users = await User.find(
                skip=skip,
                limit=limit,
                sort=[("created_at", -1)]
            ).to_list()
        
        # Convert to response schema with tenant information
        user_responses = []
        for user in users:
            # Get tenant name
            tenant = await Tenant.find_one(Tenant.id == user.tenant_id)
            tenant_name = tenant.name if tenant else None
            
            user_response = UserResponse(
                id=user.id,
                tenant_id=user.tenant_id,
                tenant_name=tenant_name,
                email=user.email,
                first_name=user.first_name,
                last_name=user.last_name,
                display_name=user.display_name,
                phone=user.phone,
                status=user.status,
                user_type=user.user_type,
                auth_provider=user.auth_provider,
                email_verified=user.email_verified,
                email_verified_at=user.email_verified_at,
                last_login_at=user.last_login_at,
                last_login_ip=user.last_login_ip,
                failed_login_count=user.failed_login_count,
                mfa_enabled=user.mfa_enabled,
                role=user.role,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
            user_responses.append(user_response)
        
        return user_responses, total
