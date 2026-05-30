from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


class AIAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[int] = None
    name: str
    api_key: Optional[str] = None
    base_url: str
    model_name: str
    supports_image: bool = True
    supports_text: bool = True
    enabled: bool = True
    priority: int = 100
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_test_status: Optional[str] = None
    last_test_message: Optional[str] = None
    last_tested_at: Optional[str] = None


class AIAccountCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    api_key: Optional[str] = None
    base_url: str
    model_name: str
    supports_image: bool = True
    supports_text: bool = True
    enabled: bool = True
    priority: int = 100
    notes: Optional[str] = None


class AIAccountUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None
    supports_image: Optional[bool] = None
    supports_text: Optional[bool] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    notes: Optional[str] = None


class AIRouteCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str
    account: AIAccount
