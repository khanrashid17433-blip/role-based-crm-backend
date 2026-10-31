from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import uuid
import logging
import re

from Models.tenant_registration import TenantRegistration
from Models.email_verification_token import EmailVerificationToken
from Models.tenant_user import Tenant, User, TenantStatus, UserStatus, UserType, AuthProvider
from Models.plan import Plan
from Models.enums import RegistrationStatus, TokenType, CompanySize, PrimaryRegion, BillingCycle
from Schema.registration import RegistrationRequest
from Utility.auth_helpers import (
    hash_password,
    generate_verification_token,
    hash_token,
    check_mx_record,
    is_disposable_email
)
from Utility.exceptions import (
    EmailAlreadyExistsError,
    DisposableEmailError,
    InvalidPromoCodeError,
    TokenExpiredError,
    InvalidTokenError,
    MaxVerificationAttemptsError
)
from Services.auth_service import create_token_pair

logger = logging.getLogger(__name__)


class RegistrationService:
    """Service layer for Registration operations"""
    
    @staticmethod
    async def register_user(
        registration_data: RegistrationRequest,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> TenantRegistration:
        """
        Complete registration flow
        
        Steps:
        1. Validate email (disposable check, MX check)
        2. Check email uniqueness
        3. Validate promo code (if provided)
        4. Hash password
        5. Create tenant registration
        6. Create verification token
        7. Return registration (email sending handled separately)
        """
        
        # Step 1: Check for disposable email
        if is_disposable_email(registration_data.email):
            raise DisposableEmailError("Disposable email addresses are not allowed")
        
        # Step 2: MX record check (warning only, don't block)
        has_mx, mx_error = check_mx_record(registration_data.email)
        if not has_mx:
            logger.warning(f"MX check failed for {registration_data.email}: {mx_error}")
            # Log for review but don't block registration
        
        # Step 3: Check email uniqueness
        existing = await TenantRegistration.find_one(
            TenantRegistration.email == registration_data.email.lower(),
            TenantRegistration.registration_status == RegistrationStatus.pending_verification
        )
        if existing:
            raise EmailAlreadyExistsError(
                f"Email {registration_data.email} is already registered. Please verify your email or login."
            )
        
        # Step 4: Validate promo code (simplified - full validation would check database)
        if registration_data.promo_code:
            # TODO: Implement full promo code validation against database
            logger.info(f"Promo code used: {registration_data.promo_code}")
            # For now, just accept it. In production, validate against promo_codes table
        
        # Step 5: Hash password with Argon2id
        password_hash = hash_password(registration_data.password)
        
        # Step 6: Create tenant registration
        # Normalize company_size from frontend format to backend format if needed
        company_size_value = registration_data.company_size
        if company_size_value in ["1-10", "11-50", "51-200", "201-500", "501-1000", "1000+"]:
            size_mapping = {
                "1-10": "1_10",
                "11-50": "11_50",
                "51-200": "51_200",
                "201-500": "201_500",
                "501-1000": "501_1000",
                "1000+": "1000_plus"
            }
            company_size_value = size_mapping.get(company_size_value, company_size_value)
        
        registration = TenantRegistration(
            email=registration_data.email.lower(),
            first_name=registration_data.first_name.strip(),
            last_name=registration_data.last_name.strip(),
            phone=registration_data.phone,
            password_hash=password_hash,
            company_name=registration_data.company_name.strip(),
            company_size=CompanySize(company_size_value),
            industry=registration_data.industry,
            primary_region=PrimaryRegion(registration_data.primary_region),
            plan_slug=registration_data.plan_slug,
            billing_cycle=BillingCycle(registration_data.billing_cycle),
            promo_code=registration_data.promo_code,
            terms_accepted=registration_data.terms_accepted,
            registration_status=RegistrationStatus.pending_verification,
            verification_attempts=0,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48)
        )
        
        try:
            await registration.insert()
            
            # Step 7: Generate verification token
            plain_token = generate_verification_token()
            token_hash = hash_token(plain_token)
            
            verification_token = EmailVerificationToken(
                registration_id=registration.id,
                user_id=None,  # Will be set after verification
                token_type=TokenType.email_verification,
                token_hash=token_hash,
                email=registration.email,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
                ip_address=ip_address
            )
            await verification_token.insert()
            
            # Return registration with plain token (for email sending)
            registration._verification_token = plain_token  # Temporary attribute
            
            logger.info(f"Registration created: {registration.id} for {registration.email}")
            
            return registration
            
        except Exception as e:
            if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                raise EmailAlreadyExistsError(f"Email {registration_data.email} already exists")
            raise
    
    @staticmethod
    async def verify_email(
        token: str,
        ip_address: Optional[str] = None,
        company_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Verify email using token and create tenant + user
        
        Security: Hash the incoming token and compare with stored hash
        
        Returns:
            Dictionary with registration, tenant, user, and tokens
        """
        # Hash the incoming token
        token_hash = hash_token(token)
        
        # Find the token
        verification_token = await EmailVerificationToken.find_one(
                EmailVerificationToken.token_hash == token_hash,
                EmailVerificationToken.token_type == TokenType.email_verification
            )
        
        if not verification_token:
            raise InvalidTokenError("Invalid verification token")
        
        # Check if token was already used
        if verification_token.used_at is not None:
            raise InvalidTokenError("This verification token has already been used. Please request a new verification email if needed.")
        
        # Check if token has expired
        current_time = datetime.now(timezone.utc)
        # Ensure both datetimes are timezone-aware for comparison
        token_expires_at = verification_token.expires_at
        if token_expires_at.tzinfo is None:
            token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)
            
        if token_expires_at < datetime.now(timezone.utc):
            raise TokenExpiredError("Verification token has expired")
        
        # Get the registration
        registration = await TenantRegistration.find_one(
                TenantRegistration.id == verification_token.registration_id
            )
        
        if not registration:
            raise InvalidTokenError("Registration not found")
        
        # Check verification attempts
        if registration.verification_attempts >= 5:
            raise MaxVerificationAttemptsError(
                "Maximum verification attempts exceeded. Please request a new verification email."
            )
        
        # If company_data is provided (Step 2 flow), update registration
        if company_data:
            from Models.enums import CompanySize, PrimaryRegion, BillingCycle
            
            # Update registration with company details
            registration.company_name = company_data.get('company_name', registration.company_name)
            registration.industry = company_data.get('industry', registration.industry)
            registration.promo_code = company_data.get('promo_code', registration.promo_code)
            
            # Convert company_size from frontend format
            company_size_value = company_data.get('company_size')
            if company_size_value:
                size_mapping = {
                    "1-10": "1_10", "11-50": "11_50", "51-200": "51_200",
                    "201-500": "201_500", "501-1000": "501_1000", "1000+": "1000_plus"
                }
                company_size_value = size_mapping.get(company_size_value, company_size_value)
                registration.company_size = CompanySize(company_size_value)
            
            # Set primary_region
            if company_data.get('primary_region'):
                registration.primary_region = PrimaryRegion(company_data['primary_region'])
            
            # Set plan and billing
            if company_data.get('plan_slug'):
                registration.plan_slug = company_data['plan_slug']
            if company_data.get('billing_cycle'):
                registration.billing_cycle = BillingCycle(company_data['billing_cycle'])
        
        # Check if this is a complete registration (has company details) or just email verification
        is_complete_registration = (
            registration.company_name and 
            registration.company_size and 
            registration.primary_region and 
            registration.plan_slug and 
            registration.billing_cycle
        )
        
        if not is_complete_registration:
            # Just verify the email, don't create tenant yet
            # Mark token as used
            verification_token.used_at = datetime.now(timezone.utc)
            await verification_token.save()
            
            # Update registration status to verified (but not converted)
            registration.registration_status = RegistrationStatus.verified
            registration.verification_attempts += 1
            registration.updated_at = datetime.now(timezone.utc)
            await registration.save()
            
            return {
                "message": "Email verified successfully. Please complete your company details to finish registration.",
                "email_verified": True,
                "registration_complete": False,
                "next_step": "complete_company_details"
            }
        
        # Complete registration flow (create tenant and user)
        # Validate that all required fields are present
        # At this point, we know it's a complete registration, so validate required fields
        if not registration.company_name:
            raise ValueError("Company name is required to complete registration")
        if not registration.company_size:
            raise ValueError("Company size is required")
        if not registration.primary_region:
            raise ValueError("Primary region is required")
        if not registration.plan_slug:
            raise ValueError("Plan selection is required")
        if not registration.billing_cycle:
            raise ValueError("Billing cycle is required")
        
        # Generate tenant slug from company name
        tenant_slug = RegistrationService._generate_tenant_slug(registration.company_name)
        subdomain = tenant_slug
        
        # Get plan details for trial period
        plan = await Plan.find_one(Plan.slug == registration.plan_slug)
        
        # Check if plan has trial enabled
        if plan and plan.has_trial:
            trial_days = plan.trial_days
            tenant_status = TenantStatus.trial
            trial_ends_at = datetime.now(timezone.utc) + timedelta(days=trial_days)
        else:
            # No trial - start as active (requires payment)
            trial_days = 0
            tenant_status = TenantStatus.active
            trial_ends_at = None
        
        # Set regional defaults
        region_defaults = RegistrationService._get_region_defaults(registration.primary_region.value)
        
        # Create tenant
        tenant = Tenant(
            name=registration.company_name,
            slug=tenant_slug,
            subdomain=subdomain,
            status=tenant_status,
            plan_id=plan.id if plan else None,
            primary_region=registration.primary_region,
            primary_currency=region_defaults['currency'],
            company_size=registration.company_size,
            industry=registration.industry,
            trial_ends_at=trial_ends_at,
            billing_cycle=registration.billing_cycle,
            fiscal_year_start=region_defaults['fiscal_year_start'],
            date_format=region_defaults['date_format'],
            timezone=region_defaults['timezone'],
            onboarding_completed=False,
            onboarding_step=1,
            registration_id=registration.id,
            settings_json={}
        )        # Create user
        display_name = f"{registration.first_name} {registration.last_name}".strip()
        
        user = User(
            tenant_id=tenant.id,
            email=registration.email,
            email_verified=True,
            email_verified_at=datetime.now(timezone.utc),
            first_name=registration.first_name,
            last_name=registration.last_name,
            display_name=display_name,
            phone=registration.phone,
            phone_verified=False,
            password_hash=registration.password_hash,
            auth_provider=AuthProvider.local,
            status=UserStatus.active,
            user_type=UserType.tenant_admin,
            last_login_at=None,
            last_login_ip=ip_address,
            failed_login_count=0,
            mfa_enabled=False,
            timezone=region_defaults['timezone'],
            locale=region_defaults['locale'],
            force_password_change=False
        )        # Mark token as used
        verification_token.used_at = datetime.now(timezone.utc)
        
        # Update registration status
        registration.registration_status = RegistrationStatus.verified
        registration.verification_attempts += 1
        registration.converted_at = datetime.now(timezone.utc)
        registration.converted_tenant_id = tenant.id        # Create access token
        tokens = create_token_pair(
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            email=user.email,
            user_type=user.user_type.value
        )
        
        # Create refresh token (opaque)
        from Services.auth_service import create_refresh_token_opaque
        from Models.login_security import RefreshToken
        import uuid
        
        refresh_token_plain, expires_at = create_refresh_token_opaque(remember_me=False)
        refresh_token_hash = hash_token(refresh_token_plain)
        
        # Store refresh token in database
        family_id = uuid.uuid4()
        refresh_token_record = RefreshToken(
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=refresh_token_hash,
            family_id=family_id,
            parent_token_id=None,
            device_fingerprint=None,
            ip_address=ip_address,
            user_agent=None,
            expires_at=expires_at
        )
        
        # Save all objects to database
        await tenant.insert()
        await user.insert()
        await refresh_token_record.insert()
        await verification_token.save()
        await registration.save()
        
        # Add refresh token to response
        tokens["refresh_token"] = refresh_token_plain
        
        logger.info(f"Email verified and tenant created: {tenant.id} for {registration.email}")
        
        return {
            "registration": registration,
            "tenant": tenant,
            "user": user,
            "tokens": tokens
        }
    
    @staticmethod
    async def resend_verification_email(
        email: str,
        ip_address: Optional[str] = None
    ) -> TenantRegistration:
        """
        Resend verification email
        
        Creates a new verification token and updates expiry
        """
        email = email.lower()
        
        # Find pending registration
        registration = await TenantRegistration.find_one(
            TenantRegistration.email == email,
            TenantRegistration.registration_status == RegistrationStatus.pending_verification
        )
        
        if not registration:
            raise InvalidTokenError("No pending registration found for this email")
        
        # Check if expired
        expires_at = registration.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if expires_at < datetime.now(timezone.utc):
            registration.registration_status = RegistrationStatus.abandoned
            await registration.save()
            
            raise TokenExpiredError(
                "Registration has expired. Please create a new account."
            )
        
        # Invalidate old tokens
        await EmailVerificationToken.find(
            EmailVerificationToken.registration_id == registration.id,
            EmailVerificationToken.token_type == TokenType.email_verification,
            EmailVerificationToken.used_at == None
        ).update({"$set": {"used_at": datetime.now(timezone.utc)}})
        
        # Create new token
        plain_token = generate_verification_token()
        token_hash = hash_token(plain_token)
        
        new_token = EmailVerificationToken(
            registration_id=registration.id,
            token_type=TokenType.email_verification,
            token_hash=token_hash,
            email=registration.email,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            ip_address=ip_address
        )
        await new_token.insert()
        
        # Update expiry
        registration.expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
        await registration.save()        # Attach token for email sending
        registration._verification_token = plain_token
        
        logger.info(f"Verification email resent for: {email}")
        
        return registration
    
    @staticmethod
    async def get_registration_by_id(
        registration_id: uuid.UUID
    ) -> Optional[TenantRegistration]:
        """Get registration by ID"""
        return await TenantRegistration.find_one(
            TenantRegistration.id == registration_id
        )
    
    @staticmethod
    async def get_registration_by_email(
        email: str
    ) -> Optional[TenantRegistration]:
        """Get registration by email"""
        return await TenantRegistration.find_one(
            TenantRegistration.email == email.lower()
        )
    
    @staticmethod
    def _generate_tenant_slug(company_name: str) -> str:
        """
        Generate URL-safe tenant slug from company name
        
        Args:
            company_name: Company name
            
        Returns:
            URL-safe slug
        """
        # Convert to lowercase
        slug = company_name.lower()
        
        # Replace spaces and special characters with hyphens
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        
        # Remove leading/trailing hyphens
        slug = slug.strip('-')
        
        # Add random suffix if too common
        if len(slug) < 3:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"
        
        # Truncate to 100 chars
        return slug[:100]
    
    @staticmethod
    def _get_region_defaults(region: str) -> Dict[str, Any]:
        """
        Get regional defaults for currency, timezone, etc.
        
        Args:
            region: Region code (US, UK, IN)
            
        Returns:
            Dictionary with regional settings
        """
        defaults = {
            'US': {
                'currency': 'USD',
                'fiscal_year_start': 1,  # January
                'date_format': 'MM/DD/YYYY',
                'timezone': 'America/New_York',
                'locale': 'en-US'
            },
            'UK': {
                'currency': 'GBP',
                'fiscal_year_start': 4,  # April
                'date_format': 'DD/MM/YYYY',
                'timezone': 'Europe/London',
                'locale': 'en-GB'
            },
            'IN': {
                'currency': 'INR',
                'fiscal_year_start': 4,  # April
                'date_format': 'DD/MM/YYYY',
                'timezone': 'Asia/Kolkata',
                'locale': 'en-IN'
            }
        }
        
        return defaults.get(region, defaults['US'])
