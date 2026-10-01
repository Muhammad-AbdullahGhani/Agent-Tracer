from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from agenttrace.models.traces import Base

class IncidentStatus(str, Enum):
    QUEUED = "QUEUED"
    REPLAYING = "REPLAYING"
    CLASSIFIED = "CLASSIFIED"
    ESCALATED_HUMAN_REVIEW = "ESCALATED_HUMAN_REVIEW"
    CONFIRMED_BUG = "CONFIRMED_BUG"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    RESOLVED = "RESOLVED"

class FailureBucket(str, Enum):
    DETERMINISTIC_BUG = "DETERMINISTIC_BUG"
    NON_DETERMINISTIC = "NON_DETERMINISTIC"
    MODEL_DECISION_FAILURE = "MODEL_DECISION_FAILURE"
    TOOL_DATA_AMBIGUITY = "TOOL_DATA_AMBIGUITY"
    MISSING_CONTEXT_FAILURE = "MISSING_CONTEXT_FAILURE"
    ENVIRONMENT_ISSUE = "ENVIRONMENT_ISSUE"
    UNDETERMINED = "UNDETERMINED"

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), ForeignKey("traces.trace_id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    agent_name = Column(String(128), index=True, nullable=False)
    
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.QUEUED, index=True)
    failure_bucket = Column(SQLEnum(FailureBucket), default=FailureBucket.UNDETERMINED, index=True)
    
    # Consistency metrics
    consistency_score = Column(Float, default=0.0) # dominant_outcome_count / N (0.0 to 1.0)
    replays_total = Column(Integer, default=0)
    replays_failed = Column(Integer, default=0)
    dominant_outcome = Column(String(128), nullable=True)
    
    # Root Cause Diagnosis
    divergence_span_id = Column(String(64), nullable=True) # The exact span where execution diverged
    divergence_step_name = Column(String(128), nullable=True)
    explanation = Column(Text, nullable=True) # Human-readable root cause explanation
    evidence_span = Column(JSON, nullable=True) # Detailed payload/snippet of the problematic span
    remediation = Column(Text, nullable=True) # Actionable fix recommendation
    confidence_score = Column(Float, default=0.0) # LLM / analysis confidence
    needs_human_review = Column(Boolean, default=False, index=True)
    
    # Developer Feedback
    developer_feedback = Column(String(32), nullable=True) # "CONFIRMED_BUG", "FALSE_POSITIVE"
    developer_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    trace = relationship("Trace", backref="incident", uselist=False)
    replay_jobs = relationship("ReplayJob", back_populates="incident", cascade="all, delete-orphan")

class ReplayJob(Base):
    __tablename__ = "replay_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    n_replays = Column(Integer, default=10)
    status = Column(String(32), default="RUNNING") # RUNNING, COMPLETED, FAILED
    
    dominant_outcome = Column(String(128), nullable=True)
    consistency_ratio = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    incident = relationship("Incident", back_populates="replay_jobs")
    runs = relationship("ReplayRun", back_populates="replay_job", cascade="all, delete-orphan", order_by="ReplayRun.run_index")

class ReplayRun(Base):
    __tablename__ = "replay_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replay_job_id = Column(Integer, ForeignKey("replay_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    run_index = Column(Integer, nullable=False) # 1..N
    
    status = Column(String(32), default="SUCCESS") # SUCCESS, FAILURE, ERROR
    outcome_signature = Column(String(256), nullable=False) # Hash or identifier of tool path & status
    
    divergence_detected = Column(Boolean, default=False)
    divergence_step = Column(String(128), nullable=True)
    
    steps_count = Column(Integer, default=0)
    output = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    execution_steps = Column(JSON, default=list) # Detailed log of tool calls and node transitions
    
    duration_ms = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    replay_job = relationship("ReplayJob", back_populates="runs")
