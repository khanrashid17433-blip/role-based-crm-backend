from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta, timezone
import logging

from Services.registration_service import RegistrationService
from Services.auth_service import AuthService
from Schema.registration import (
    RegistrationRequest,
    RegistrationResponse,
    EmailVerificationRequest,
    ResendVerificationRequest
)
from Schema.tenant_user import (
    VerificationSuccessResponse,
    UserResponse,
    TenantResponse,
    LoginResponse,
    TokenRefreshRequest,
    TokenRefreshResponse
)
from Schema.auth import LoginRequest, MFAVerifyRequest
from Utility.exceptions import (
    EmailAlreadyExistsError,
    DisposableEmailError,
    InvalidPromoCodeError,
    TokenExpiredError,
    InvalidTokenError,
    MaxVerificationAttemptsError
)
from Utility.auth_helpers import (
    extract_ip_address,
    verify_password,
    hash_token
)
from Utility.email_service import send_verification_email
from Utility.rate_limiter import limiter

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================
# REGISTRATION ENDPOINTS
# ============================================

@router.post(
    "/api/auth/register/step1",
    status_code=status.HTTP_201_CREATED,
    summary="Step 1: Create account (Lead)",
    description="First step of registration. Creates a lead/CRM record with account details."
)
@limiter.limit("10/hour")
async def register_step1(
    request: Request
):
    """
    Step 1: Create account details (Lead generation)
    
    **Flow:**
    1. Validates email (disposable check, MX record check)
    2. Checks email uniqueness
    3. Hashes password with Argon2id
    4. Creates lead record (partial registration)
    5. Sends verification email
    
    **Rate Limits:**
    - 10 requests per IP per hour
    - 3 requests per email per day
    """
    from Schema.registration import Step1RegistrationRequest
    from pydantic import ValidationError
    
    try:
        # Parse request body manually to get Step 1 data
        body = await request.json()
        
        # Validate Step 1 fields
        step1_data = Step1RegistrationRequest(**body)
        
        # Extract client information
        ip_address = extract_ip_address(request)
        user_agent = request.headers.get("User-Agent")
        
        # Check for disposable email
        from Utility.auth_helpers import is_disposable_email, check_mx_record
        from Utility.exceptions import DisposableEmailError
        
        if is_disposable_email(step1_data.email):
            raise DisposableEmailError("Disposable email addresses are not allowed")
        
        # MX record check (warning only)
        has_mx, mx_error = check_mx_record(step1_data.email)
        if not has_mx:
            logger.warning(f"MX check failed for {step1_data.email}: {mx_error}")
        
        # Check email uniqueness
        from Models.tenant_registration import TenantRegistration
        
        existing = await TenantRegistration.find_one(
            TenantRegistration.email == step1_data.email.lower(),
            TenantRegistration.registration_status == "pending_verification"
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email {step1_data.email} is already registered. Please verify your email or login."
            )
        
        # Hash password
        from Utility.auth_helpers import hash_password, generate_verification_token, hash_token
        password_hash = hash_password(step1_data.password)
        
        # Combine phone if country_code and phone_number are provided
        import re
        phone = step1_data.phone
        if not phone and step1_data.phone_country_code and step1_data.phone_number:
            country_code = step1_data.phone_country_code.lstrip('+')
            phone_number = re.sub(r'\D', '', step1_data.phone_number)
            phone = f"+{country_code}{phone_number}"
        
        # Create partial registration (lead)
        logger.info(f"Creating lead for {step1_data.email} with phone: {phone}")
        
        registration = TenantRegistration(
            email=step1_data.email.lower(),
            first_name=step1_data.first_name.strip(),
            last_name=step1_data.last_name.strip(),
            phone=phone,
            password_hash=password_hash,
            # Company fields will be filled in Step 2
            company_name=None,
            company_size=None,
            industry=None,
            primary_region=None,
            plan_slug=None,
            billing_cycle=None,
            promo_code=None,
            terms_accepted=step1_data.terms_accepted,
            registration_status="pending_verification",
            verification_attempts=0,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48)
        )
        
        await registration.insert()
        
        # Generate verification token
        plain_token = generate_verification_token()
        token_hash = hash_token(plain_token)
        
        from Models.email_verification_token import EmailVerificationToken
        from Models.enums import TokenType
        
        verification_token = EmailVerificationToken(
            registration_id=registration.id,
            user_id=None,
            token_type=TokenType.email_verification,
            token_hash=token_hash,
            email=registration.email,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            ip_address=ip_address
        )
        
        await verification_token.insert()
        
        # Store token temporarily (will be used after Step 2)
        # Don't send email yet - will send after Step 2
        
        return {
            "message": "Account details saved! Please complete Step 2 with company details.",
            "registration_id": str(registration.id),
            "email": registration.email,
            "next_step": "/complete-registration"
        }
        
    except DisposableEmailError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Step 1 registration failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again later."
        )

