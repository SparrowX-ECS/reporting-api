# routes/health.py

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/api/reporting/health")
def api_health():
    return {"status": "ok"}