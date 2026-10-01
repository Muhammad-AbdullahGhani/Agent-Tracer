import time
import copy
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from agenttrace.models import RegressionFixture, TraceStatus
from agenttrace.replay import ReplaySandbox, get_agent_runner
from agenttrace.tracer.otel import generate_trace_id
from agenttrace.db import SessionLocal, crud

class RegressionSuiteRunner:
    """
    Executes all active regression fixtures against current agent code.
    If a regression resurfaces, it automatically queues a new incident for investigation!
    """
    def __init__(self, db: Optional[Session] = None):
        self.db = db

    def run_all(self, agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
        db = self.db or SessionLocal()
        should_close = (self.db is None)
        results = []
        
        try:
            fixtures = crud.get_regression_fixtures(db, agent_name=agent_name)
            for fixture in fixtures:
                res = self.run_fixture(fixture, db)
                results.append(res)
            return results
        finally:
            if should_close:
                db.close()

    def run_fixture(self, fixture: RegressionFixture, db: Session) -> Dict[str, Any]:
        runner = get_agent_runner(fixture.agent_name)
        t0 = time.perf_counter()
        passed = False
        details = ""
        output = None

        if not runner:
            passed = False
            details = f"Runner for agent '{fixture.agent_name}' not registered."
            duration_ms = 0.0
        else:
            try:
                with ReplaySandbox(fixture.mocked_tool_fixtures) as sandbox:
                    output = runner(copy.deepcopy(fixture.initial_inputs))
                    
                    # Validate assertions
                    is_failed = False
                    if isinstance(output, dict):
                        if output.get("error") or output.get("status") in ["failed", "failure", "error"]:
                            is_failed = True
                            details = output.get("error") or f"Returned status: {output.get('status')}"
                    
                    passed = not is_failed
                    if passed:
                        details = "Regression test passed: no failure detected."
            except Exception as e:
                passed = False
                details = f"Exception raised during regression test: {str(e)}"
            finally:
                duration_ms = (time.perf_counter() - t0) * 1000.0

        # Log run in DB
        crud.log_regression_run(
            db=db,
            fixture_id=fixture.id,
            passed=passed,
            actual_output=output,
            details=details,
            duration_ms=duration_ms
        )

        # Resurfaced regression handling:
        # If regression resurfaces -> Queue for replay investigation!
        if not passed:
            resurfaced_trace_id = generate_trace_id()
            crud.create_trace(
                db=db,
                trace_id=resurfaced_trace_id,
                agent_name=fixture.agent_name,
                initial_inputs=fixture.initial_inputs,
                status=TraceStatus.FAILURE,
                error_message=f"Regression resurfaced for fixture '{fixture.name}': {details}",
                final_output=output,
                latency_ms=duration_ms
            )
            resurfaced_incident = crud.create_incident(
                db=db,
                trace_id=resurfaced_trace_id,
                agent_name=fixture.agent_name
            )
            details += f" [Queued new investigation Incident #{resurfaced_incident.id}]"

        return {
            "fixture_id": fixture.id,
            "fixture_name": fixture.name,
            "agent_name": fixture.agent_name,
            "passed": passed,
            "details": details,
            "duration_ms": duration_ms
        }
