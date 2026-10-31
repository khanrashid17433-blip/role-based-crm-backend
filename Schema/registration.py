from pydantic import BaseModel, Field, validator, EmailStr
from typing import Optional, Dict
from enum import Enum
import re


class CompanySizeEnum(str, Enum):
    """Company size options - accepts both frontend (hyphen) and backend (underscore) formats"""
    size_1_10 = "1_10"
    size_1_10_alt = "1-10"  # Frontend format
    size_11_50 = "11_50"
    size_11_50_alt = "11-50"  # Frontend format
    size_51_200 = "51_200"
    size_51_200_alt = "51-200"  # Frontend format
    size_201_500 = "201_500"
    size_201_500_alt = "201-500"  # Frontend format
    size_501_1000 = "501_1000"
    size_501_1000_alt = "501-1000"  # Frontend format
    size_1000_plus = "1000_plus"
    size_1000_plus_alt = "1000+"  # Frontend format
    
    class Config:
        use_enum_values = True


class PrimaryRegionEnum(str, Enum):
    """Primary region options"""
    US = "US"
    UK = "UK"
    IN = "IN"
    
    class Config:
        use_enum_values = True


class BillingCycleEnum(str, Enum):
    """Billing cycle options"""
    monthly = "monthly"
    annual = "annual"
    
    class Config:
        use_enum_values = True


class UTMParameters(BaseModel):
    """UTM tracking parameters"""
    utm_source: Optional[str] = Field(None, max_length=100)
    utm_medium: Optional[str] = Field(None, max_length=100)
    utm_campaign: Optional[str] = Field(None, max_length=100)
    utm_content: Optional[str] = Field(None, max_length=100)
    utm_term: Optional[str] = Field(None, max_length=100)
    gclid: Optional[str] = Field(None, max_length=200)
    fbclid: Optional[str] = Field(None, max_length=200)


class Step1RegistrationRequest(BaseModel):
    """Step 1: Account Details only (creates lead)"""
    
    first_name: str = Field(..., min_length=2, max_length=50, description="First name")
    last_name: str = Field(..., min_length=2, max_length=50, description="Last name")
    email: EmailStr = Field(..., description="Work email address")
    phone_country_code: Optional[str] = Field(None, description="Country code (e.g., +91, +1)")
    phone_number: Optional[str] = Field(None, description="Phone number without country code")
    phone: Optional[str] = Field(None, description="Full phone number in E.164 format (auto-generated)")
    password: str = Field(..., min_length=12, description="Password")
    terms_accepted: bool = Field(..., description="Terms and conditions accepted")
    
    @validator('first_name', 'last_name')
    def name_no_numbers(cls, v):
        """Validate names don't contain numbers"""
        if re.search(r'\d', v):
            raise ValueError('Name cannot contain numbers')
        return v.strip()
    
    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password meets strength requirements"""
        if len(v) < 12:
            raise ValueError('Password must be at least 12 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @validator('email')
    def validate_work_email(cls, v):
        """Validate it's not a disposable email or +alias"""
        v = v.lower()
        if '+' in v:
            raise ValueError('Email aliases with + are not allowed')
        
        disposable_domains = [
            'mailinator.com', 'guerrillamail.com', 'tempmail.com',
            'throwaway.email', 'yopmail.com'
        ]
        domain = v.split('@')[1]
        if domain in disposable_domains:
            raise ValueError('Disposable email addresses are not allowed')
        
        return v
    
    @validator('terms_accepted')
    def validate_terms_accepted(cls, v):
        """Validate terms are accepted"""
        if not v:
            raise ValueError('You must accept the terms and conditions')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@company.com",
                "phone_country_code": "+1",
                "phone_number": "5551234567",
                "password": "SecurePass123!",
                "terms_accepted": True
            }
        }
        use_enum_values = True


