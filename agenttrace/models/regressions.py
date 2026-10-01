from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
)
from sqlalchemy.orm import relationship
from agenttrace.models.traces import Base

class RegressionFixture(Base):
    __tablename__ = "regression_fixtures"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True, index=True)
    
    name = Column(String(128), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    agent_name = Column(String(128), index=True, nullable=False)
    
    # Replay environment inputs
    initial_inputs = Column(JSON, nullable=False)
    mocked_tool_fixtures = Column(JSON, nullable=False) # Tool name -> recorded output mapping
    expected_outcome_assertion = Column(JSON, nullable=False) # e.g. {"should_not_call": "process_refund", "expected_status": "rejected"}
    
    is_active = Column(Boolean, default=True, index=True)
    last_run_status = Column(String(32), default="PENDING") # PASS, FAIL, PENDING
    last_run_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    incident = relationship("Incident", backref="regression_fixture")
    test_runs = relationship("RegressionSuiteRun", back_populates="fixture", cascade="all, delete-orphan", order_by="RegressionSuiteRun.created_at.desc()")

class RegressionSuiteRun(Base):
    __tablename__ = "regression_suite_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, ForeignKey("regression_fixtures.id", ondelete="CASCADE"), nullable=False, index=True)
    
    passed = Column(Boolean, nullable=False)
    commit_sha = Column(String(64), nullable=True)
    agent_version = Column(String(32), default="1.0.0")
    
    details = Column(Text, nullable=True)
    actual_output = Column(JSON, nullable=True)
    duration_ms = Column(Float, default=0.0)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    fixture = relationship("RegressionFixture", back_populates="test_runs")
