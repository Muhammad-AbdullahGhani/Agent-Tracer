import pytest
from agenttrace.tracer import trace_tool, TraceSession, is_tool_side_effect
from agenttrace.models import TraceStatus
from agenttrace.db import init_db, SessionLocal, crud

@pytest.fixture(autouse=True)
def setup_db():
    init_db()

def test_side_effect_detection():
    assert is_tool_side_effect("process_refund") is True
    assert is_tool_side_effect("send_email") is True
    assert is_tool_side_effect("get_user_profile") is False
    assert is_tool_side_effect("fetch_orders") is False

def test_trace_tool_interception():
    call_counter = {"read": 0, "side_effect": 0}

    @trace_tool(name="read_data", is_side_effect=False)
    def read_data(x: int):
        call_counter["read"] += 1
        return {"data": x * 2}

    @trace_tool(name="mutate_account", is_side_effect=True)
    def mutate_account(amount: float):
        call_counter["side_effect"] += 1
        return {"status": "debited", "amount": amount}

    with TraceSession(agent_name="unit_test_agent", initial_inputs={"val": 42}) as session:
        r1 = read_data(10)
        assert r1 == {"data": 20}
        r2 = mutate_account(50.0)
        assert r2["status"] == "debited"
        session.mark_result(output={"ok": True}, status=TraceStatus.SUCCESS)

    # Verify spans persisted
    with SessionLocal() as db:
        trace = crud.get_trace(db, session.trace_id)
        assert trace is not None
        assert trace.status == TraceStatus.SUCCESS
        assert len(trace.spans) == 2
        
        span_names = [s.name for s in trace.spans]
        assert "read_data" in span_names
        assert "mutate_account" in span_names
        
        mutate_span = next(s for s in trace.spans if s.name == "mutate_account")
        assert mutate_span.is_side_effect is True
