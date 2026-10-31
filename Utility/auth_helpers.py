import hashlib
import secrets
import re
import logging
from typing import Optional, Tuple
import bcrypt
import dns.resolver
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logger
logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer()


# BCrypt configuration for password hashing
BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)  # 12 cost factor
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')  # gives $2a$ / $2b$ format


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )

def generate_verification_token() -> str:
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def check_mx_record(email: str) -> Tuple[bool, Optional[str]]:
    try:
        domain = email.split('@')[1]
        mx_records = dns.resolver.resolve(domain, 'MX')
        if mx_records:
            return True, None
        return False, f"No MX records found for domain {domain}"
    except dns.resolver.NoAnswer:
        return False, f"No MX records found for domain {domain}"
    except dns.resolver.NXDOMAIN:
        return False, f"Domain {domain} does not exist"
    except Exception as e:
        return False, f"MX check failed: {str(e)}"


def is_disposable_email(email: str) -> bool:
    disposable_domains = {
    }
    
    domain = email.lower().split('@')[1]
    return domain in disposable_domains


def validate_email_format(email: str) -> Tuple[bool, Optional[str]]:
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        return False, "Invalid email format"
    if '+' in email:
        return False, "Email aliases with + are not allowed"
    
    # Check disposable
    if is_disposable_email(email):
        return False, "Disposable email addresses are not allowed"
    
    # Check common typos
    common_typos = {
        'gmial.com': 'gmail.com',
        'gmal.com': 'gmail.com',
        'yaho.com': 'yahoo.com',
        'hotmal.com': 'hotmail.com',
    }
    domain = email.split('@')[1]
    if domain in common_typos:
        return False, f"Did you mean {email.split('@')[0]}@{common_typos[domain]}?"
    
    return True, None


def extract_ip_address(request) -> Optional[str]:
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip
    
    # Fallback to client host
    return request.client.host if request.client else None


def calculate_password_strength(password: str) -> dict:
    """
    Calculate password strength score and feedback
    
    Args:
        password: Password to check
        
    Returns:
        Dictionary with score (0-4) and feedback
    """
    score = 0
    feedback = []
    
    # Length check
    if len(password) >= 12:
        score += 1
    else:
        feedback.append("Password should be at least 12 characters")
    
    # Uppercase check
    if re.search(r'[A-Z]', password):
        score += 1
    else:
        feedback.append("Add uppercase letters")
    
    # Lowercase check
    if re.search(r'[a-z]', password):
        score += 1
    else:
        feedback.append("Add lowercase letters")
    
    # Number check
    if re.search(r'\d', password):
        score += 1
    else:
        feedback.append("Add numbers")
    
    # Special character check
    if re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', password):
        score += 1
    else:
        feedback.append("Add special characters")
    
    return {
        "score": min(score, 4),  # Cap at 4
        "feedback": feedback,
        "strength": ["Very Weak", "Weak", "Fair", "Strong", "Very Strong"][min(score, 4)]
    }


