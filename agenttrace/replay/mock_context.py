from typing import Dict, Any, List, Optional
from agenttrace.tracer.interceptor import active_replay_mock_map, active_replay_log
from agenttrace.models import Trace, Span, SpanKind

class ReplaySandbox:
    """
    Context manager that isolates an agent execution in a deterministic replay environment.
    All side-effects are intercepted and mocked using recorded data from the original trace.
    """
    def __init__(self, mock_map: Dict[str, Any]):
        self.mock_map = mock_map
        self.execution_log: List[Dict[str, Any]] = []
        self._token_mock = None
        self._token_log = None

    def __enter__(self):
        self._token_mock = active_replay_mock_map.set(self.mock_map)
        self._token_log = active_replay_log.set(self.execution_log)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._token_mock:
            active_replay_mock_map.reset(self._token_mock)
        if self._token_log:
            active_replay_log.reset(self._token_log)

def extract_mock_fixtures_from_trace(trace: Trace) -> Dict[str, Any]:
    """
    Extracts recorded tool responses and outputs from a trace's spans
    to build the deterministic replay fixture map.
    Faithfully records both successful responses and recorded tool exceptions.
    """
    mock_map: Dict[str, Any] = {}
    for span in trace.spans:
        if span.kind == SpanKind.TOOL_CALL:
            output_data = span.outputs or {}
            if span.status_code == "ERROR" or span.error:
                mock_map[span.name] = {"__replay_error__": span.error or "Recorded tool exception"}
            elif "result" in output_data:
                mock_map[span.name] = output_data["result"]
            else:
                mock_map[span.name] = output_data
    return mock_map
