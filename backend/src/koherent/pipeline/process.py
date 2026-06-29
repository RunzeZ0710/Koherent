"""Orchestrator: run the four pipeline stages for one lecture and persist results.

Idempotent: a re-run clears this lecture's derived rows (transcript -> cascades
chunks; alignments) and rebuilds them, so processing twice yields the same state.
Holds no clever logic of its own — chunking and alignment live in their own
modules; transcription and embedding live behind the AIClient seam.
"""

import os
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.models import (
    AudioRecording,
    Lecture,
    Note,
    NoteAlignment,
    Transcript,
    TranscriptChunk,
)
from koherent.pipeline.alignment import align
from koherent.pipeline.chunking import chunk_transcript


@dataclass(frozen=True)
class ProcessSummary:
    transcript_id: uuid.UUID
    chunk_count: int
    note_count: int
    alignment_count: int


class NoAudioError(Exception):
    """Raised when a lecture has no audio recording to process."""


def process_lecture(lecture_id: uuid.UUID, db: Session, ai: AIClient) -> ProcessSummary:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise LookupError("lecture not found")

    recording = db.scalar(
        select(AudioRecording)
        .where(AudioRecording.lecture_id == lecture_id)
        .order_by(AudioRecording.created_at)
    )
    if recording is None:
        raise NoAudioError()

    notes = list(db.scalars(select(Note).where(Note.lecture_id == lecture_id)))

    # --- idempotency: clear derived rows in FK-safe order ---
    note_ids = [n.id for n in notes]
    if note_ids:
        db.execute(delete(NoteAlignment).where(NoteAlignment.note_id.in_(note_ids)))
    existing = db.scalar(select(Transcript).where(Transcript.lecture_id == lecture_id))
    if existing is not None:
        db.delete(existing)  # cascades to its chunks
    for note in notes:
        note.embedding = None
    db.flush()

    # --- stage 1: transcribe ---
    audio_path = os.path.join(settings.audio_storage_dir, recording.file_path)
    transcription = ai.transcribe(audio_path)
    transcript = Transcript(lecture_id=lecture_id, full_text=transcription.text)
    db.add(transcript)
    db.flush()

    # --- stage 2: chunk ---
    chunks = chunk_transcript(transcription.words)

    # --- stage 3: embed chunks + notes ---
    chunk_vectors = ai.embed([c.content for c in chunks]) if chunks else []
    chunk_rows: list[TranscriptChunk] = []
    for chunk, vector in zip(chunks, chunk_vectors):
        row = TranscriptChunk(
            transcript_id=transcript.id,
            chunk_index=chunk.index,
            content=chunk.content,
            start_ms=chunk.start_ms,
            end_ms=chunk.end_ms,
            embedding=vector,
        )
        db.add(row)
        chunk_rows.append(row)
    db.flush()

    note_vectors = ai.embed([n.content for n in notes]) if notes else []
    for note, vector in zip(notes, note_vectors):
        note.embedding = vector
    db.flush()

    # --- stage 4: align ---
    alignments = align(note_vectors, [row.embedding for row in chunk_rows])
    for result in alignments:
        db.add(
            NoteAlignment(
                note_id=notes[result.note_index].id,
                transcript_chunk_id=chunk_rows[result.chunk_index].id,
                similarity=result.similarity,
            )
        )

    db.commit()
    return ProcessSummary(
        transcript_id=transcript.id,
        chunk_count=len(chunk_rows),
        note_count=len(notes),
        alignment_count=len(alignments),
    )
