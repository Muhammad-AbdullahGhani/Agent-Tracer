from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class SpanKind(str, Enum):
    AGENT_RUN = "AGENT_RUN"
    LLM_CALL = "LLM_CALL"
    TOOL_CALL = "TOOL_CALL"
    STATE_TRANSITION = "STATE_TRANSITION"
    EVALUATION = "EVALUATION"

class TraceStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNEXPECTED = "UNEXPECTED"

class Trace(Base):
    __tablename__ = "traces"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String(64), unique=True, index=True, nullable=False)
    session_id = Column(String(64), index=True, nullable=True)
    agent_name = Column(String(128), index=True, nullable=False)
    agent_version = Column(String(32), default="1.0.0")
    
    initial_inputs = Column(JSON, nullable=False, default=dict)
    final_output = Column(JSON, nullable=True)
    
    status = Column(SQLEnum(TraceStatus), default=TraceStatus.SUCCESS, index=True)
    is_healthy_baseline = Column(Boolean, default=False, index=True)
    
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    
    spans = relationship("Span", back_populates="trace", cascade="all, delete-orphan", order_by="Span.start_time")

class Span(Base):
    __tablename__ = "spans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    span_id = Column(String(64), unique=True, index=True, nullable=False)
    trace_id = Column(String(64), ForeignKey("traces.trace_id", ondelete="CASCADE"), nullable=False, index=True)
    parent_span_id = Column(String(64), nullable=True, index=True)
    
    name = Column(String(128), nullable=False)
    kind = Column(SQLEnum(SpanKind), nullable=False, index=True)
    
    start_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_ms = Column(Float, default=0.0)
    
    inputs = Column(JSON, default=dict)
    outputs = Column(JSON, default=dict)
    
    is_side_effect = Column(Boolean, default=False, index=True)
    status_code = Column(String(16), default="OK")  # "OK", "ERROR"
    error = Column(Text, nullable=True)
    
    attributes = Column(JSON, default=dict)  # model name, token usage, tool args, state node, etc.

    trace = relationship("Trace", back_populates="spans")
