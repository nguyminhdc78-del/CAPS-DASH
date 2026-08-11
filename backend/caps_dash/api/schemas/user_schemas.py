"""Request and response models for user administration."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from ...db.enums import UserRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    last_login_at: dt.datetime | None
    created_at: dt.datetime


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=10, max_length=256)
    display_name: str = Field(default="", max_length=120)
    role: UserRole = UserRole.RESIDENT


class UpdateUserRequest(BaseModel):
    """Every field optional: this is a partial update, not a replacement."""

    display_name: str | None = Field(default=None, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=10, max_length=256)
