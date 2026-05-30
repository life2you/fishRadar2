"""
Authentication and tenant domain models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


AppRole = Literal["admin", "tenant"]
UserStatus = Literal["active", "disabled"]
TenantStatus = Literal["active", "disabled"]
ActivationCodeStatus = Literal["unused", "redeemed", "disabled"]


class Tenant(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    slug: str
    status: TenantStatus = "active"
    ai_enabled: bool = False
    activation_required: bool = True
    activated_at: Optional[str] = None
    access_expires_at: Optional[str] = None
    created_at: str


class User(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    username: str
    password_hash: str
    role: AppRole
    status: UserStatus = "active"
    display_name: Optional[str] = None
    created_at: str


class ActivationCode(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    code: str
    status: ActivationCodeStatus = "unused"
    duration_minutes: int
    note: Optional[str] = None
    created_by_user_id: Optional[int] = None
    redeemed_by_tenant_id: Optional[int] = None
    redeemed_by_user_id: Optional[int] = None
    redeemed_at: Optional[str] = None
    created_at: str


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(extra="ignore")

    user_id: int
    username: str
    role: AppRole
    display_name: Optional[str] = None
    tenant_id: Optional[int] = None
    tenant_name: Optional[str] = None
    tenant_status: Optional[TenantStatus] = None
    tenant_ai_enabled: bool = False
    tenant_activation_required: bool = False
    tenant_activated_at: Optional[str] = None
    tenant_access_expires_at: Optional[str] = None
    session_token: Optional[str] = None

    @staticmethod
    def _parse_iso(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @property
    def activated(self) -> bool:
        if self.role != "tenant":
            return True
        return (not self.tenant_activation_required) or bool(self.tenant_activated_at)

    @property
    def access_expired(self) -> bool:
        if self.role != "tenant":
            return False
        expires_at = self._parse_iso(self.tenant_access_expires_at)
        if expires_at is None:
            return False
        return expires_at <= datetime.now()

    @property
    def workspace_enabled(self) -> bool:
        if self.role != "tenant":
            return True
        if self.tenant_status != "active":
            return False
        return self.activated and not self.access_expired

    @property
    def can_use_ai(self) -> bool:
        if self.role == "admin":
            return True
        return self.workspace_enabled and self.tenant_ai_enabled

    @property
    def allowed_routes(self) -> list[str]:
        if self.role == "admin":
            return [
                "dashboard",
                "tasks",
                "accounts",
                "results",
                "logs",
                "settings",
            ]
        if not self.workspace_enabled:
            return [
                "activate",
            ]
        return [
            "tasks",
            "results",
            "notifications",
        ]
