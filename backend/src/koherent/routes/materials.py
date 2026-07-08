"""Course-material ingestion routes. Endpoint bodies land with the materials task."""
from fastapi import APIRouter

router = APIRouter(prefix="/classes", tags=["materials"])
