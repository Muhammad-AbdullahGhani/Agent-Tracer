import uuid
import pytest
from agenttrace.db import init_db, SessionLocal, crud
from agenttrace.models import TraceStatus, IncidentStatus, FailureBucket
from agenttrace.regression import create_fixture_from_incident, export_pytest_file, RegressionSuiteRunner
from agenttrace.replay import register_agent_runner

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_regression_fixture_and_runner(tmp_path):
    unique_suffix = uuid.uuid4().hex[:8]
    trace_id = f"test_reg_trace_{unique_suffix}"
    span_id = f"span_tool_{unique_suffix}"
    with SessionLocal() as db:
        trace = crud.create_trace(
            db=db,
            trace_id=trace_id,
            agent_name="mock_test_agent",
            initial_inputs={"query": "test input"},
            status=TraceStatus.FAILURE,
            error_message="Simulated failure"
        )
        crud.add_span(
            db=db,
            span_id=span_id,
            trace_id=trace.trace_id,
            name="fetch_data",
            kind=crud.SpanKind.TOOL_CALL,
            outputs={"result": {"status": "ok", "value": 100}}
        )
        inc = crud.create_incident(db, trace_id=trace.trace_id, agent_name="mock_test_agent")
        crud.update_incident_diagnosis(
            db=db,
            incident_id=inc.id,
            status=IncidentStatus.CONFIRMED_BUG,
            failure_bucket=FailureBucket.MODEL_DECISION_FAILURE,
            consistency_score=1.0,
            replays_total=10,
            replays_failed=10,
            dominant_outcome="FAIL",
            explanation="Model decision error in test"
        )

        # Create regression fixture
        fixture_name = f"test_fixture_unit_{unique_suffix}"
        fixture = create_fixture_from_incident(db, incident_id=inc.id, custom_name=fixture_name)
        assert fixture is not None
        assert fixture.name == fixture_name
        assert "fetch_data" in fixture.mocked_tool_fixtures

        # Export pytest file
        pytest_file = export_pytest_file(fixture, output_dir=str(tmp_path))
        assert pytest_file is not None

        # Register a runner that passes
        register_agent_runner("mock_test_agent", lambda inputs: {"status": "success", "result": "fixed"})

        # Run regression suite
        suite_runner = RegressionSuiteRunner(db=db)
        results = suite_runner.run_all(agent_name="mock_test_agent")
        assert len(results) >= 1
        matched = next(r for r in results if r["fixture_name"] == "test_fixture_unit")
        assert matched["passed"] is True
