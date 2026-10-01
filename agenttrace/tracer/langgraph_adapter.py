import time
import copy
from typing import Any, Dict, Optional, Callable
from agenttrace.tracer.interceptor import TraceSession, record_state_transition
from agenttrace.models import TraceStatus

class AgentTraceGraphRunner:
    """
    Wraps a LangGraph compiled graph to automatically capture state transitions,
    tool calls, and errors into OpenTelemetry-compatible traces.
    """
    def __init__(self, compiled_graph: Any, agent_name: str, agent_version: str = "1.0.0"):
        self.compiled_graph = compiled_graph
        self.agent_name = agent_name
        self.agent_version = agent_version

    def invoke(self, inputs: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        with TraceSession(agent_name=self.agent_name, initial_inputs=inputs, session_id=session_id) as session:
            try:
                # Execute graph
                output = self.compiled_graph.invoke(inputs)
                
                # Check for logical failure flagged in state (e.g., error key, failure status)
                is_failed = False
                err_msg = None
                
                if isinstance(output, dict):
                    if output.get("error") or output.get("status") in ["failed", "failure", "error"]:
                        is_failed = True
                        err_msg = output.get("error") or f"Execution reached failure status: {output.get('status')}"
                    elif output.get("violation") or output.get("policy_breach"):
                        is_failed = True
                        err_msg = output.get("violation") or output.get("policy_breach")
                        
                if is_failed:
                    session.mark_result(output=output, status=TraceStatus.FAILURE, error=err_msg)
                else:
                    session.mark_result(output=output, status=TraceStatus.SUCCESS)
                    
                return output
            except Exception as e:
                session.mark_result(output=None, status=TraceStatus.FAILURE, error=str(e))
                raise

    async def ainvoke(self, inputs: Dict[str, Any], session_id: Optional[str] = None) -> Dict[str, Any]:
        with TraceSession(agent_name=self.agent_name, initial_inputs=inputs, session_id=session_id) as session:
            try:
                output = await self.compiled_graph.ainvoke(inputs)
                is_failed = False
                err_msg = None
                
                if isinstance(output, dict):
                    if output.get("error") or output.get("status") in ["failed", "failure", "error"]:
                        is_failed = True
                        err_msg = output.get("error") or f"Execution reached failure status: {output.get('status')}"
                    elif output.get("violation") or output.get("policy_breach"):
                        is_failed = True
                        err_msg = output.get("violation") or output.get("policy_breach")

                if is_failed:
                    session.mark_result(output=output, status=TraceStatus.FAILURE, error=err_msg)
                else:
                    session.mark_result(output=output, status=TraceStatus.SUCCESS)
                    
                return output
            except Exception as e:
                session.mark_result(output=None, status=TraceStatus.FAILURE, error=str(e))
                raise

def trace_node(node_name: str):
    """
    Decorator for LangGraph node functions to record state before/after.
    """
    def decorator(func: Callable):
        def wrapper(state: Dict[str, Any], *args, **kwargs):
            from agenttrace.tracer.interceptor import current_trace_id
            trace_id = current_trace_id.get()
            state_before = copy.deepcopy(state) if isinstance(state, dict) else {}
            
            t0 = time.perf_counter()
            new_state = func(state, *args, **kwargs)
            t1 = time.perf_counter()
            
            if trace_id:
                state_after = copy.deepcopy(new_state) if isinstance(new_state, dict) else {}
                record_state_transition(
                    trace_id=trace_id,
                    node_name=node_name,
                    state_before=state_before,
                    state_after=state_after,
                    duration_ms=(t1 - t0) * 1000.0
                )
            return new_state
        return wrapper
    return decorator
