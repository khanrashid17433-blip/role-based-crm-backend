import enum


class CompanySize(enum.Enum):
    """Company size enumeration"""
    size_1_10 = "1_10"
    size_11_50 = "11_50"
    size_51_200 = "51_200"
    size_201_500 = "201_500"
    size_501_1000 = "501_1000"
    size_1000_plus = "1000_plus"


class PrimaryRegion(enum.Enum):
    """Primary region enumeration"""
    US = "US"
    UK = "UK"
    IN = "IN"


class BillingCycle(enum.Enum):
    """Billing cycle enumeration"""
    monthly = "monthly"
    annual = "annual"


class RegistrationStatus(enum.Enum):
    """Registration status enumeration"""
    pending_verification = "pending_verification"
    verified = "verified"
    abandoned = "abandoned"
    spam_blocked = "spam_blocked"


class TokenType(enum.Enum):
    """Token type enumeration"""
    email_verification = "email_verification"
    password_reset = "password_reset"
    email_change = "email_change"
    invite = "invite"


class EntityType(enum.Enum):
    """Entity type enumeration"""
    limited_company = "limited_company"
    llc = "llc"
    sole_trader = "sole_trader"
    plc = "plc"
    partnership = "partnership"
    llp = "llp"


class UserRole(enum.Enum):
    """User role enumeration for invitations"""
    hr_admin = "hr_admin"
    payroll_admin = "payroll_admin"
    recruiter = "recruiter"
    finance_viewer = "finance_viewer"
    it_admin = "it_admin"


class InvitationStatus(enum.Enum):
    """Invitation status enumeration"""
    pending = "pending"
    accepted = "accepted"
    expired = "expired"
    revoked = "revoked"
