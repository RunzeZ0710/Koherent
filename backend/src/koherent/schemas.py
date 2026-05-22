from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ClassRead(BaseModel):
    id: uuid.UUID
    name: str
    join_code: str
    created_at: datetime


class ClassCreated(ClassRead):
    owner_token: str