# ============================================
# LOGIN ENDPOINTS
# ============================================

@router.post(
    "/api/auth/login",
    status_code=status.HTTP_200_OK,
    summary="Login user",
    description="Authenticate user with email and password. Returns JWT tokens or MFA challenge."
)
@limiter.limit("20/hour")  # 20 login attempts per IP per hour
async def login_user(
    login_data: LoginRequest,
    request: Request
):
    """
    Login user with email and password (Full Spec Implementation)
    
    **Rate Limits:**
    - 5 attempts per email per 15 minutes
    - 20 attempts per IP per hour
    - After 5 failures: 30-min account lockout
    
    **Flow (Steps 1-8):**
    1. Normalize email: LOWER(TRIM(email))
    2. Lookup user with timing attack protection
    3. Check account status (suspended, pending_verification, deactivated)
    4. Check lockout status
    5. Verify password with Argon2id
    6. Check trusted device (skip MFA if trusted)
    7. Check MFA (return 202 with mfa_token if enabled)
    8. Complete login (return 200 with tokens)
    
    **Responses:**
    - 200: Login successful (with tokens)
    - 202: MFA required (with mfa_token)
    - 401: Invalid credentials
    - 403: Account suspended/deactivated/not verified
    - 423: Account locked
    """
    from Schema.auth import MFARequiredResponse, LoginSuccessResponse
    
    try:
        
        ip_address = extract_ip_address(request)
        user_agent = request.headers.get("User-Agent")
        
        # Authenticate user
        result = await AuthService.authenticate_user(
            email=login_data.email,
            password=login_data.password,
            remember_me=login_data.remember_me,
            device_fingerprint=login_data.device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        # Check if MFA is required
        if result.get("mfa_required"):
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "mfa_required": True,
                    "mfa_token": result["mfa_token"],
                    "mfa_type": result["mfa_type"],
                    "masked_email": result.get("masked_email"),
                    "message": "MFA verification required"
                }
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
                "access_token": result["tokens"]["access_token"],
                "refresh_token": result["tokens"]["refresh_token"],
                "token_type": "bearer",
                "expires_in": 86400,  # 24 hours
                "user": user_response.model_dump(mode='json'),
                "tenant": tenant_response.model_dump(mode='json')
            }
        )
        
        # Set refresh token as httpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=result["tokens"]["refresh_token"],
            httponly=True,
            secure=True,  # HTTPS only in production
            samesite="strict",
            max_age=604800 if not login_data.remember_me else 2592000  # 7 or 30 days
        )
        
        return response
        
    except ValueError as e:
        error_msg = str(e)
        
        # Determine appropriate status code
        if "suspended" in error_msg or "deactivated" in error_msg or "not verified" in error_msg:
            status_code = status.HTTP_403_FORBIDDEN
        elif "locked" in error_msg:
            status_code = status.HTTP_423_LOCKED
        else:
            status_code = status.HTTP_401_UNAUTHORIZED
        
        raise HTTPException(
            status_code=status_code,
            detail=error_msg
        )
    except Exception as e:
        logger.error(f"Login failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again later."
        )


# ============================================
# EMAIL VERIFICATION ENDPOINTS
# ============================================

