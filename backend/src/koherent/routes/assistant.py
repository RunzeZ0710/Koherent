"""Grounded Q&A over a class's corpus: uploaded materials + lecture transcripts.

The RAG loop: embed the query (as "query" — asymmetric model), rank every
chunk in the class by cosine, assemble the top k into a numbered context
block, and generate with a system prompt that forbids answering beyond it.
Citations returned to the caller are the same numbered chunks the model saw.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Lecture, Material, MaterialChunk, Student, Transcript, TranscriptChunk
from koherent.pipeline.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    build_ask_prompt,
    build_context_block,
    build_explain_prompt,
)
from koherent.pipeline.retrieval import Candidate, top_k
from koherent.routes.access import require_class_member
from koherent.schemas import AskRequest, Citation, ExplainRequest, GeneratedAnswer

router = APIRouter(prefix="/classes", tags=["assistant"])

_TOP_K = 5


def gather_candidates(class_id: uuid.UUID, db: Session) -> list[Candidate]:
    """Every embedded chunk in the class: material chunks and transcript chunks."""
    candidates: list[Candidate] = []
    material_rows = db.execute(
        select(MaterialChunk, Material.filename)
        .join(Material, MaterialChunk.material_id == Material.id)
        .where(Material.class_id == class_id)
    ).all()
    for chunk, filename in material_rows:
        candidates.append(
            Candidate(
                source="material",
                ref_id=chunk.id,
                label=filename,
                content=chunk.content,
                vector=chunk.embedding,
            )
        )
    transcript_rows = db.execute(
        select(TranscriptChunk, Lecture.title)
        .join(Transcript, TranscriptChunk.transcript_id == Transcript.id)
        .join(Lecture, Transcript.lecture_id == Lecture.id)
        .where(Lecture.class_id == class_id)
    ).all()
    for chunk, title in transcript_rows:
        candidates.append(
            Candidate(
                source="transcript",
                ref_id=chunk.id,
                label=f"lecture:{title or 'untitled'}",
                content=chunk.content,
                vector=chunk.embedding,
            )
        )
    return candidates


def _generate_grounded(
    class_id: uuid.UUID,
    query_text: str,
    build_user_prompt,
    db: Session,
    ai: AIClient,
) -> GeneratedAnswer:
    candidates = gather_candidates(class_id, db)
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="Class has no indexed content yet (upload materials or process a lecture)",
        )
    query_vector = ai.embed_query(query_text)
    ranked = top_k(query_vector, candidates, k=_TOP_K)
    context_block, truncated = build_context_block(ranked, settings.context_char_budget)
    try:
        answer = ai.generate(GROUNDED_SYSTEM_PROMPT, build_user_prompt(context_block))
    except Exception:
        raise HTTPException(status_code=502, detail="LLM generation failed")
    return GeneratedAnswer(
        answer=answer,
        citations=[
            Citation(
                source=r.source, chunk_id=r.ref_id, label=r.label, content=r.content, score=r.score
            )
            for r in ranked
        ],
        truncated=truncated,
        model=settings.nim_chat_model,
    )


@router.post("/{class_id}/ask", response_model=GeneratedAnswer)
def ask(
    class_id: uuid.UUID,
    payload: AskRequest,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> GeneratedAnswer:
    require_class_member(class_id, current)
    return _generate_grounded(
        class_id,
        payload.question,
        lambda block: build_ask_prompt(payload.question, block),
        db,
        ai,
    )


@router.post("/{class_id}/explain", response_model=GeneratedAnswer)
def explain(
    class_id: uuid.UUID,
    payload: ExplainRequest,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> GeneratedAnswer:
    require_class_member(class_id, current)
    return _generate_grounded(
        class_id,
        payload.concept,
        lambda block: build_explain_prompt(payload.concept, block),
        db,
        ai,
    )