class RegistrationRequest(BaseModel):
    """Complete registration request schema (legacy - both steps at once)"""
    
    # Step 1: Account Details
    first_name: str = Field(..., min_length=2, max_length=50, description="First name")
    last_name: str = Field(..., min_length=2, max_length=50, description="Last name")
    email: EmailStr = Field(..., description="Work email address")
    phone_country_code: Optional[str] = Field(None, description="Country code (e.g., +91, +1)")
    phone_number: Optional[str] = Field(None, description="Phone number without country code")
    phone: Optional[str] = Field(None, description="Full phone number in E.164 format (auto-generated)")
    password: str = Field(..., min_length=12, description="Password")
    
    # Step 2: Company Details
    company_name: str = Field(..., min_length=2, max_length=100, description="Company name")
    company_size: CompanySizeEnum = Field(..., description="Company size")
    industry: Optional[str] = Field(None, max_length=100, description="Industry")
    primary_region: PrimaryRegionEnum = Field(..., description="Primary region")
    plan_slug: str = Field(..., min_length=1, max_length=50, description="Selected plan slug")
    billing_cycle: BillingCycleEnum = Field(..., description="Billing cycle")
    promo_code: Optional[str] = Field(None, max_length=50, description="Promotional code")
    
    # Legal & Compliance
    terms_accepted: bool = Field(..., description="Terms and conditions accepted")
    
    @validator('first_name', 'last_name')
    def name_no_numbers(cls, v):
        """Validate names don't contain numbers"""
        if re.search(r'\d', v):
            raise ValueError('Name cannot contain numbers')
        return v.strip()
    
    @validator('company_size')
    def normalize_company_size(cls, v):
        """Convert frontend format (hyphens) to backend format (underscores)"""
        # Mapping from frontend format to backend format
        size_mapping = {
            "1-10": "1_10",
            "11-50": "11_50",
            "51-200": "51_200",
            "201-500": "201_500",
            "501-1000": "501_1000",
            "1000+": "1000_plus"
        }
        # Convert if it's in frontend format
        return size_mapping.get(v, v)
    
    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password meets strength requirements"""
        if len(v) < 12:
            raise ValueError('Password must be at least 12 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @validator('phone')
    def combine_phone_number(cls, v, values):
        """Combine country code and phone number into E.164 format"""
        # If phone is already provided in E.164 format, use it
        if v and re.match(r'^\+[1-9]\d{1,14}$', v):
            return v
        
        # Otherwise, combine country code and phone number
        country_code = values.get('phone_country_code')
        phone_number = values.get('phone_number')
        
        # If both are provided, combine them
        if country_code and phone_number:
            # Remove any leading + from country code
            country_code = country_code.lstrip('+')
            # Remove any non-digit characters from phone number
            phone_number = re.sub(r'\D', '', phone_number)
            
            # Combine into E.164 format
            full_phone = f"+{country_code}{phone_number}"
            
            # Validate the combined number
            if not re.match(r'^\+[1-9]\d{1,14}$', full_phone):
                raise ValueError('Phone number must be in E.164 format (e.g., +917895172367)')
            
            return full_phone
        
        # If only one is provided, raise error
        if country_code or phone_number:
            raise ValueError('Both country code and phone number are required')
        
        # If neither is provided, phone is optional (None)
        return v
    
    @validator('email')
    def validate_work_email(cls, v):
        """Validate it's not a disposable email or +alias"""
        v = v.lower()
        if '+' in v:
            raise ValueError('Email aliases with + are not allowed')
        
        # Common disposable email domains blocklist
        disposable_domains = [
            'mailinator.com', 'guerrillamail.com', 'tempmail.com',
            'throwaway.email', 'yopmail.com'
        ]
        domain = v.split('@')[1]
        if domain in disposable_domains:
            raise ValueError('Disposable email addresses are not allowed')
        
        return v
    
    @validator('terms_accepted')
    def validate_terms_accepted(cls, v):
        """Validate terms are accepted"""
        if not v:
            raise ValueError('You must accept the terms and conditions')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john.doe@company.com",
                "phone": "+14155552671",
                "password": "StrongP@ssw0rd123!",
                "company_name": "Acme Corporation",
                "company_size": "51_200",
                "industry": "Technology",
                "primary_region": "US",
                "plan_slug": "growth",
                "billing_cycle": "annual",
                "promo_code": "SAVE20",
                "terms_accepted": True
            }
        }


class RegistrationResponse(BaseModel):
    """Registration success response"""
    message: str
    registration_id: str
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Verification email sent. Please check your inbox.",
                "registration_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class EmailVerificationRequest(BaseModel):
    """Email verification request"""
    token: str = Field(..., min_length=1, description="Verification token from email")
    
    class Config:
        schema_extra = {
            "example": {
                "token": "abc123def456..."
            }
        }


class ResendVerificationRequest(BaseModel):
    """Resend verification email request"""
    email: EmailStr = Field(..., description="Email address to resend verification to")
    
    class Config:
        schema_extra = {
            "example": {
                "email": "john.doe@company.com"
            }
        }
