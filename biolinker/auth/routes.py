"""
Authentication API routes.
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field

from biolinker.auth.utils import (
    get_password_hash,
    verify_password,
    create_access_token,
    require_auth,
    generate_api_key,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    Token,
)
from biolinker.auth.models import UserModel, WaitlistModel
from biolinker.storage.database import DatabaseManager

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ==================== Request/Response Models ====================

class RegisterRequest(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    organization: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User profile response."""
    id: int
    email: str
    full_name: Optional[str]
    organization: Optional[str]
    role: str
    is_verified: bool
    created_at: str


class UpdateProfileRequest(BaseModel):
    """Update user profile."""
    full_name: Optional[str] = None
    organization: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    current_password: str
    new_password: str = Field(..., min_length=8)


class WaitlistRequest(BaseModel):
    """Waitlist signup request."""
    email: EmailStr
    name: Optional[str] = None
    organization: Optional[str] = None
    use_case: Optional[str] = None


# ==================== Auth Routes ====================

@router.post("/register", response_model=Token)
async def register(request: RegisterRequest):
    """
    Register a new user account.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        # Check if email already exists
        existing = session.query(UserModel).filter_by(email=request.email.lower()).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create user
        user = UserModel(
            email=request.email.lower(),
            hashed_password=get_password_hash(request.password),
            full_name=request.full_name,
            organization=request.organization,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        
        # Generate token
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
        )
        
        return Token(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """
    Login with email and password.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        user = session.query(UserModel).filter_by(email=request.email.lower()).first()
        
        if not user or not verify_password(request.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )
        
        # Update last login
        user.last_login = datetime.utcnow()
        session.commit()
        
        # Generate token
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role,
        )
        
        return Token(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


@router.get("/me", response_model=UserResponse)
async def get_me(user: dict = Depends(require_auth)):
    """
    Get current user profile.
    """
    return UserResponse(
        id=user["id"],
        email=user["email"],
        full_name=user.get("full_name"),
        organization=user.get("organization"),
        role=user["role"],
        is_verified=user.get("is_verified", False),
        created_at=user.get("created_at", ""),
    )


@router.put("/me", response_model=UserResponse)
async def update_profile(request: UpdateProfileRequest, user: dict = Depends(require_auth)):
    """
    Update current user profile.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        db_user = session.query(UserModel).filter_by(id=user["id"]).first()
        
        if request.full_name is not None:
            db_user.full_name = request.full_name
        if request.organization is not None:
            db_user.organization = request.organization
        
        session.commit()
        session.refresh(db_user)
        
        return UserResponse(
            id=db_user.id,
            email=db_user.email,
            full_name=db_user.full_name,
            organization=db_user.organization,
            role=db_user.role,
            is_verified=db_user.is_verified,
            created_at=db_user.created_at.isoformat() if db_user.created_at else "",
        )


@router.post("/change-password")
async def change_password(request: ChangePasswordRequest, user: dict = Depends(require_auth)):
    """
    Change user password.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        db_user = session.query(UserModel).filter_by(id=user["id"]).first()
        
        if not verify_password(request.current_password, db_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
        
        db_user.hashed_password = get_password_hash(request.new_password)
        session.commit()
        
        return {"message": "Password changed successfully"}


@router.post("/api-key")
async def generate_user_api_key(user: dict = Depends(require_auth)):
    """
    Generate or regenerate API key for the user.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        db_user = session.query(UserModel).filter_by(id=user["id"]).first()
        db_user.api_key = generate_api_key()
        session.commit()
        
        return {"api_key": db_user.api_key}


# ==================== Waitlist Routes ====================

@router.post("/waitlist")
async def join_waitlist(request: WaitlistRequest):
    """
    Join the waitlist for early access.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        # Check if already on waitlist
        existing = session.query(WaitlistModel).filter_by(email=request.email.lower()).first()
        if existing:
            return {"message": "You're already on the waitlist!", "position": existing.id}
        
        # Add to waitlist
        entry = WaitlistModel(
            email=request.email.lower(),
            name=request.name,
            organization=request.organization,
            use_case=request.use_case,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        
        # Get position
        position = session.query(WaitlistModel).count()
        
        return {
            "message": "You've been added to the waitlist!",
            "position": position,
        }


@router.get("/waitlist/count")
async def get_waitlist_count():
    """
    Get the current waitlist count.
    """
    db = DatabaseManager()
    
    with db.get_session() as session:
        count = session.query(WaitlistModel).count()
        return {"count": count}

