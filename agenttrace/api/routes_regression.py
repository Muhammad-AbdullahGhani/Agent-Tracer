from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from agenttrace.db import get_db, crud
from agenttrace.regression import RegressionSuiteRunner

router = APIRouter(prefix="/regression", tags=["Regression Suite"])

@router.get("/fixtures")
def list_regression_fixtures(agent_name: Optional[str] = None, db: Session = Depends(get_db)):
    fixtures = crud.get_regression_fixtures(db, agent_name=agent_name)
    return [
        {
            "id": f.id,
            "incident_id": f.incident_id,
            "name": f.name,
            "agent_name": f.agent_name,
            "description": f.description,
            "is_active": f.is_active,
            "last_run_status": f.last_run_status,
            "last_run_at": f.last_run_at.isoformat() if f.last_run_at else None,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "mocked_tools_count": len(f.mocked_tool_fixtures or {})
        }
        for f in fixtures
    ]

@router.post("/run")
def run_regression_suite(agent_name: Optional[str] = None, db: Session = Depends(get_db)):
    runner = RegressionSuiteRunner(db=db)
    results = runner.run_all(agent_name=agent_name)
    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    return {
        "total_fixtures": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "results": results
    }