@router.post(
    "/api/auth/register/step2",
    status_code=status.HTTP_200_OK,
    summary="Step 2: Complete company details & send verification",
    description="Complete company details and send verification email."
)
@limiter.limit("20/hour")
async def register_step2(
    request: Request
):
    """
    Step 2: Complete company details
    
    **Flow:**
    1. Finds existing registration by email
    2. Updates with company details
    3. Generates verification token
    4. Sends verification email
    
    **User clicks email link** → Email is verified and tenant+user created
    """
    from pydantic import ValidationError
    from Models.enums import CompanySize, PrimaryRegion, BillingCycle
    
    try:
        body = await request.json()
        
        # Extract email and company details
        email = body.get('email')
        company_data = {
            'company_name': body.get('company_name'),
            'company_size': body.get('company_size'),
            'industry': body.get('industry'),
            'primary_region': body.get('primary_region'),
            'plan_slug': body.get('plan_slug'),
            'billing_cycle': body.get('billing_cycle'),
            'promo_code': body.get('promo_code')
        }
        
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is required"
            )
        
        # Find existing registration
        from Models.tenant_registration import TenantRegistration
        
        registration = await TenantRegistration.find_one(
            TenantRegistration.email == email.lower()
        )
        
        if not registration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration not found. Please complete Step 1 first."
            )
        
        if registration.registration_status == "converted":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Registration already completed. Please login."
            )
        
        ip_address = extract_ip_address(request)
        
        # Update registration with company details
        # Convert company_size from frontend format
        company_size_value = company_data.get('company_size')
        if company_size_value:
            size_mapping = {
                "1-10": "1_10", "11-50": "11_50", "51-200": "51_200",
                "201-500": "201_500", "501-1000": "501_1000", "1000+": "1000_plus"
            }
            company_size_value = size_mapping.get(company_size_value, company_size_value)
            registration.company_size = CompanySize(company_size_value)
        
        registration.company_name = company_data.get('company_name')
        registration.industry = company_data.get('industry')
        registration.promo_code = company_data.get('promo_code')
        
        if company_data.get('primary_region'):
            registration.primary_region = PrimaryRegion(company_data['primary_region'])
        
        if company_data.get('plan_slug'):
            registration.plan_slug = company_data['plan_slug']
        
        if company_data.get('billing_cycle'):
            registration.billing_cycle = BillingCycle(company_data['billing_cycle'])
        
        # Save the updated registration with company data
        await registration.save()
        
        # Generate verification token
        from Utility.auth_helpers import generate_verification_token, hash_token
        plain_token = generate_verification_token()
        token_hash = hash_token(plain_token)
        
        from Models.email_verification_token import EmailVerificationToken
        from Models.enums import TokenType
        
        # Check if verification token already exists
        existing_token = await EmailVerificationToken.find_one(
            EmailVerificationToken.registration_id == registration.id,
            EmailVerificationToken.token_type == TokenType.email_verification
        )
        
        if existing_token:
            # Update existing token
            existing_token.token_hash = token_hash
            existing_token.expires_at = datetime.now(timezone.utc) + timedelta(hours=48)
            existing_token.ip_address = ip_address
            await existing_token.save()
        else:
            # Create new token
            verification_token = EmailVerificationToken(
                registration_id=registration.id,
                user_id=None,
                token_type=TokenType.email_verification,
                token_hash=token_hash,
                email=registration.email,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
                ip_address=ip_address
            )
            await verification_token.insert()
        
        # Send verification email NOW (after Step 2)
        email_sent = send_verification_email(
            to_email=registration.email,
            token=plain_token,
            first_name=registration.first_name,
            company_name=registration.company_name
        )
        
        if email_sent:
            logger.info(f"Verification email sent successfully to {registration.email}")
        else:
            logger.error(f"Failed to send verification email to {registration.email}")
        
        return {
            "message": "Company details saved! Please check your email to verify and complete registration.",
            "registration_id": str(registration.id),
            "email": registration.email,
            "next_step": "/verify-email"
        }
        
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.errors()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Step 2 registration failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again."
        )


