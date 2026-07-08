"""Grounded Q&A routes (ask/explain). Endpoint bodies land with the assistant task."""
from fastapi import APIRouter

router = APIRouter(prefix="/classes", tags=["assistant"])
