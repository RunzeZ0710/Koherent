"""Lecture study artifacts (summary/review). Endpoint bodies land with the study task."""
from fastapi import APIRouter

router = APIRouter(prefix="/lectures", tags=["study"])
