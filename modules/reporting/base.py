"""Structured report records shared by reporting helpers."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from modules.core.time_utils import utc_now


class ReportArtifact(BaseModel):
    """A report body with optional categorization tags."""

    title: str
    body: str
    created_at: datetime = Field(default_factory=utc_now)
    tags: list[str] = Field(default_factory=list)
