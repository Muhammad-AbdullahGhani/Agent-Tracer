from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from agenttrace.config import settings
from agenttrace.models import (
    Incident, IncidentStatus, FailureBucket, Trace, Span
)
from agenttrace.replay.consistency import analyze_replays_consistency
from agenttrace.analysis.divergence import locate_divergence_span
from agenttrace.analysis.llm_analyzer import analyze_failure_with_llm
from agenttrace.db import crud

async def classify_incident_investigation(
    db: Session,
    incident_id: int,
    runs_data: List[Dict[str, Any]]
) -> Incident:
    """
    Core Classification & Escalation Engine.
    Implements the flowchart:
    1. Compare outcomes across all N replays.
    2. If non-deterministic -> flag, lower confidence, escalate to human review.
    3. If deterministic / mixed majority -> locate divergence point (Model Decision, Tool Ambiguity, Missing Context, Environment).
    4. Generate human-readable explanation and evidence span.
    5. Check confidence against threshold:
       - If above threshold: attach verdict + confidence score.
       - If below threshold: escalate to human review.
    """
    incident = crud.get_incident(db, incident_id)
    if not incident:
        raise ValueError(f"Incident {incident_id} not found")
        
    trace = incident.trace
    
    # 1. Analyze consistency across replays
    consistency_data = analyze_replays_consistency(runs_data)
    consistency_score = consistency_data["consistency_score"]
    total_replays = consistency_data["total_runs"]
    dominant_count = consistency_data["dominant_outcome_count"]
    dominant_outcome = consistency_data["dominant_outcome"]
    
    # Count failed replays
    failed_replays = sum(1 for r in runs_data if r.get("status") in ["FAILURE", "ERROR"])
    
    # Build trace spans summary
    spans_summary = [
        {
            "span_id": s.span_id,
            "name": s.name,
            "kind": s.kind.value if hasattr(s.kind, "value") else str(s.kind),
            "status_code": s.status_code,
            "is_side_effect": s.is_side_effect,
            "inputs": s.inputs,
            "outputs": s.outputs,
            "error": s.error
        }
        for s in trace.spans
    ]

    # 2. Check if Non-Deterministic
    if consistency_data["is_non_deterministic"]:
        preliminary_bucket = FailureBucket.NON_DETERMINISTIC
        divergence_info = {
            "step_name": "stochastic_divergence",
            "reason": f"Tool and status sequences varied across runs ({len(consistency_data['outcome_distribution'])} distinct patterns).",
            "evidence": {"outcomes": consistency_data["outcome_distribution"]}
        }
    else:
        # 3. Locate divergence point
        divergence_info = locate_divergence_span(trace)
        preliminary_bucket = divergence_info.get("bucket", FailureBucket.DETERMINISTIC_BUG)

    # 4. Generate Root Cause Diagnosis (Open Model / Heuristic)
    diagnosis = await analyze_failure_with_llm(
        failure_bucket=preliminary_bucket,
        consistency_data=consistency_data,
        divergence_info=divergence_info,
        trace_spans_summary={"spans": spans_summary},
        trace_error=trace.error_message
    )
    
    confidence = diagnosis.get("confidence_score", consistency_score)
    final_bucket = diagnosis.get("failure_bucket", preliminary_bucket.value if hasattr(preliminary_bucket, "value") else str(preliminary_bucket))
    
    # 5. Threshold & Escalation Check
    needs_review = (
        final_bucket == FailureBucket.NON_DETERMINISTIC.value or 
        confidence < settings.CONFIDENCE_THRESHOLD
    )
    
    final_status = IncidentStatus.ESCALATED_HUMAN_REVIEW if needs_review else IncidentStatus.CLASSIFIED

    # Update Incident in DB
    updated_incident = crud.update_incident_diagnosis(
        db=db,
        incident_id=incident_id,
        status=final_status,
        failure_bucket=FailureBucket(final_bucket) if final_bucket in FailureBucket.__members__.values() else FailureBucket.UNDETERMINED,
        consistency_score=consistency_score,
        replays_total=total_replays,
        replays_failed=failed_replays,
        dominant_outcome=dominant_outcome,
        divergence_span_id=divergence_info.get("span_id"),
        divergence_step_name=divergence_info.get("step_name"),
        explanation=diagnosis.get("explanation"),
        evidence_span=diagnosis.get("evidence_span") or divergence_info.get("evidence"),
        remediation=diagnosis.get("remediation"),
        confidence_score=confidence,
        needs_human_review=needs_review
    )
    
    return updated_incident