@router.post(
    "/api/auth/verify-email",
    response_model=VerificationSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Step 3: Verify email and create tenant",
    description="Verify email using token sent after Step 2. Creates tenant and user account."
)
@limiter.limit("20/hour")
async def verify_email(
    request: Request,
    verification_data: EmailVerificationRequest
):
    """
    Verify email address and create tenant + user.
    
    **This is Step 3 of the registration flow:**
    1. Step 1: Fill account details (creates lead)
    2. Step 2: Fill company details (sends verification email)
    3. Step 3: Verify email (creates tenant + user)
    
    **Flow:**
    1. Hashes token with SHA-256
    2. Looks up token in database
    3. Creates tenant account
    4. Creates user account with Tenant Admin role
    5. Issues JWT access and refresh tokens
    
    **Security:**
    - Token is hashed with SHA-256 before storage
    - Tokens expire after 48 hours
    - Maximum 5 verification attempts
    """
    try:
        ip_address = extract_ip_address(request)
        
        result = await RegistrationService.verify_email(
            token=verification_data.token,
            ip_address=ip_address
        )
        
        # Check if this is just email verification or complete registration
        if not result.get("registration_complete", True):
            # Just email verification, no user/tenant created yet
            return JSONResponse(
                status_code=200,
                content={
                    "message": result["message"],
                    "email_verified": result["email_verified"],
                    "registration_complete": result["registration_complete"],
                    "next_step": result["next_step"]
                }
            )
        
        # Complete registration - convert models to response schemas
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
        
        return VerificationSuccessResponse(
            message="Email verified successfully! Your account is ready.",
            access_token=result["tokens"]["access_token"],
            refresh_token=result["tokens"]["refresh_token"],
            redirect_to="/onboarding/step/1",
            user=user_response,
            tenant=tenant_response
        )
        
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e)
        )
    except MaxVerificationAttemptsError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Email verification failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Verification failed. Please try again."
        )


@router.post(
    "/api/auth/resend-verification",
    status_code=status.HTTP_200_OK,
    summary="Resend verification email",
    description="Request a new verification email if the original expired or was lost"
)
@limiter.limit("5/hour")
async def resend_verification(
    request: Request,
    resend_data: ResendVerificationRequest
):
    """
    Resend verification email to user.
    
    **Notes:**
    - Invalidates previous verification tokens
    - Creates new token with 48-hour expiry
    - Rate limited to prevent abuse
    """
    try:
        ip_address = extract_ip_address(request)
        
        registration = await RegistrationService.resend_verification_email(
            email=resend_data.email,
            ip_address=ip_address
        )
        
        # Send verification email
        verification_token = getattr(registration, '_verification_token', None)
        
        if verification_token:
            email_sent = send_verification_email(
                to_email=registration.email,
                token=verification_token,
                first_name=registration.first_name,
                company_name=registration.company_name
            )
            
            if email_sent:
                logger.info(
                    f"Verification email resent to {registration.email} "
                    f"with new token"
                )
            else:
                logger.error(f"Failed to resend verification email to {registration.email}")
        
        return {
            "message": "Verification email resent. Please check your inbox.",
            "email": registration.email
        }
        
    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(e)
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Resend verification failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resend verification email. Please try again."
        )


@router.get(
    "/api/auth/registration-status/{registration_id}",
    status_code=status.HTTP_200_OK,
    summary="Check registration status",
    description="Check the status of a registration (pending, verified, expired)"
)
async def check_registration_status(
    registration_id: str
):
    """
    Check registration status by ID.
    
    Useful for frontend to poll registration status after submission.
    """
    try:
        import uuid
        registration_uuid = uuid.UUID(registration_id)
        
        registration = await RegistrationService.get_registration_by_id(
            registration_id=registration_uuid
        )
        
        if not registration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Registration not found"
            )
        
        return {
            "registration_id": str(registration.id),
            "email": registration.email,
            "status": registration.registration_status.value,
            "created_at": registration.created_at,
            "expires_at": registration.expires_at,
            "is_expired": (registration.expires_at.replace(tzinfo=timezone.utc) if registration.expires_at.tzinfo is None else registration.expires_at) < datetime.now(timezone.utc)
        }
        
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid registration ID format"
        )
    except Exception as e:
        logger.error(f"Check registration status failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check registration status"
        )



# ============================================
# MFA ENDPOINTS
# ============================================

