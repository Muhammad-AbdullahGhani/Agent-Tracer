from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from agenttrace.models import (
    Trace, Span, TraceStatus, SpanKind,
    Incident, IncidentStatus, FailureBucket,
    ReplayJob, ReplayRun,
    RegressionFixture, RegressionSuiteRun
)

# --- Traces & Spans ---

def create_trace(
    db: Session,
    trace_id: str,
    agent_name: str,
    initial_inputs: Dict[str, Any],
    session_id: Optional[str] = None,
    agent_version: str = "1.0.0",
    status: TraceStatus = TraceStatus.SUCCESS,
    is_healthy_baseline: bool = False,
    final_output: Optional[Any] = None,
    error_message: Optional[str] = None,
    latency_ms: float = 0.0,
    created_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None
) -> Trace:
    trace = Trace(
        trace_id=trace_id,
        session_id=session_id,
        agent_name=agent_name,
        agent_version=agent_version,
        initial_inputs=initial_inputs,
        final_output=final_output,
        status=status,
        is_healthy_baseline=is_healthy_baseline,
        error_message=error_message,
        latency_ms=latency_ms,
        created_at=created_at or datetime.utcnow(),
        completed_at=completed_at
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return trace

def add_span(
    db: Session,
    span_id: str,
    trace_id: str,
    name: str,
    kind: SpanKind,
    inputs: Optional[Dict[str, Any]] = None,
    outputs: Optional[Dict[str, Any]] = None,
    parent_span_id: Optional[str] = None,
    is_side_effect: bool = False,
    status_code: str = "OK",
    error: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    duration_ms: float = 0.0
) -> Span:
    span = Span(
        span_id=span_id,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        name=name,
        kind=kind,
        inputs=inputs or {},
        outputs=outputs or {},
        is_side_effect=is_side_effect,
        status_code=status_code,
        error=error,
        attributes=attributes or {},
        start_time=start_time or datetime.utcnow(),
        end_time=end_time,
        duration_ms=duration_ms
    )
    db.add(span)
    db.commit()
    db.refresh(span)
    return span

def get_trace(db: Session, trace_id: str) -> Optional[Trace]:
    return db.query(Trace).filter(Trace.trace_id == trace_id).first()

def get_traces(db: Session, skip: int = 0, limit: int = 50, status: Optional[TraceStatus] = None) -> List[Trace]:
    query = db.query(Trace)
    if status:
        query = query.filter(Trace.status == status)
    return query.order_by(desc(Trace.created_at)).offset(skip).limit(limit).all()

def get_healthy_baselines(db: Session, agent_name: str, limit: int = 5) -> List[Trace]:
    return db.query(Trace).filter(
        Trace.agent_name == agent_name,
        Trace.is_healthy_baseline == True
    ).order_by(desc(Trace.created_at)).limit(limit).all()

# --- Incidents ---

def create_incident(
    db: Session,
    trace_id: str,
    agent_name: str,
    status: IncidentStatus = IncidentStatus.QUEUED
) -> Incident:
    incident = Incident(
        trace_id=trace_id,
        agent_name=agent_name,
        status=status
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident

def get_incident(db: Session, incident_id: int) -> Optional[Incident]:
    return db.query(Incident).filter(Incident.id == incident_id).first()

def get_incident_by_trace(db: Session, trace_id: str) -> Optional[Incident]:
    return db.query(Incident).filter(Incident.trace_id == trace_id).first()

def get_incidents(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    status: Optional[IncidentStatus] = None,
    failure_bucket: Optional[FailureBucket] = None
) -> List[Incident]:
    query = db.query(Incident)
    if status:
        query = query.filter(Incident.status == status)
    if failure_bucket:
        query = query.filter(Incident.failure_bucket == failure_bucket)
    return query.order_by(desc(Incident.created_at)).offset(skip).limit(limit).all()

def update_incident_diagnosis(
    db: Session,
    incident_id: int,
    status: IncidentStatus,
    failure_bucket: FailureBucket,
    consistency_score: float,
    replays_total: int,
    replays_failed: int,
    dominant_outcome: str,
    divergence_span_id: Optional[str] = None,
    divergence_step_name: Optional[str] = None,
    explanation: Optional[str] = None,
    evidence_span: Optional[Dict[str, Any]] = None,
    remediation: Optional[str] = None,
    confidence_score: float = 0.0,
    needs_human_review: bool = False
) -> Optional[Incident]:
    incident = get_incident(db, incident_id)
    if not incident:
        return None
    
    incident.status = status
    incident.failure_bucket = failure_bucket
    incident.consistency_score = consistency_score
    incident.replays_total = replays_total
    incident.replays_failed = replays_failed
    incident.dominant_outcome = dominant_outcome
    incident.divergence_span_id = divergence_span_id
    incident.divergence_step_name = divergence_step_name
    incident.explanation = explanation
    incident.evidence_span = evidence_span
    incident.remediation = remediation
    incident.confidence_score = confidence_score
    incident.needs_human_review = needs_human_review
    incident.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(incident)
    return incident

def set_incident_feedback(
    db: Session,
    incident_id: int,
    feedback: str,
    notes: Optional[str] = None
) -> Optional[Incident]:
    incident = get_incident(db, incident_id)
    if not incident:
        return None
    
    incident.developer_feedback = feedback
    incident.developer_notes = notes
    if feedback == "CONFIRMED_BUG":
        incident.status = IncidentStatus.CONFIRMED_BUG
    elif feedback == "FALSE_POSITIVE":
        incident.status = IncidentStatus.FALSE_POSITIVE
        
    incident.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(incident)
    return incident

# --- Replays ---

def create_replay_job(db: Session, incident_id: int, n_replays: int = 10) -> ReplayJob:
    job = ReplayJob(
        incident_id=incident_id,
        n_replays=n_replays,
        status="RUNNING"
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def add_replay_run(
    db: Session,
    replay_job_id: int,
    run_index: int,
    status: str,
    outcome_signature: str,
    divergence_detected: bool = False,
    divergence_step: Optional[str] = None,
    steps_count: int = 0,
    output: Optional[Any] = None,
    error: Optional[str] = None,
    execution_steps: Optional[List[Any]] = None,
    duration_ms: float = 0.0
) -> ReplayRun:
    run = ReplayRun(
        replay_job_id=replay_job_id,
        run_index=run_index,
        status=status,
        outcome_signature=outcome_signature,
        divergence_detected=divergence_detected,
        divergence_step=divergence_step,
        steps_count=steps_count,
        output=output,
        error=error,
        execution_steps=execution_steps or [],
        duration_ms=duration_ms
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

def complete_replay_job(
    db: Session,
    job_id: int,
    status: str,
    dominant_outcome: str,
    consistency_ratio: float
) -> Optional[ReplayJob]:
    job = db.query(ReplayJob).filter(ReplayJob.id == job_id).first()
    if not job:
        return None
    job.status = status
    job.dominant_outcome = dominant_outcome
    job.consistency_ratio = consistency_ratio
    job.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    return job

# --- Regressions ---

def create_regression_fixture(
    db: Session,
    incident_id: Optional[int],
    name: str,
    agent_name: str,
    initial_inputs: Dict[str, Any],
    mocked_tool_fixtures: Dict[str, Any],
    expected_outcome_assertion: Dict[str, Any],
    description: Optional[str] = None
) -> RegressionFixture:
    fixture = RegressionFixture(
        incident_id=incident_id,
        name=name,
        agent_name=agent_name,
        description=description,
        initial_inputs=initial_inputs,
        mocked_tool_fixtures=mocked_tool_fixtures,
        expected_outcome_assertion=expected_outcome_assertion,
        is_active=True
    )
    db.add(fixture)
    db.commit()
    db.refresh(fixture)
    return fixture

def get_regression_fixtures(db: Session, agent_name: Optional[str] = None) -> List[RegressionFixture]:
    query = db.query(RegressionFixture).filter(RegressionFixture.is_active == True)
    if agent_name:
        query = query.filter(RegressionFixture.agent_name == agent_name)
    return query.order_by(desc(RegressionFixture.created_at)).all()

def log_regression_run(
    db: Session,
    fixture_id: int,
    passed: bool,
    actual_output: Optional[Any] = None,
    details: Optional[str] = None,
    duration_ms: float = 0.0
) -> RegressionSuiteRun:
    fixture = db.query(RegressionFixture).filter(RegressionFixture.id == fixture_id).first()
    if fixture:
        fixture.last_run_status = "PASS" if passed else "FAIL"
        fixture.last_run_at = datetime.utcnow()

    run = RegressionSuiteRun(
        fixture_id=fixture_id,
        passed=passed,
        actual_output=actual_output,
        details=details,
        duration_ms=duration_ms
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run

# --- Stats & Overview ---

def get_stats(db: Session) -> Dict[str, Any]:
    total_traces = db.query(func.count(Trace.id)).scalar() or 0
    total_failures = db.query(func.count(Trace.id)).filter(Trace.status == TraceStatus.FAILURE).scalar() or 0
    total_incidents = db.query(func.count(Incident.id)).scalar() or 0
    
    bucket_counts = db.query(
        Incident.failure_bucket, func.count(Incident.id)
    ).group_by(Incident.failure_bucket).all()
    
    bucket_map = {bucket.value if hasattr(bucket, 'value') else str(bucket): count for bucket, count in bucket_counts}
    
    deterministic_count = bucket_map.get(FailureBucket.DETERMINISTIC_BUG.value, 0) + \
                          bucket_map.get(FailureBucket.MODEL_DECISION_FAILURE.value, 0) + \
                          bucket_map.get(FailureBucket.TOOL_DATA_AMBIGUITY.value, 0) + \
                          bucket_map.get(FailureBucket.MISSING_CONTEXT_FAILURE.value, 0)
                          
    non_deterministic_count = bucket_map.get(FailureBucket.NON_DETERMINISTIC.value, 0)
    
    active_regressions = db.query(func.count(RegressionFixture.id)).filter(RegressionFixture.is_active == True).scalar() or 0
    
    return {
        "total_traces": total_traces,
        "total_failures": total_failures,
        "total_incidents": total_incidents,
        "deterministic_count": deterministic_count,
        "non_deterministic_count": non_deterministic_count,
        "active_regressions": active_regressions,
        "failure_buckets": bucket_map
    }
