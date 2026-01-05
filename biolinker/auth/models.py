"""
User authentication models.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
import enum

from biolinker.storage.models import Base


class UserRole(str, enum.Enum):
    """User roles for access control."""
    USER = "user"
    PRO = "pro"
    TEAM = "team"
    ADMIN = "admin"


class UserModel(Base):
    """User account model."""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Profile
    full_name = Column(String(255))
    organization = Column(String(255))
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    role = Column(String(20), default=UserRole.USER.value)
    
    # Usage tracking
    articles_processed = Column(Integer, default=0)
    searches_this_month = Column(Integer, default=0)
    last_search_reset = Column(DateTime, default=datetime.utcnow)
    
    # API access
    api_key = Column(String(64), unique=True, nullable=True)
    api_calls_this_month = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "organization": self.organization,
            "role": self.role,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WaitlistModel(Base):
    """Waitlist signups for landing page."""
    __tablename__ = "waitlist"
    
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255))
    organization = Column(String(255))
    use_case = Column(Text)
    
    # Status
    is_invited = Column(Boolean, default=False)
    invited_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "organization": self.organization,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

