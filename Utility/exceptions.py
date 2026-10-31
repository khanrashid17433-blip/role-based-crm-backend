class RegistrationError(Exception):
    """Base exception for registration errors"""
    pass


class ValidationError(Exception):
    """Raised when validation fails"""
    pass


class NotFoundError(Exception):
    """Raised when a resource is not found"""
    pass


class ConflictError(Exception):
    """Raised when there's a conflict (e.g., duplicate resource)"""
    pass


class EmailAlreadyExistsError(RegistrationError):
    """Raised when email already exists"""
    pass


class DisposableEmailError(RegistrationError):
    """Raised when disposable email is detected"""
    pass


class InvalidPromoCodeError(RegistrationError):
    """Raised when promo code is invalid"""
    pass


class TokenExpiredError(RegistrationError):
    """Raised when verification token has expired"""
    pass


class InvalidTokenError(RegistrationError):
    """Raised when verification token is invalid"""
    pass


class MaxVerificationAttemptsError(RegistrationError):
    """Raised when max verification attempts exceeded"""
    pass


class RateLimitExceededError(RegistrationError):
    """Raised when rate limit is exceeded"""
    pass


class TermsNotAcceptedError(RegistrationError):
    """Raised when terms are not accepted"""
    pass