@router.post(
    "/api/auth/verify-mfa",
    status_code=status.HTTP_200_OK,
    summary="Verify MFA code",
    description="Verify TOTP, Email OTP, or backup code to complete login"
)
@limiter.limit("10/hour")
async def verify_mfa(
    mfa_data: MFAVerifyRequest,
    request: Request
):
    """
    Verify MFA code (TOTP, Email OTP, or Backup Code)
    
    **Flow:**
    1. Verify MFA session token
    2. Check code based on MFA type (TOTP, Email OTP, Backup Code)
    3. Create trusted device if remember_device=true
    4. Issue access + refresh tokens
    
    **Security:**
    - 3 failed MFA attempts → invalidate mfa_token, force re-login
    - TOTP: ±1 time step tolerance (30s), replay protection
    - Email OTP: 10 min expiry, delete after use
    - Backup codes: One-time use, max 10 per account
    """
    from Schema.auth import MFAVerifyRequest
    from fastapi.responses import JSONResponse
    
    try:
        
        ip_address = extract_ip_address(request)
        user_agent = request.headers.get("User-Agent")
        
        # Verify MFA
        result = await AuthService.verify_mfa(
            mfa_token=mfa_data.mfa_token,
            code=mfa_data.code,
            remember_device=mfa_data.remember_device,
            device_fingerprint=mfa_data.device_fingerprint,
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
                "access_token": result["tokens"]["access_token"],
                "refresh_token": result["tokens"]["refresh_token"],
                "token_type": "bearer",
                "expires_in": 86400,
                "user": user_response.model_dump(mode='json'),
                "tenant": tenant_response.model_dump(mode='json')
            }
        )
        
        # Set refresh token as httpOnly cookie
        response.set_cookie(
            key="refresh_token",
            value=result["tokens"]["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=604800 if not mfa_data.remember_device else 2592000
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"MFA verification failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA verification failed. Please try again."
        )


# ============================================
# TOKEN REFRESH ENDPOINT
# ============================================

@router.post(
    "/api/auth/refresh",
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Get new access token using refresh token (with rotation)"
)
@limiter.limit("30/hour")
async def refresh_token(
    request: Request
):
    """
    Refresh access token using refresh token
    
    **Token Rotation:**
    - Every use: old token invalidated, new token issued
    - Stored in refresh_tokens table with family tracking
    
    **Reuse Detection:**
    - If consumed token is presented → REVOKE entire token family
    - Indicates token theft → notify user via email
    
    **Security:**
    - Refresh tokens are opaque (not JWT)
    - Stored as SHA-256 hash
    - httpOnly, Secure, SameSite=Strict cookie
    """
    from Schema.auth import RefreshTokenRequest
    from fastapi.responses import JSONResponse
    
    try:
        # Get refresh token from cookie or body
        refresh_token = request.cookies.get("refresh_token")
        
        if not refresh_token:
            body = await request.json()
            refresh_token_data = RefreshTokenRequest(**body)
            refresh_token = refresh_token_data.refresh_token
        
        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token required"
            )
        
        ip_address = extract_ip_address(request)
        user_agent = request.headers.get("User-Agent")
        
        # Refresh token
        result = await AuthService.refresh_access_token(
            refresh_token=refresh_token,
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "access_token": result["access_token"],
                "refresh_token": result["refresh_token"],
                "token_type": "bearer",
                "expires_in": 86400
            }
        )
        
        # Update refresh token cookie
        response.set_cookie(
            key="refresh_token",
            value=result["refresh_token"],
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=604800
        )
        
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed. Please try again."
        )


# ============================================
# PASSWORD RESET ENDPOINTS
# ============================================

@router.post(
    "/api/auth/forgot-password",
    status_code=status.HTTP_200_OK,
    summary="Request password reset",
    description="Send password reset email (always returns success)"
)
@limiter.limit("3/hour")
async def forgot_password(
    request: Request
):
    """
    Request password reset email
    
    **Security:**
    - Always returns success (prevents user enumeration)
    - Rate limit: 3 per email per hour
    - Token valid for 1 hour
    - Token stored as SHA-256 hash
    
    **Flow:**
    1. User enters email
    2. If email exists → send reset link
    3. If email doesn't exist → show same success message
    """
    from Schema.auth import ForgotPasswordRequest
    
    try:
        body = await request.json()
        forgot_data = ForgotPasswordRequest(**body)
        
        ip_address = extract_ip_address(request)
        
        # Request password reset
        await AuthService.request_password_reset(
            email=forgot_data.email,
            ip_address=ip_address
        )
        
        return {
            "message": "If this email is registered, a password reset link has been sent.",
            "email": forgot_data.email
        }
        
    except Exception as e:
        logger.error(f"Forgot password failed: {str(e)}", exc_info=True)
        # Always return success to prevent enumeration
        return {
            "message": "If this email is registered, a password reset link has been sent."
        }


