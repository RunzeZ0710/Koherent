import secrets

from koherent.models import (
    Class,
    Lecture,
    Note,
    NoteAlignment,
    Student,
    Transcript,
    TranscriptChunk,
)


def _seed_note(db) -> Note:
    klass = Class(name="Econ 101", join_code="ABC123", owner_token=secrets.token_urlsafe(32))
    db.add(klass)
    db.flush()
    student = Student(class_id=klass.id, display_name="Alice", session_token=secrets.token_urlsafe(32))
    lecture = Lecture(class_id=klass.id, title="Day 1")
    db.add_all([student, lecture])
    db.flush()
    note = Note(
        lecture_id=lecture.id, student_id=student.id, content="MR=MC", client_timestamp_ms=10
    )
    db.add(note)
    db.flush()
    return note


def test_transcript_chunk_and_alignment_persist(db):
    note = _seed_note(db)

    transcript = Transcript(lecture_id=note.lecture_id, full_text="full lecture text")
    db.add(transcript)
    db.flush()

    chunk = TranscriptChunk(
        transcript_id=transcript.id,
        chunk_index=0,
        content="marginal revenue equals marginal cost",
        start_ms=0,
        end_ms=30000,
        embedding=[0.1, 0.2, 0.3],
    )
    db.add(chunk)
    db.flush()

    note.embedding = [0.1, 0.2, 0.3]
    alignment = NoteAlignment(
        note_id=note.id, transcript_chunk_id=chunk.id, similarity=0.97
    )
    db.add(alignment)
    db.flush()

    refetched = db.get(NoteAlignment, alignment.id)
    assert refetched.similarity == 0.97
    assert refetched.chunk.content == "marginal revenue equals marginal cost"
    assert refetched.note.embedding == [0.1, 0.2, 0.3]


def test_deleting_transcript_cascades_to_chunks_and_alignments(db):
    note = _seed_note(db)
    transcript = Transcript(lecture_id=note.lecture_id, full_text="x")
    db.add(transcript)
    db.flush()
    chunk = TranscriptChunk(
        transcript_id=transcript.id, chunk_index=0, content="c", start_ms=0, end_ms=1, embedding=[1.0]
    )
    db.add(chunk)
    db.flush()
    db.add(NoteAlignment(note_id=note.id, transcript_chunk_id=chunk.id, similarity=0.5))
    db.flush()

    db.delete(transcript)
    db.flush()

    from sqlalchemy import func, select

    assert db.scalar(select(func.count(TranscriptChunk.id))) == 0
    assert db.scalar(select(func.count(NoteAlignment.id))) == 0
