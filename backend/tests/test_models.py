import secrets

from koherent.models import Class, Student


def test_can_persist_class_and_student(db):
    klass = Class(name="Econ 101", join_code="ABC123", owner_token=secrets.token_urlsafe(32))
    db.add(klass)
    db.flush()

    student = Student(class_id=klass.id, display_name="Alice", session_token=secrets.token_urlsafe(32))
    db.add(student)
    db.flush()

    refetched = db.get(Class, klass.id)
    assert refetched is not None
    assert refetched.name == "Econ 101"
    assert len(refetched.students) == 1
    assert refetched.students[0].display_name == "Alice"
