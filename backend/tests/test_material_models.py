from koherent.models import (
    Class,
    Lecture,
    LectureSummary,
    Material,
    MaterialChunk,
)


def _make_class(db) -> Class:
    klass = Class(name="Econ 101", join_code="ABC123", owner_token="tok-" + "x" * 8)
    db.add(klass)
    db.commit()
    return klass


def test_material_with_chunks_persists(db):
    klass = _make_class(db)
    material = Material(
        class_id=klass.id,
        filename="econ_notes.md",
        media_type="text/markdown",
        size_bytes=1234,
        extracted_chars=1000,
    )
    material.chunks = [
        MaterialChunk(chunk_index=0, content="supply and demand", embedding=[0.1, 0.2]),
        MaterialChunk(chunk_index=1, content="elasticity", embedding=[0.3, 0.4]),
    ]
    db.add(material)
    db.commit()
    db.refresh(material)
    assert len(material.chunks) == 2
    assert material.chunks[0].embedding == [0.1, 0.2]


def test_deleting_class_cascades_to_materials_and_chunks(db):
    klass = _make_class(db)
    material = Material(
        class_id=klass.id,
        filename="a.txt",
        media_type="text/plain",
        size_bytes=1,
        extracted_chars=1,
    )
    material.chunks = [MaterialChunk(chunk_index=0, content="x", embedding=[1.0])]
    db.add(material)
    db.commit()
    db.delete(klass)
    db.commit()
    assert db.query(Material).count() == 0
    assert db.query(MaterialChunk).count() == 0


def test_lecture_summary_one_to_one(db):
    klass = _make_class(db)
    lecture = Lecture(class_id=klass.id)
    db.add(lecture)
    db.commit()
    summary = LectureSummary(lecture_id=lecture.id, content="## Overview", model="fake")
    db.add(summary)
    db.commit()
    db.refresh(lecture)
    assert lecture.summary is not None
    assert lecture.summary.content == "## Overview"
