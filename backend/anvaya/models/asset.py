"""Asset and relationship models for BlastScope."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel

from anvaya.models.enums import AssetType


class Asset(SQLModel, table=True):
    __tablename__ = "assets"

    id: Optional[int] = Field(default=None, primary_key=True)
    asset_id: str = Field(unique=True, index=True, max_length=64)
    name: str = Field(max_length=128)
    asset_type: AssetType = Field(default=AssetType.HOST, index=True)
    is_critical: bool = False
    is_compromised: bool = False
    is_neutralized: bool = False
    tenant_id: str = Field(default="default", max_length=64)

    ip_address: str = Field(default="", max_length=64)
    hostname: str = Field(default="", max_length=128)
    department: str = Field(default="", max_length=128)

    metadata_json: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssetRelationship(SQLModel, table=True):
    __tablename__ = "asset_relationships"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_asset_id: str = Field(index=True, max_length=64)
    target_asset_id: str = Field(index=True, max_length=64)
    relationship_type: str = Field(max_length=64)
    is_observed: bool = False
    is_simulated: bool = False
    weight: float = 1.0
    metadata_json: str = ""
