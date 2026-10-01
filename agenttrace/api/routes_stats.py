from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from agenttrace.db import get_db, crud

router = APIRouter(prefix="/stats", tags=["Statistics & Overview"])

@router.get("")
def get_system_stats(db: Session = Depends(get_db)):
    stats = crud.get_stats(db)
    total_incidents = stats["total_incidents"]
    flake_rate = round((stats["non_deterministic_count"] / total_incidents * 100), 1) if total_incidents > 0 else 0.0
    deterministic_rate = round((stats["deterministic_count"] / total_incidents * 100), 1) if total_incidents > 0 else 0.0

    return {
        **stats,
        "flake_rate_percent": flake_rate,
        "deterministic_rate_percent": deterministic_rate
    }
