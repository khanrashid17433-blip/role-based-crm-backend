from beanie import Document
from pydantic import Field, EmailStr
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4
from Models.enums import TokenType


class EmailVerificationToken(Document):
    """Email Verification Token model"""
    
    # ID and timestamps
    id: UUID = Field(default_factory=uuid4, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Foreign Keys (stored as UUIDs in MongoDB)
    registration_id: Optional[UUID] = None  # Required for email verification, optional for password reset
    user_id: Optional[UUID] = None  # Null pre-verification
    
    # Token Information
    token_type: TokenType = Field(default=TokenType.email_verification)
    token_hash: str = Field(..., max_length=64)  # SHA-256 hash
    email: EmailStr  # Denormalized for quick lookup
    
    # Token Lifecycle
    expires_at: datetime
    used_at: Optional[datetime] = None
    
    # Metadata
    ip_address: Optional[str] = None  # Store as string instead of INET
    
    class Settings:
        name = "email_verification_tokens"
        indexes = [
            "registration_id",
            "user_id",
            "token_hash",
            "email",
        ]
    
    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }
    
    def __repr__(self):
        return f"<EmailVerificationToken {self.email} - {self.token_type.value}>"
