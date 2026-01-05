"""
Authentication utilities - JWT tokens, password hashing, etc.
"""

import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token security
security = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    """JWT token payload."""
    user_id: int
    email: str
    role: str
    exp: datetime


class Token(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(
    user_id: int,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "exp": expire,
    }
    
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[TokenData]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
        email = payload.get("email")
        role = payload.get("role", "user")
        exp = datetime.fromtimestamp(payload.get("exp"))
        
        if user_id is None or email is None:
            return None
        
        return TokenData(user_id=user_id, email=email, role=role, exp=exp)
    except JWTError:
        return None


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
):
    """
    Dependency to get the current authenticated user.
    Returns None if not authenticated (for optional auth).
    """
    if credentials is None:
        return None
    
    token_data = decode_token(credentials.credentials)
    if token_data is None:
        return None
    
    # Import here to avoid circular imports
    from biolinker.storage.database import DatabaseManager
    from biolinker.auth.models import UserModel
    
    db = DatabaseManager()
    with db.get_session() as session:
        user = session.query(UserModel).filter_by(id=token_data.user_id).first()
        if user is None or not user.is_active:
            return None
        return user.to_dict()


async def require_auth(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
):
    """
    Dependency that requires authentication.
    Raises 401 if not authenticated.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = decode_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    from biolinker.storage.database import DatabaseManager
    from biolinker.auth.models import UserModel
    
    db = DatabaseManager()
    with db.get_session() as session:
        user = session.query(UserModel).filter_by(id=token_data.user_id).first()
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )
        return user.to_dict()


def require_role(allowed_roles: list[str]):
    """
    Dependency factory that requires specific roles.
    """
    async def role_checker(user: dict = Depends(require_auth)):
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user
    return role_checker


def generate_api_key() -> str:
    """Generate a secure API key."""
    return f"bl_{secrets.token_urlsafe(32)}"

