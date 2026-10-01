from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agenttrace.db import get_db, crud
from agenttrace.models import IncidentStatus, FailureBucket
from agenttrace.replay import ReplayEngine
from agenttrace.regression import create_fixture_from_incident, export_pytest_file

router = APIRouter(prefix="/incidents", tags=["Incidents & Investigations"])

class FeedbackRequest(BaseModel):
    action: str  # "CONFIRMED_BUG" or "FALSE_POSITIVE"
    notes: Optional[str] = None
    export_pytest: bool = True

class InvestigationRequest(BaseModel):
    n_replays: int = 10

@router.get("")
def list_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[IncidentStatus] = None,
    failure_bucket: Optional[FailureBucket] = None,
    db: Session = Depends(get_db)
):
    incidents = crud.get_incidents(db, skip=skip, limit=limit, status=status, failure_bucket=failure_bucket)
    return [
        {
            "id": inc.id,
            "trace_id": inc.trace_id,
            "agent_name": inc.agent_name,
            "status": inc.status.value if hasattr(inc.status, "value") else str(inc.status),
            "failure_bucket": inc.failure_bucket.value if hasattr(inc.failure_bucket, "value") else str(inc.failure_bucket),
            "consistency_score": inc.consistency_score,
            "confidence_score": inc.confidence_score,
            "replays_total": inc.replays_total,
            "replays_failed": inc.replays_failed,
            "dominant_outcome": inc.dominant_outcome,
            "divergence_step_name": inc.divergence_step_name,
            "needs_human_review": inc.needs_human_review,
            "developer_feedback": inc.developer_feedback,
            "created_at": inc.created_at.isoformat() if inc.created_at else None,
            "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
        }
        for inc in incidents
    ]

@router.get("/{incident_id}")
def get_incident_detail(incident_id: int, db: Session = Depends(get_db)):
    inc = crud.get_incident(db, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    replay_jobs_data = []
    for job in inc.replay_jobs:
        runs_list = [
            {
                "id": r.id,
                "run_index": r.run_index,
                "status": r.status,
                "outcome_signature": r.outcome_signature,
                "divergence_detected": r.divergence_detected,
                "divergence_step": r.divergence_step,
                "steps_count": r.steps_count,
                "output": r.output,
                "error": r.error,
                "duration_ms": round(r.duration_ms, 2),
                "execution_steps": r.execution_steps
            }
            for r in job.runs
        ]
        replay_jobs_data.append({
            "id": job.id,
            "n_replays": job.n_replays,
            "status": job.status,
            "dominant_outcome": job.dominant_outcome,
            "consistency_ratio": job.consistency_ratio,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "runs": runs_list
        })

    trace_data = None
    if inc.trace:
        trace_data = {
            "trace_id": inc.trace.trace_id,
            "initial_inputs": inc.trace.initial_inputs,
            "final_output": inc.trace.final_output,
            "error_message": inc.trace.error_message,
            "latency_ms": round(inc.trace.latency_ms, 2),
            "spans": [
                {
                    "span_id": s.span_id,
                    "name": s.name,
                    "kind": s.kind.value if hasattr(s.kind, "value") else str(s.kind),
                    "status_code": s.status_code,
                    "duration_ms": round(s.duration_ms, 2),
                    "is_side_effect": s.is_side_effect,
                    "inputs": s.inputs,
                    "outputs": s.outputs,
                    "error": s.error
                }
                for s in inc.trace.spans
            ]
        }

    return {
        "id": inc.id,
        "trace_id": inc.trace_id,
        "agent_name": inc.agent_name,
        "status": inc.status.value if hasattr(inc.status, "value") else str(inc.status),
        "failure_bucket": inc.failure_bucket.value if hasattr(inc.failure_bucket, "value") else str(inc.failure_bucket),
        "consistency_score": inc.consistency_score,
        "confidence_score": inc.confidence_score,
        "replays_total": inc.replays_total,
        "replays_failed": inc.replays_failed,
        "dominant_outcome": inc.dominant_outcome,
        "divergence_span_id": inc.divergence_span_id,
        "divergence_step_name": inc.divergence_step_name,
        "explanation": inc.explanation,
        "evidence_span": inc.evidence_span,
        "remediation": inc.remediation,
        "needs_human_review": inc.needs_human_review,
        "developer_feedback": inc.developer_feedback,
        "developer_notes": inc.developer_notes,
        "created_at": inc.created_at.isoformat() if inc.created_at else None,
        "updated_at": inc.updated_at.isoformat() if inc.updated_at else None,
        "trace": trace_data,
        "replay_jobs": replay_jobs_data
    }

@router.post("/{incident_id}/investigate")
async def trigger_replay_investigation(
    incident_id: int,
    req: InvestigationRequest = InvestigationRequest(),
    db: Session = Depends(get_db)
):
    inc = crud.get_incident(db, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    engine = ReplayEngine(db=db)
    updated_incident = await engine.execute_investigation(
        incident_id=incident_id,
        n_replays=req.n_replays
    )
    return {
        "message": f"Investigation completed for Incident #{incident_id}",
        "status": updated_incident.status.value,
        "failure_bucket": updated_incident.failure_bucket.value,
        "consistency_score": updated_incident.consistency_score,
        "confidence_score": updated_incident.confidence_score,
        "explanation": updated_incident.explanation,
        "remediation": updated_incident.remediation
    }

@router.post("/{incident_id}/feedback")
def submit_developer_feedback(
    incident_id: int,
    req: FeedbackRequest,
    db: Session = Depends(get_db)
):
    inc = crud.get_incident(db, incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    updated_inc = crud.set_incident_feedback(
        db=db,
        incident_id=incident_id,
        feedback=req.action,
        notes=req.notes
    )

    fixture_id = None
    pytest_path = None

    # If confirmed real bug -> Add to regression suite with mocked replay fixtures!
    if req.action == "CONFIRMED_BUG":
        fixture = create_fixture_from_incident(
            db=db,
            incident_id=incident_id,
            description=req.notes or f"Regression test for incident #{incident_id}"
        )
        fixture_id = fixture.id
        if req.export_pytest:
            pytest_path = export_pytest_file(fixture)

    return {
        "message": f"Feedback '{req.action}' recorded for Incident #{incident_id}",
        "status": updated_inc.status.value,
        "regression_fixture_id": fixture_id,
        "pytest_path": pytest_path
    }
