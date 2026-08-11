"""Request and response models for authentication.

`password_hash` appears nowhere in this module, and must never be added to it.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    """The refresh token is absent on purpose - it goes back as an httpOnly cookie."""

    access_token: str
    token_type: str = "bearer"  # noqa: S105 - a scheme name, not a credential
    expires_in_s: int
    user: CurrentUserResponse


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in_s: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class SessionResponse(BaseModel):
    """One logged-in device, so a user can recognise and revoke their own."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    issued_at: dt.datetime
    expires_at: dt.datetime
    last_used_at: dt.datetime | None
    user_agent: str
    client_ip: str
