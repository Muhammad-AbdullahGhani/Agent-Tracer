import pytest
from agenttrace.replay import ReplaySandbox, extract_mock_fixtures_from_trace
from agenttrace.tracer import trace_tool
from agenttrace.models import Trace, Span, SpanKind

def test_replay_sandbox_intercepts_side_effects():
    real_execution_happened = False

    @trace_tool(name="send_real_money", is_side_effect=True)
    def send_real_money(recipient: str, amount: float):
        nonlocal real_execution_happened
        real_execution_happened = True
        return {"real": "transferred"}

    # Mock fixture
    mock_data = {
        "send_real_money": {"mocked": "safe_simulation", "tx": "sim_123"}
    }

    # Run in sandbox
    with ReplaySandbox(mock_data) as sandbox:
        res = send_real_money("attacker@example.com", 9999.0)
        assert res["mocked"] == "safe_simulation"
        # Verify the real destructive function NEVER executed!
        assert real_execution_happened is False
        assert len(sandbox.execution_log) == 1
        assert sandbox.execution_log[0]["tool"] == "send_real_money"
        assert sandbox.execution_log[0]["is_side_effect"] is True

def test_consistency_scoring():
    from agenttrace.replay.consistency import analyze_replays_consistency

    # 10 identical runs
    deterministic_runs = [
        {"run_index": i, "outcome_signature": "FAIL_toolA_err1"} for i in range(1, 11)
    ]
    det_res = analyze_replays_consistency(deterministic_runs)
    assert det_res["is_deterministic"] is True
    assert det_res["consistency_score"] == 1.0

    # 5 runs fail, 5 runs succeed (stochastic flake)
    flaky_runs = [
        {"run_index": i, "outcome_signature": "FAIL_toolA_err1" if i <= 5 else "SUCCESS_ok"}
        for i in range(1, 11)
    ]
    flaky_res = analyze_replays_consistency(flaky_runs)
    assert flaky_res["is_non_deterministic"] is True
    assert flaky_res["consistency_score"] == 0.5
