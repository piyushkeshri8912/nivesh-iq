from pydantic import BaseModel, Field
from typing import Optional
from app.schemas.profile import UserProfileResponse

class UserBase(BaseModel):
    email: str = Field(..., description="User Email")

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: str
    is_active: bool
    profile: Optional[UserProfileResponse] = None

    class Config:
        from_attributes = True
