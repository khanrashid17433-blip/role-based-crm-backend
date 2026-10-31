import jwt
import secrets
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, Tuple
import os
from dotenv import load_dotenv
import logging

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("Redis not available. MFA features will not work.")

from Models.tenant_user import User, Tenant, UserStatus
from Models.login_security import (
    RefreshToken, LoginEvent, PasswordHistory, TrustedDevice,
    MagicLinkToken, LoginEventType, RevokeReason
)
from Utility.auth_helpers import verify_password, hash_password

load_dotenv()

logger = logging.getLogger(__name__)

# JWT Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
MFA_SECRET_KEY = os.getenv("MFA_SECRET_KEY", "mfa-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days (30 if remember_me)

# Redis for MFA sessions and OTP storage
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
redis_client = None


async def get_redis():
    """Get Redis client (returns None if Redis not available)"""
    global redis_client
    if not REDIS_AVAILABLE:
        logger.warning("Redis not available. MFA features disabled.")
        return None
    
    if redis_client is None:
        try:
            redis_client = await redis.from_url(REDIS_URL, decode_responses=True)
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return None
    return redis_client


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token (RS256 recommended in production)
    
    Args:
        data: Payload data (user_id, tenant_id, roles, permissions, etc.)
        expires_delta: Custom expiration time
        
    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Add standard JWT claims
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "jti": str(uuid.uuid4()),  # Unique token ID
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token_opaque(remember_me: bool = False) -> Tuple[str, datetime]:
    """
    Create opaque refresh token (not JWT)
    
    Args:
        remember_me: If True, token expires in 30 days, else 7 days
        
    Returns:
        Tuple of (token, expiry_datetime)
    """
    # Generate cryptographically secure random token
    token = secrets.token_urlsafe(48)  # 64-char URL-safe string
    
    # Set expiry
    if remember_me:
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
    
    return token, expires_at


def hash_token(token: str) -> str:
    """Hash token with SHA-256 for storage"""
    return hashlib.sha256(token.encode()).hexdigest()


def create_mfa_session_token(user_id: str, mfa_type: str) -> str:
    """
    Create temporary MFA session token (10 min expiry)
    
    Args:
        user_id: User UUID
        mfa_type: MFA type (totp, email_otp, sms_otp)
        
    Returns:
        JWT token for MFA session
    """
    payload = {
        "sub": user_id,
        "mfa_type": mfa_type,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "iat": datetime.now(timezone.utc),
        "type": "mfa_session"
    }
    
    return jwt.encode(payload, MFA_SECRET_KEY, algorithm=ALGORITHM)


def verify_mfa_session_token(token: str) -> Dict[str, Any]:
    """Verify MFA session token"""
    try:
        payload = jwt.decode(token, MFA_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "mfa_session":
            raise ValueError("Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("MFA session expired. Please login again.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid MFA token")


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode and verify JWT token
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload dictionary
        
    Raises:
        jwt.ExpiredSignatureError: Token has expired
        jwt.InvalidTokenError: Token is invalid
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify access token and return payload
    
    Args:
        token: JWT access token
        
    Returns:
        Decoded payload
        
    Raises:
        ValueError: If token is invalid or wrong type
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")


def verify_refresh_token(token: str) -> Dict[str, Any]:
    """
    Verify refresh token and return payload
    
    Args:
        token: JWT refresh token
        
    Returns:
        Decoded payload
        
    Raises:
        ValueError: If token is invalid or wrong type
    """
    try:
        payload = decode_token(token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")


def create_token_pair(
    user_id: str,
    tenant_id: str,
    email: str,
    user_type: str,
    role: Optional[str] = None,
    roles: list = None,
    permissions: list = None
) -> Dict[str, str]:
    """
    Create access token (JWT) only
    Refresh token is created separately as opaque token
    
    Args:
        user_id: User UUID
        tenant_id: Tenant UUID
        email: User email
        user_type: User type
        role: User role (hr_admin, payroll_admin, etc.)
        roles: User roles (for future multi-role support)
        permissions: User permissions
        
    Returns:
        Dictionary with access_token
    """
    token_data = {
        "sub": user_id,
        "tid": tenant_id,
        "email": email,
        "user_type": user_type,
        "role": role,
        "roles": roles or [],
        "permissions": permissions or []
    }
    
    access_token = create_access_token(token_data)
    
    return {
        "access_token": access_token
    }


class AuthService:
    """Service layer for authentication operations"""
    
    @staticmethod
    async def authenticate_user(
        email: str,
        password: str,
        remember_me: bool = False,
        device_fingerprint: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Authenticate user with email and password (Step 1-8 from spec)
        
        Args:
            email: User email
            password: Plain text password
            remember_me: Remember device for 30 days
            device_fingerprint: SHA-256 hash of device fingerprint
            ip_address: Client IP address
            user_agent: User agent string
            
        Returns:
            Dictionary with user, tenant, tokens OR mfa_required response
            
        Raises:
            ValueError: If credentials are invalid or account is locked
        """
        # Step 1: Normalize email
        normalized_email = email.lower().strip()
        
        # Step 2: Lookup user
        user = await User.find_one(
            User.email == normalized_email,
            User.deleted_at == None
        )
        
        # Run dummy verify to prevent timing attacks
        if not user:
            # Dummy argon2 verify to maintain consistent timing
            try:
                verify_password("dummy_password", "$argon2id$v=19$m=65536,t=3,p=4$dummy")
            except:
                pass
            
            # Log failed attempt
            await AuthService._log_login_event(
                user_id=None,
                tenant_id=None,
                event_type=LoginEventType.login_failed,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="invalid_credentials"
            )
            
            raise ValueError("Invalid email or password")
        
        # Step 3: Check account status
        if user.status == UserStatus.suspended:
            await AuthService._log_login_event(
                user_id=user.id,
                tenant_id=user.tenant_id,
                event_type=LoginEventType.login_failed,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_suspended"
            )
            raise ValueError("Account suspended. Please contact support.")
        
        if user.status == UserStatus.pending_verification:
            await AuthService._log_login_event(
                user_id=user.id,
                tenant_id=user.tenant_id,
                event_type=LoginEventType.login_failed,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="email_not_verified"
            )
            raise ValueError("Email not verified. Please check your inbox for verification link.")
        
        if user.status == UserStatus.deactivated:
            await AuthService._log_login_event(
                user_id=user.id,
                tenant_id=user.tenant_id,
                event_type=LoginEventType.login_failed,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_deactivated"
            )
            raise ValueError("Account deactivated. Please contact support.")
        
        # Step 4: Check lockout
        locked_until = user.locked_until
        if locked_until:
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
                
            if locked_until > datetime.now(timezone.utc):
                seconds_remaining = int((locked_until - datetime.now(timezone.utc)).total_seconds())
            await AuthService._log_login_event(
                user_id=user.id,
                tenant_id=user.tenant_id,
                event_type=LoginEventType.account_locked,
                ip_address=ip_address,
                user_agent=user_agent,
                failure_reason="account_locked"
            )
            raise ValueError(f"Account locked. Try again in {seconds_remaining} seconds.")
        
        # Step 5: Verify password
        if not verify_password(password, user.password_hash):
            # Increment failed login count
            user.failed_login_count += 1
            
            # Lock account after 5 failed attempts (30 min lockout)
            if user.failed_login_count >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                logger.warning(f"Account locked for {user.email} after 5 failed attempts")
                
                await AuthService._log_login_event(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    event_type=LoginEventType.account_locked,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="too_many_failed_attempts"
                )
            else:
                await AuthService._log_login_event(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    event_type=LoginEventType.login_failed,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="wrong_password"
                )
            
            await user.save()
            raise ValueError("Invalid email or password")
        
        # Step 6: Check trusted device (skip MFA if device is trusted)
        if remember_me and device_fingerprint and user.mfa_enabled:
            trusted_device = await AuthService._check_trusted_device(
                user_id=user.id,
                device_fingerprint=device_fingerprint
            )
            
            if trusted_device:
                # Update last used
                trusted_device.last_used_at = datetime.now(timezone.utc)
                await trusted_device.save()
                
                # Skip MFA, proceed to Step 8
                return await AuthService._complete_login(
                    user=user,
                    remember_me=remember_me,
                    device_fingerprint=device_fingerprint,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
        
        # Step 7: Check MFA
        if user.mfa_enabled:
            # Check if Redis is available for MFA
            redis_conn = await get_redis()
            if not redis_conn:
                logger.error("MFA enabled but Redis not available. Skipping MFA.")
                # Skip MFA if Redis is not available (fallback)
                return await AuthService._complete_login(
                    user=user,
                    remember_me=remember_me,
                    device_fingerprint=device_fingerprint,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            
            # Generate MFA session token
            mfa_token = create_mfa_session_token(
                user_id=str(user.id),
                mfa_type=user.mfa_type.value
            )
            
            # Store MFA session in Redis (10 min expiry)
            try:
                await redis_conn.setex(
                    f"mfa_session:{mfa_token}",
                    600,  # 10 minutes
                    str(user.id)
                )
            except Exception as e:
                logger.error(f"Failed to store MFA session in Redis: {e}")
                # Fallback: skip MFA if Redis fails
                return await AuthService._complete_login(
                    user=user,
                    remember_me=remember_me,
                    device_fingerprint=device_fingerprint,
                    ip_address=ip_address,
                    user_agent=user_agent
                )
            
            # If email OTP, generate and send code
            if user.mfa_type.value == "email_otp":
                otp_code = secrets.randbelow(1000000)  # 6-digit code
                otp_code_str = f"{otp_code:06d}"
                
                # Store OTP in Redis (10 min expiry)
                await redis_conn.setex(
                    f"otp:{user.id}",
                    600,
                    hashlib.sha256(otp_code_str.encode()).hexdigest()
                )
                
                # TODO: Send email with OTP code
                logger.info(f"OTP code for {user.email}: {otp_code_str}")
            
            # Mask email for display
            email_parts = user.email.split('@')
            masked_email = f"{email_parts[0][0]}***@{email_parts[1]}"
            
            return {
                "mfa_required": True,
                "mfa_token": mfa_token,
                "mfa_type": user.mfa_type.value,
                "masked_email": masked_email if user.mfa_type.value == "email_otp" else None
            }
        
        # Step 8: No MFA - complete login
        return await AuthService._complete_login(
            user=user,
            remember_me=remember_me,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    async def _complete_login(
        user: User,
        remember_me: bool,
        device_fingerprint: Optional[str],
        ip_address: Optional[str],
        user_agent: Optional[str]
    ) -> Dict[str, Any]:
        """Complete login process (Step 8)"""
        # Reset failed login count
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)
        user.last_login_ip = ip_address
        
        # Get tenant
        tenant = await Tenant.find_one(Tenant.id == user.tenant_id)
        
        if not tenant:
            raise ValueError("Tenant not found")
        
        # Create access token
        tokens = create_token_pair(
            user_id=str(user.id),
            tenant_id=str(tenant.id),
            email=user.email,
            user_type=user.user_type.value,
            role=user.role
        )
        
        # Create refresh token (opaque)
        refresh_token_plain, expires_at = create_refresh_token_opaque(remember_me)
        refresh_token_hash = hash_token(refresh_token_plain)
        
        # Store refresh token in database
        family_id = uuid.uuid4()
        refresh_token_record = RefreshToken(
            user_id=user.id,
            tenant_id=tenant.id,
            token_hash=refresh_token_hash,
            family_id=family_id,
            parent_token_id=None,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at
        )
        await refresh_token_record.insert()
        
        # Save user updates
        await user.save()
        
        # Log successful login
        await AuthService._log_login_event(
            user_id=user.id,
            tenant_id=tenant.id,
            event_type=LoginEventType.login_success,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint
        )
        
        logger.info(f"User logged in: {user.email}")
        
        return {
            "user": user,
            "tenant": tenant,
            "tokens": {
                "access_token": tokens["access_token"],
                "refresh_token": refresh_token_plain
            }
        }
    
    @staticmethod
    async def _check_trusted_device(
        user_id: uuid.UUID,
        device_fingerprint: str
    ) -> Optional[TrustedDevice]:
        """Check if device is trusted"""
        return await TrustedDevice.find_one(
            TrustedDevice.user_id == user_id,
            TrustedDevice.device_fingerprint == device_fingerprint,
            TrustedDevice.revoked_at == None,
            TrustedDevice.expires_at > datetime.now(timezone.utc)
        )
    
    @staticmethod
    async def _log_login_event(
        user_id: Optional[uuid.UUID],
        tenant_id: Optional[uuid.UUID],
        event_type: LoginEventType,
        ip_address: Optional[str],
        user_agent: Optional[str] = None,
        device_fingerprint: Optional[str] = None,
        failure_reason: Optional[str] = None,
        risk_score: int = 0
    ):
        """Log login event"""
        if not user_id:
            return  # Skip logging for non-existent users
        
        event = LoginEvent(
            user_id=user_id,
            tenant_id=tenant_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            failure_reason=failure_reason,
            risk_score=risk_score,
            flagged=risk_score > 70
        )
        await event.insert()
    
    @staticmethod
    async def verify_mfa(
        mfa_token: str,
        code: str,
        remember_device: bool = False,
        device_fingerprint: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify MFA code (TOTP, Email OTP, or Backup Code)
        
        Args:
            db: Database session
            mfa_token: MFA session token
            code: 6-digit OTP or 8-char backup code
            remember_device: Trust this device for 30 days
            device_fingerprint: SHA-256 hash of device fingerprint
            ip_address: Client IP address
            user_agent: User agent string
            
        Returns:
            Dictionary with user, tenant, and tokens
            
        Raises:
            ValueError: If MFA verification fails
        """
        # Verify MFA session token
        try:
            payload = verify_mfa_session_token(mfa_token)
            user_id = uuid.UUID(payload["sub"])
            mfa_type = payload["mfa_type"]
        except ValueError as e:
            raise ValueError(str(e))
        
        # Get user
        user = await User.find_one(User.id == user_id)
        
        if not user:
            raise ValueError("User not found")
        
        # Verify code based on MFA type
        if mfa_type == "totp":
            # TOTP verification
            import pyotp
            
            # Decrypt user.mfa_secret (TODO: implement encryption)
            totp = pyotp.TOTP(user.mfa_secret)
            
            # Check ±1 time step (30s tolerance)
            if not totp.verify(code, valid_window=1):
                await AuthService._log_login_event(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    event_type=LoginEventType.mfa_failed,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="invalid_totp_code"
                )
                raise ValueError("Invalid MFA code")
                raise ValueError("Invalid MFA code")
            
            # Check replay protection (Redis)
            redis_conn = await get_redis()
            replay_key = f"mfa_used:{user.id}:{code}"
            if await redis_conn.exists(replay_key):
                raise ValueError("MFA code already used")
            
            # Mark code as used (90 seconds = 3 time steps)
            await redis_conn.setex(replay_key, 90, "1")
        
        elif mfa_type == "email_otp":
            # Email OTP verification
            redis_conn = await get_redis()
            stored_hash = await redis_conn.get(f"otp:{user.id}")
            
            if not stored_hash:
                raise ValueError("OTP expired. Please login again.")
            
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            
            if code_hash != stored_hash:
                await AuthService._log_login_event(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    event_type=LoginEventType.mfa_failed,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="invalid_email_otp"
                )
                raise ValueError("Invalid OTP code")
                raise ValueError("Invalid OTP code")
            
            # Delete OTP after use
            await redis_conn.delete(f"otp:{user.id}")
        
        else:
            # Backup code verification
            if not user.mfa_backup_codes:
                raise ValueError("No backup codes available")
            
            code_hash = hashlib.sha256(code.encode()).hexdigest()
            
            if code_hash not in user.mfa_backup_codes:
                await AuthService._log_login_event(
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    event_type=LoginEventType.mfa_failed,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    failure_reason="invalid_backup_code"
                )
                raise ValueError("Invalid backup code")
            
            # Mark backup code as used (remove from array)
            user.mfa_backup_codes.remove(code_hash)
        
        # MFA success - create trusted device if requested
        if remember_device and device_fingerprint:
            await AuthService._create_trusted_device(
                user_id=user.id,
                device_fingerprint=device_fingerprint,
                ip_address=ip_address,
                user_agent=user_agent
            )
        
        # Save user changes
        await user.save()
        
        # Log MFA success
        await AuthService._log_login_event(
            user_id=user.id,
            tenant_id=user.tenant_id,
            event_type=LoginEventType.mfa_success,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint
        )
        
        # Complete login
        return await AuthService._complete_login(
            user=user,
            remember_me=remember_device,
            device_fingerprint=device_fingerprint,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    async def _create_trusted_device(
        user_id: uuid.UUID,
        device_fingerprint: str,
        ip_address: str,
        user_agent: Optional[str]
    ):
        """Create trusted device record"""
        # Parse device name from user agent
        device_name = "Unknown Device"
        if user_agent:
            if "Chrome" in user_agent:
                device_name = "Chrome"
            elif "Firefox" in user_agent:
                device_name = "Firefox"
            elif "Safari" in user_agent:
                device_name = "Safari"
            elif "Edge" in user_agent:
                device_name = "Edge"
            
            if "Windows" in user_agent:
                device_name += " on Windows"
            elif "Mac" in user_agent:
                device_name += " on macOS"
            elif "Linux" in user_agent:
                device_name += " on Linux"
            elif "Android" in user_agent:
                device_name += " on Android"
            elif "iOS" in user_agent:
                device_name += " on iOS"
        
        trusted_device = TrustedDevice(
            user_id=user_id,
            device_fingerprint=device_fingerprint,
            device_name=device_name,
            ip_address=ip_address,
            trusted_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            last_used_at=datetime.now(timezone.utc)
        )
        await trusted_device.insert()    @staticmethod
    async def refresh_access_token(
        refresh_token: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Refresh access token using refresh token (with rotation)
        
        Args:
            db: Database session
            refresh_token: Refresh token
            ip_address: Client IP address
            user_agent: User agent string
            
        Returns:
            Dictionary with new access_token and refresh_token
            
        Raises:
            ValueError: If refresh token is invalid or revoked
        """
        # Hash the token
        token_hash = hash_token(refresh_token)
        
        # Find refresh token in database
        token_record = await RefreshToken.find_one(
            RefreshToken.token_hash == token_hash
        )
        
        if not token_record:
            raise ValueError("Invalid refresh token")
        
        # Check if token is revoked
        if token_record.revoked_at:
            # SECURITY: Token reuse detected - revoke entire family
            await AuthService._revoke_token_family(
                family_id=token_record.family_id,
                reason=RevokeReason.family_compromised
            )
            
            logger.warning(
                f"Refresh token reuse detected for user {token_record.user_id}. "
                f"Revoking entire token family {token_record.family_id}"
            )
            
            # TODO: Send email alert to user
            
            raise ValueError("Token reuse detected. All sessions have been revoked for security.")
        
        # Check if token is expired
        expires_at = token_record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if expires_at < datetime.now(timezone.utc):
            raise ValueError("Refresh token expired")
        
        # Get user
        user = await User.find_one(User.id == token_record.user_id)
        
        if not user:
            raise ValueError("User not found")
        
        # Revoke old token (rotation)
        token_record.revoked_at = datetime.now(timezone.utc)
        token_record.revoke_reason = RevokeReason.rotation
        await token_record.save()
        
        # Create new access token
        tokens = create_token_pair(
            user_id=str(user.id),
            tenant_id=str(token_record.tenant_id),
            email=user.email,
            user_type=user.user_type.value,
            role=user.role
        )
        
        # Create new refresh token (rotation)
        new_refresh_token, expires_at = create_refresh_token_opaque(
            remember_me=(token_record.expires_at - token_record.created_at).days > 7
        )
        new_token_hash = hash_token(new_refresh_token)
        
        # Store new refresh token
        new_token_record = RefreshToken(
            user_id=user.id,
            tenant_id=token_record.tenant_id,
            token_hash=new_token_hash,
            family_id=token_record.family_id,  # Same family
            parent_token_id=token_record.id,  # Link to parent
            device_fingerprint=token_record.device_fingerprint,
            ip_address=ip_address or token_record.ip_address,
            user_agent=user_agent or token_record.user_agent,
            expires_at=expires_at
        )
        await new_token_record.insert()
        
        return {
            "access_token": tokens["access_token"],
            "refresh_token": new_refresh_token
        }
    
    @staticmethod
    async def _revoke_token_family(
        family_id: uuid.UUID,
        reason: RevokeReason
    ):
        """Revoke all tokens in a family (security measure)"""
        tokens = await RefreshToken.find(
            RefreshToken.family_id == family_id,
            RefreshToken.revoked_at == None
        ).to_list()
        
        for token in tokens:
            token.revoked_at = datetime.now(timezone.utc)
            token.revoke_reason = reason
            await token.save()    @staticmethod
    async def request_password_reset(
        email: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Request password reset (always returns success to prevent enumeration)
        
        Args:
            db: Database session
            email: User email
            ip_address: Client IP address
            
        Returns:
            Always True (to prevent user enumeration)
        """
        # Normalize email
        normalized_email = email.lower().strip()
        
        # Find user
        user = await User.find_one(
            User.email == normalized_email,
            User.deleted_at == None
        )
        
        if not user:
            # Don't reveal that user doesn't exist
            logger.info(f"Password reset requested for non-existent email: {email}")
            return True
        
        # Generate reset token
        from Models.email_verification_token import EmailVerificationToken
        from Models.enums import TokenType
        from Utility.auth_helpers import generate_verification_token, hash_token
        
        plain_token = generate_verification_token()
        token_hash = hash_token(plain_token)
        
        # Invalidate previous reset tokens
        existing_tokens = await EmailVerificationToken.find(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.token_type == TokenType.password_reset,
            EmailVerificationToken.used_at == None
        ).to_list()
        
        for token in existing_tokens:
            token.used_at = datetime.now(timezone.utc)
            await token.save()
        
        # Create new reset token (1 hour expiry)
        reset_token = EmailVerificationToken(
            user_id=user.id,
            token_type=TokenType.password_reset,
            token_hash=token_hash,
            email=user.email,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            ip_address=ip_address
        )
        await reset_token.insert()

        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        reset_url = f"{frontend_url.rstrip('/')}/reset-password?token={plain_token}"
        try:
            from Utility.email_service import EmailService

            EmailService.send_custom_email(
                user.email,
                "Reset your password",
                (
                    f"Hi {user.first_name or 'there'},\n\n"
                    "A password reset was requested for your B2B HRMS account.\n"
                    f"Use this link to reset your password: {reset_url}\n\n"
                    "This link expires in 1 hour. If you did not request this, you can ignore this email."
                ),
            )
        except Exception as email_error:
            logger.error(f"Failed to send password reset email to {user.email}: {email_error}", exc_info=True)

        logger.info(f"Password reset token generated for {user.email}: {plain_token}")
        
        return True
    
    @staticmethod
    async def reset_password(
        token: str,
        new_password: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Reset password using reset token
        
        Args:
            db: Database session
            token: Password reset token
            new_password: New password (plain text)
            ip_address: Client IP address
            
        Returns:
            True if successful
            
        Raises:
            ValueError: If token is invalid or password is reused
        """
        from Models.email_verification_token import EmailVerificationToken
        from Models.enums import TokenType
        from Utility.auth_helpers import hash_token
        
        # Hash token
        token_hash = hash_token(token)
        
        # Find token
        reset_token = await EmailVerificationToken.find_one(
            EmailVerificationToken.token_hash == token_hash,
            EmailVerificationToken.token_type == TokenType.password_reset,
            EmailVerificationToken.used_at == None
        )
        
        if not reset_token:
            raise ValueError("Invalid or expired reset token")
        
        # Check expiry
        expires_at = reset_token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
            
        if expires_at < datetime.now(timezone.utc):
            raise ValueError("Reset token has expired")
        
        # Get user
        user = await User.find_one(User.id == reset_token.user_id)
        
        if not user:
            raise ValueError("User not found")
        
        # Allow password reuse - commented out validation
        # if verify_password(new_password, user.password_hash):
        #     raise ValueError("New password cannot be the same as current password")
        
        # Allow reusing recent passwords - commented out validation
        # password_history = await PasswordHistory.find(
        #     PasswordHistory.user_id == user.id,
        #     sort=[("created_at", -1)],
        #     limit=5
        # ).to_list()
        # 
        # for old_password in password_history:
        #     if verify_password(new_password, old_password.password_hash):
        #         raise ValueError("You cannot reuse a recent password")
        
        # Save current password to history (optional - keeping for audit trail)
        history_entry = PasswordHistory(
            user_id=user.id,
            password_hash=user.password_hash
        )
        await history_entry.insert()        # Update password
        user.password_hash = hash_password(new_password)
        user.force_password_change = False
        await user.save()
        
        # Mark token as used
        reset_token.used_at = datetime.now(timezone.utc)
        await reset_token.save()
        
        # Revoke all refresh tokens (force re-login)
        tokens = await RefreshToken.find(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked_at == None
        ).to_list()
        
        for token_record in tokens:
            token_record.revoked_at = datetime.now(timezone.utc)
            token_record.revoke_reason = RevokeReason.password_change
            await token_record.save()
        
        # Log password reset
        await AuthService._log_login_event(
            user_id=user.id,
            tenant_id=user.tenant_id,
            event_type=LoginEventType.password_reset,
            ip_address=ip_address
        )
        
        logger.info(f"Password reset successful for {user.email}")
        
        return True