@router.post(
    "/api/auth/reset-password",
    status_code=status.HTTP_200_OK,
    summary="Reset password",
    description="Reset password using token from email"
)
@limiter.limit("5/hour")
async def reset_password(
    request: Request
):
    """
    Reset password using reset token
    
    **Security:**
    - Cannot be same as current password
    - Cannot be in last 5 passwords (password_history table)
    - Invalidates ALL refresh tokens (force re-login)
    
    **Flow:**
    1. User clicks email link with token
    2. User enters new password
    3. Password validated against history
    4. All sessions revoked
    5. User must login again
    """
    from Schema.auth import ResetPasswordRequest
    
    try:
        body = await request.json()
        reset_data = ResetPasswordRequest(**body)
        
        # Validate passwords match
        if reset_data.new_password != reset_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        ip_address = extract_ip_address(request)
        
        # Reset password
        await AuthService.reset_password(
            token=reset_data.token,
            new_password=reset_data.new_password,
            ip_address=ip_address
        )
        
        return {
            "message": "Password changed successfully. Please log in with your new password."
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Password reset failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Password reset failed. Please try again."
        )


# ============================================
# SSO ENDPOINTS
# ============================================

@router.get(
    "/api/auth/sso-config",
    status_code=status.HTTP_200_OK,
    summary="Check SSO configuration",
    description="Check if email domain has SSO configured"
)
async def check_sso_config(
    email: str
):
    """
    Email Domain → SSO Auto-Detection
    
    **Flow:**
    1. Extract domain from email (e.g., acmecorp.com)
    2. SELECT * FROM sso_configurations WHERE domain = $1 AND is_active = true
    3. If found: return SSO config
    4. Frontend shows "Continue with Acme Corp SSO" button
    
    **Example:**
    - Email: user@acmecorp.com
    - Domain: acmecorp.com
    - Response: { sso_type: "saml", entity_id: "...", sso_url: "..." }
    """
    from Models.login_security import SSOConfiguration
    from Schema.auth import SSOConfigResponse
    
    try:
        # Extract domain
        domain = email.split('@')[1].lower()
        
        # Find SSO configuration
        sso_config = await SSOConfiguration.find_one(
            SSOConfiguration.domain == domain,
            SSOConfiguration.is_active == True
        )
        
        if not sso_config:
            return SSOConfigResponse(
                has_sso=False,
                message="No SSO configuration found for this domain"
            )
        
        return SSOConfigResponse(
            has_sso=True,
            sso_type=sso_config.sso_type.value,
            entity_id=sso_config.saml_entity_id,
            sso_url=sso_config.saml_sso_url,
            message=f"SSO available for {domain}"
        )
        
    except Exception as e:
        logger.error(f"SSO config check failed: {str(e)}", exc_info=True)
        return SSOConfigResponse(
            has_sso=False,
            message="Error checking SSO configuration"
        )


# ============================================
# LOGOUT ENDPOINT
# ============================================

@router.post(
    "/api/auth/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description="Revoke refresh token and clear session"
)
async def logout(
    request: Request
):
    """
    Logout user
    
    **Flow:**
    1. Get refresh token from cookie
    2. Revoke refresh token in database
    3. Clear httpOnly cookie
    4. Log logout event
    """
    from Models.login_security import RefreshToken, RevokeReason
    from fastapi.responses import JSONResponse
    
    try:
        # Get refresh token from cookie
        refresh_token = request.cookies.get("refresh_token")
        
        if refresh_token:
            # Hash token
            token_hash = hash_token(refresh_token)
            
            # Find and revoke token
            token_record = await RefreshToken.find_one(
                RefreshToken.token_hash == token_hash
            )
            
            if token_record and not token_record.revoked_at:
                token_record.revoked_at = datetime.now(timezone.utc)
                token_record.revoke_reason = RevokeReason.logout
                await token_record.save()
                
                # Log logout event
                from Models.login_security import LoginEvent, LoginEventType
                logout_event = LoginEvent(
                    user_id=token_record.user_id,
                    tenant_id=token_record.tenant_id,
                    event_type=LoginEventType.logout,
                    ip_address=extract_ip_address(request),
                    user_agent=request.headers.get("User-Agent")
                )
                await logout_event.insert()
        
        # Clear cookie
        response = JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "Logged out successfully"}
        )
        response.delete_cookie(key="refresh_token")
        
        return response
        
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed. Please try again."
        )


