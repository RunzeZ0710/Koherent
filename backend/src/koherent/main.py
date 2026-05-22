from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from koherent.config import settings
from koherent.routes import classes

app = FastAPI(title="Koherent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(classes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