async def verify_platform_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify JWT token and check if user is platform_admin or admin
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        User payload from JWT token
        
    Raises:
        HTTPException: If token is invalid or user is not admin
    """
    try:
        # Get secret key from environment
        secret_key = os.getenv("SECRET_KEY", "dev-secret-key-12345")
        
        # Decode and verify JWT token
        payload = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=["HS256"]
        )
        
        # Check if user is admin (platform_admin, tenant_admin, or admin role)
        user_type = payload.get("user_type")
        user_role = payload.get("role", "")
        
        # Check if user has explicit CRM read permission in the database
        from Utility.permissions import has_permission
        from uuid import UUID
        
        user_id = UUID(payload.get("sub"))
        tenant_id = UUID(payload.get("tid") or payload.get("tenant_id"))
        
        has_crm_read = False
        try:
            has_crm_read = await has_permission(user_id, tenant_id, "crm", "read")
        except Exception as e:
            logger.warning(f"Error checking CRM permissions in verify_platform_admin: {e}")
        
        # Allow platform_admin, tenant_admin, admin user_type, or admin/sales/manager roles, or has_crm_read
        if (user_type in ["platform_admin", "tenant_admin", "admin"] or 
            user_role in ["admin", "tenant_admin", "super_admin", "sales", "sales_executive", "manager"] or
            has_crm_read):
            return payload
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin, Sales, or Manager role required."
        )
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


async def validate_tenant_status(payload: dict) -> None:
    tenant_id = payload.get("tenant_id") or payload.get("tid")
    user_type = payload.get("user_type")
    
    # Platform admin is global and exempt from tenant restrictions
    if tenant_id and user_type != "platform_admin":
        from uuid import UUID
        from Models.tenant_user import Tenant, TenantStatus
        from datetime import datetime, timezone
        
        tenant = await Tenant.find_one(Tenant.id == UUID(tenant_id))
        if not tenant or tenant.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Workspace not found or has been deleted."
            )
        
        if tenant.status in [TenantStatus.suspended, TenantStatus.cancelled, TenantStatus.churned]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Your workspace status is currently {tenant.status.value}. Please complete your subscription payment to restore access."
            )
        
        # Check if trial has expired and not paid
        if tenant.status == TenantStatus.trial and tenant.trial_ends_at:
            trial_ends_at = tenant.trial_ends_at
            if trial_ends_at.tzinfo is None:
                trial_ends_at = trial_ends_at.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            if trial_ends_at < now:
                from Services.trial_service import TrialService
                has_payment = await TrialService._has_payment_method(tenant.id)
                if not has_payment:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied. Your free trial period has expired. Please configure a payment method/subscribe to continue accessing features."
                    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify JWT token and return user payload from token
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        User payload from JWT token
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Get secret key from environment
        secret_key = os.getenv("SECRET_KEY", "dev-secret-key-12345")
        
        # Decode and verify JWT token
        payload = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=["HS256"]
        )
        
        # Check if token is access token
        token_type = payload.get("type")
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        # Validate tenant status (e.g. trial active status or payment configured)
        await validate_tenant_status(payload)
        
        # Return the payload directly (contains user_id, tenant_id, etc.)
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )


async def verify_tenant_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    Verify JWT token and check if user is tenant_admin
    
    Args:
        credentials: HTTP Bearer token credentials
        
    Returns:
        User payload from JWT token
        
    Raises:
        HTTPException: If token is invalid or user is not tenant_admin
    """
    try:
        # Get secret key from environment
        secret_key = os.getenv("SECRET_KEY", "dev-secret-key-12345")
        
        # Decode and verify JWT token
        payload = jwt.decode(
            credentials.credentials,
            secret_key,
            algorithms=["HS256"]
        )
        
        # Check if user is tenant_admin or platform_admin
        user_type = payload.get("user_type")
        if user_type not in ["tenant_admin", "platform_admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Tenant admin role required."
            )
        
        # Validate tenant status (e.g. trial active status or payment configured)
        await validate_tenant_status(payload)
        
        return payload
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )

def require_permissions(user_payload: dict, required_permissions: list) -> None:
    """
    Check if user has required permissions
    
    Args:
        user_payload: User payload from JWT token
        required_permissions: List of required permissions
        
    Raises:
        HTTPException: If user doesn't have required permissions
    """
    # For now, we'll implement a basic role-based check
    # In a full implementation, you'd check against a permissions system
    
    user_role = user_payload.get("role", "")
    user_type = user_payload.get("user_type", "")
    
    # Super admin has all permissions
    if user_type == "platform_admin":
        return
    
    # Tenant admin and admin have most permissions within their tenant
    if user_type in ["tenant_admin", "admin"]:
        return
    
    # Admin role (from role field) also has all permissions
    if user_role in ["admin", "tenant_admin", "super_admin"]:
        return
    
    # For other users, you can implement specific permission checks
    # This is a simplified version - expand based on your needs
    
    # Example: HR admin can manage employees and departments
    if user_role in ["hr_admin", "hr", "hr_manager"] and any(
        keyword in perm for perm in required_permissions 
        for keyword in ["employee", "department", "attendance", "leave", "job_title", "work_location", "job_history"]
    ):
        return
    
    # Example: Payroll admin can view employees and manage payroll
    if user_role in ["payroll_admin"] and any(
        keyword in perm for perm in required_permissions 
        for keyword in ["employee:read", "department:read", "payroll"]
    ):
        return
    
    # Sales or Manager roles can access CRM
    if user_role in ["sales", "sales_executive", "manager"] and any("crm" in perm for perm in required_permissions):
        return
    
    # Manager can read employee and department data
    if user_role in ["manager"] and all("read" in perm for perm in required_permissions):
        return
    
    # If no permissions match, deny access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Insufficient permissions. Required: {required_permissions}"
    )