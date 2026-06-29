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


class LectureCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class LectureRead(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    title: str | None
    started_at: datetime
    ended_at: datetime | None


class NoteCreate(BaseModel):
    content: str = Field(min_length=1)
    client_timestamp_ms: int = Field(ge=0)


class NoteRead(BaseModel):
    id: uuid.UUID
    lecture_id: uuid.UUID
    student_id: uuid.UUID
    content: str
    client_timestamp_ms: int
    created_at: datetime


class AudioRecordingRead(BaseModel):
    id: uuid.UUID
    lecture_id: uuid.UUID
    uploaded_by_student_id: uuid.UUID | None
    file_path: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class LectureStatus(LectureRead):
    my_notes_count: int
    has_audio: bool


class ProcessResult(BaseModel):
    transcript_id: uuid.UUID
    chunk_count: int
    note_count: int
    alignment_count: int


class NoteReportItem(BaseModel):
    note_id: uuid.UUID
    student_id: uuid.UUID
    note_content: str
    client_timestamp_ms: int
    matched_chunk_index: int | None
    matched_content: str | None
    matched_start_ms: int | None
    matched_end_ms: int | None
    similarity: float | None
    anomaly: bool


class LectureReport(BaseModel):
    lecture_id: uuid.UUID
    threshold: float
    items: list[NoteReportItem]
