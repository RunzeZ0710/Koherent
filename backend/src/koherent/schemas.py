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


class JoinRequest(BaseModel):
    join_code: str = Field(min_length=1, max_length=16)
    display_name: str = Field(min_length=1, max_length=100)


class StudentSession(BaseModel):
    student_id: uuid.UUID
    class_id: uuid.UUID
    display_name: str
    session_token: str
