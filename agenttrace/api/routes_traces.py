from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agenttrace.db import get_db, crud
from agenttrace.models import TraceStatus, SpanKind

router = APIRouter(prefix="/traces", tags=["Traces"])

@router.get("")
def list_traces(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[TraceStatus] = None,
    db: Session = Depends(get_db)
):
    traces = crud.get_traces(db, skip=skip, limit=limit, status=status)
    return [
        {
            "id": t.id,
            "trace_id": t.trace_id,
            "session_id": t.session_id,
            "agent_name": t.agent_name,
            "agent_version": t.agent_version,
            "status": t.status.value if hasattr(t.status, "value") else str(t.status),
            "is_healthy_baseline": t.is_healthy_baseline,
            "latency_ms": round(t.latency_ms, 2),
            "error_message": t.error_message,
            "spans_count": len(t.spans),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in traces
    ]

@router.get("/baselines")
def list_healthy_baselines(agent_name: str, limit: int = 5, db: Session = Depends(get_db)):
    baselines = crud.get_healthy_baselines(db, agent_name=agent_name, limit=limit)
    return [
        {
            "trace_id": b.trace_id,
            "agent_name": b.agent_name,
            "latency_ms": round(b.latency_ms, 2),
            "initial_inputs": b.initial_inputs,
            "final_output": b.final_output,
            "spans_count": len(b.spans),
            "created_at": b.created_at.isoformat() if b.created_at else None
        }
        for b in baselines
    ]

@router.get("/{trace_id}")
def get_trace_detail(trace_id: str, db: Session = Depends(get_db)):
    trace = crud.get_trace(db, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    spans_data = []
    for s in trace.spans:
        spans_data.append({
            "id": s.id,
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "name": s.name,
            "kind": s.kind.value if hasattr(s.kind, "value") else str(s.kind),
            "is_side_effect": s.is_side_effect,
            "status_code": s.status_code,
            "duration_ms": round(s.duration_ms, 2),
            "inputs": s.inputs,
            "outputs": s.outputs,
            "error": s.error,
            "attributes": s.attributes,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None
        })

    return {
        "id": trace.id,
        "trace_id": trace.trace_id,
        "session_id": trace.session_id,
        "agent_name": trace.agent_name,
        "agent_version": trace.agent_version,
        "status": trace.status.value if hasattr(trace.status, "value") else str(trace.status),
        "is_healthy_baseline": trace.is_healthy_baseline,
        "latency_ms": round(trace.latency_ms, 2),
        "initial_inputs": trace.initial_inputs,
        "final_output": trace.final_output,
        "error_message": trace.error_message,
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
        "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
        "spans": spans_data
    }
