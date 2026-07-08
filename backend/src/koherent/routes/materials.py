"""Course-material ingestion: upload a document, extract, chunk, embed, store.

Processing is synchronous and inline (same decision as lecture processing,
wiki D-028): a class's documents are small and the corpus is bounded, so a
queue would be premature.
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Material, MaterialChunk, Student
from koherent.pipeline.extraction import (
    EmptyDocumentError,
    UnsupportedDocumentError,
    extract_text,
)
from koherent.pipeline.text_chunking import chunk_text
from koherent.routes.access import require_class_member
from koherent.schemas import MaterialList, MaterialRead

router = APIRouter(prefix="/classes", tags=["materials"])


def _to_read(material: Material) -> MaterialRead:
    return MaterialRead(
        id=material.id,
        class_id=material.class_id,
        filename=material.filename,
        media_type=material.media_type,
        size_bytes=material.size_bytes,
        chunk_count=len(material.chunks),
        created_at=material.created_at,
    )


@router.post(
    "/{class_id}/materials", response_model=MaterialRead, status_code=status.HTTP_201_CREATED
)
def upload_material(
    class_id: uuid.UUID,
    file: UploadFile = File(...),
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> MaterialRead:
    require_class_member(class_id, current)

    data = file.file.read()
    filename = file.filename or "upload"
    try:
        text = extract_text(data, filename)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except EmptyDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    chunks = chunk_text(text)
    vectors = ai.embed([c.content for c in chunks])

    material = Material(
        class_id=class_id,
        filename=filename,
        media_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        extracted_chars=len(text),
    )
    material.chunks = [
        MaterialChunk(chunk_index=c.index, content=c.content, embedding=v)
        for c, v in zip(chunks, vectors)
    ]
    db.add(material)
    db.commit()
    db.refresh(material)
    return _to_read(material)


@router.get("/{class_id}/materials", response_model=MaterialList)
def list_materials(
    class_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> MaterialList:
    require_class_member(class_id, current)
    materials = list(
        db.scalars(
            select(Material).where(Material.class_id == class_id).order_by(Material.created_at)
        )
    )
    return MaterialList(items=[_to_read(m) for m in materials])
