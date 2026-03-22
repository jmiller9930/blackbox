"""Structured plan records shared by planning helpers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from modules.core.time_utils import utc_now


class PlanArtifact(BaseModel):
    """A plan document fragment suitable for review and iteration."""

    title: str
    summary: str
    steps: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
