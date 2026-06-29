from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from koherent.config import settings
from koherent.deps import get_current_student
from koherent.models import Student
from koherent.routes import classes, lectures, processing
from koherent.schemas import StudentSession

app = FastAPI(title="Koherent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(classes.router)
app.include_router(lectures.router)
app.include_router(processing.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/me", response_model=StudentSession)
def me(current: Student = Depends(get_current_student)) -> StudentSession:
    return StudentSession(
        student_id=current.id,
        class_id=current.class_id,
        display_name=current.display_name,
        session_token=current.session_token,
    )
