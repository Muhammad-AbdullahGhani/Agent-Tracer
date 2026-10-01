import functools
import inspect
import time
from datetime import datetime
from contextvars import ContextVar
from typing import Optional, Dict, Any, Callable, List
from agenttrace.config import settings
from agenttrace.models import SpanKind, TraceStatus
from agenttrace.db import SessionLocal, crud
from agenttrace.tracer.otel import generate_trace_id, generate_span_id

# Context variables for tracking active trace and replay environments
current_trace_id: ContextVar[Optional[str]] = ContextVar("current_trace_id", default=None)
current_parent_span_id: ContextVar[Optional[str]] = ContextVar("current_parent_span_id", default=None)
active_replay_mock_map: ContextVar[Optional[Dict[str, Any]]] = ContextVar("active_replay_mock_map", default=None)
active_replay_log: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("active_replay_log", default=None)

def is_tool_side_effect(tool_name: str, explicit_flag: Optional[bool] = None) -> bool:
    if explicit_flag is not None:
        return explicit_flag
    name_lower = tool_name.lower()
    return any(keyword in name_lower for keyword in settings.SIDE_EFFECT_KEYWORDS)

class TraceSession:
    """Context manager to scope an agent run trace."""
    def __init__(self, agent_name: str, initial_inputs: Dict[str, Any], session_id: Optional[str] = None):
        self.trace_id = generate_trace_id()
        self.agent_name = agent_name
        self.initial_inputs = initial_inputs
        self.session_id = session_id
        self.start_time = None
        self._marked_status = None
        self._marked_output = None
        self._marked_error = None
        self._token_trace = None

    def __enter__(self):
        self.start_time = datetime.utcnow()
        self._is_replay = active_replay_mock_map.get() is not None
        self._token_trace = current_trace_id.set(self.trace_id)
        
        # Only persist production traces (not replay sandbox runs)
        if not self._is_replay:
            with SessionLocal() as db:
                crud.create_trace(
                    db=db,
                    trace_id=self.trace_id,
                    session_id=self.session_id,
                    agent_name=self.agent_name,
                    initial_inputs=self.initial_inputs,
                    created_at=self.start_time
                )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        completed_at = datetime.utcnow()
        duration_ms = (completed_at - self.start_time).total_seconds() * 1000.0
        
        if exc_type is not None:
            status = TraceStatus.FAILURE
            error_msg = str(exc_val)
        elif self._marked_status is not None:
            status = self._marked_status
            error_msg = self._marked_error
        else:
            status = TraceStatus.SUCCESS
            error_msg = None
        
        # Only persist production traces
        if not getattr(self, "_is_replay", False):
            with SessionLocal() as db:
                trace_obj = crud.get_trace(db, self.trace_id)
                if trace_obj:
                    trace_obj.completed_at = completed_at
                    trace_obj.latency_ms = duration_ms
                    trace_obj.status = status
                    if self._marked_output is not None:
                        trace_obj.final_output = self._marked_output
                    if error_msg is not None:
                        trace_obj.error_message = error_msg
                    trace_obj.is_healthy_baseline = (status == TraceStatus.SUCCESS)
                    db.commit()
                    
                    # If failed and not already queued, queue incident for replay investigation
                    if status == TraceStatus.FAILURE:
                        existing_inc = crud.get_incident_by_trace(db, self.trace_id)
                        if not existing_inc:
                            crud.create_incident(db, trace_id=self.trace_id, agent_name=self.agent_name)
                        
        if self._token_trace:
            current_trace_id.reset(self._token_trace)

    def mark_result(self, output: Any, status: TraceStatus = TraceStatus.SUCCESS, error: Optional[str] = None):
        self._marked_status = status
        self._marked_output = output
        self._marked_error = error
        if not getattr(self, "_is_replay", False):
            with SessionLocal() as db:
                trace_obj = crud.get_trace(db, self.trace_id)
                if trace_obj:
                    trace_obj.final_output = output
                    trace_obj.status = status
                    trace_obj.error_message = error
                    trace_obj.is_healthy_baseline = (status == TraceStatus.SUCCESS)
                    db.commit()
                    
                    if status == TraceStatus.FAILURE:
                        existing_inc = crud.get_incident_by_trace(db, self.trace_id)
                        if not existing_inc:
                            crud.create_incident(db, trace_id=self.trace_id, agent_name=self.agent_name)

def trace_tool(name: Optional[str] = None, is_side_effect: Optional[bool] = None):
    """
    Decorator to wrap agent tools.
    - During production: records input, output, duration, and side-effect flag to database.
    - During replay: if side-effect or configured, intercepts and returns recorded mock response!
    """
    def decorator(func: Callable):
        tool_name = name or func.__name__
        side_effect = is_tool_side_effect(tool_name, is_side_effect)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Check if running inside replay sandbox
            mock_map = active_replay_mock_map.get()
            replay_log = active_replay_log.get()
            
            # Form call arguments
            bound = {}
            try:
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                bound = dict(bound_args.arguments)
            except Exception:
                bound = {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}}

            # REPLAY SANDBOX EXECUTION
            if mock_map is not None:
                # Intercept!
                # If it's a side-effect, NEVER run live! Return recorded mock.
                mock_response = mock_map.get(tool_name)
                record_entry = {
                    "tool": tool_name,
                    "inputs": bound,
                    "is_side_effect": side_effect,
                    "intercepted_replay": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
                if mock_response is not None:
                    if isinstance(mock_response, dict) and "__replay_error__" in mock_response:
                        err_msg = mock_response["__replay_error__"]
                        record_entry["error"] = err_msg
                        if replay_log is not None:
                            replay_log.append(record_entry)
                        raise RuntimeError(err_msg)

                    record_entry["mock_response"] = mock_response
                    if replay_log is not None:
                        replay_log.append(record_entry)
                    return mock_response
                elif not side_effect:
                    # Safe pure read tool can be executed if no mock found
                    result = func(*args, **kwargs)
                    record_entry["live_response"] = result
                    if replay_log is not None:
                        replay_log.append(record_entry)
                    return result
                else:
                    # Side effect with missing mock: safely stub to prevent live execution
                    stub = {"status": "mocked_side_effect", "message": f"Safely mocked {tool_name}"}
                    record_entry["mock_response"] = stub
                    if replay_log is not None:
                        replay_log.append(record_entry)
                    return stub

            # LIVE PRODUCTION EXECUTION
            trace_id = current_trace_id.get()
            span_id = generate_span_id()
            start_time = datetime.utcnow()
            t0 = time.perf_counter()
            error_str = None
            status_code = "OK"
            result = None

            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error_str = str(e)
                status_code = "ERROR"
                raise
            finally:
                t1 = time.perf_counter()
                duration_ms = (t1 - t0) * 1000.0
                end_time = datetime.utcnow()
                if trace_id:
                    with SessionLocal() as db:
                        crud.add_span(
                            db=db,
                            span_id=span_id,
                            trace_id=trace_id,
                            name=tool_name,
                            kind=SpanKind.TOOL_CALL,
                            inputs=bound,
                            outputs={"result": result} if status_code == "OK" else {},
                            is_side_effect=side_effect,
                            status_code=status_code,
                            error=error_str,
                            attributes={"tool_name": tool_name, "is_side_effect": side_effect},
                            start_time=start_time,
                            end_time=end_time,
                            duration_ms=duration_ms
                        )

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            mock_map = active_replay_mock_map.get()
            replay_log = active_replay_log.get()

            bound = {}
            try:
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                bound = dict(bound_args.arguments)
            except Exception:
                bound = {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}}

            if mock_map is not None:
                mock_response = mock_map.get(tool_name)
                record_entry = {
                    "tool": tool_name,
                    "inputs": bound,
                    "is_side_effect": side_effect,
                    "intercepted_replay": True,
                    "timestamp": datetime.utcnow().isoformat()
                }
                if mock_response is not None:
                    if isinstance(mock_response, dict) and "__replay_error__" in mock_response:
                        err_msg = mock_response["__replay_error__"]
                        record_entry["error"] = err_msg
                        if replay_log is not None:
                            replay_log.append(record_entry)
                        raise RuntimeError(err_msg)

                    record_entry["mock_response"] = mock_response
                    if replay_log is not None:
                        replay_log.append(record_entry)
                    return mock_response
                elif not side_effect:
                    result = await func(*args, **kwargs)
                    record_entry["live_response"] = result
                    if replay_log is not None:
                        replay_log.append(record_entry)
                    return result
                else:
                    stub = {"status": "mocked_side_effect", "message": f"Safely mocked {tool_name}"}
                    record_entry["mock_response"] = stub
                    if replay_log is not None:
                        replay_log.append(record_entry)
                    return stub

            trace_id = current_trace_id.get()
            span_id = generate_span_id()
            start_time = datetime.utcnow()
            t0 = time.perf_counter()
            error_str = None
            status_code = "OK"
            result = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error_str = str(e)
                status_code = "ERROR"
                raise
            finally:
                t1 = time.perf_counter()
                duration_ms = (t1 - t0) * 1000.0
                end_time = datetime.utcnow()
                if trace_id:
                    with SessionLocal() as db:
                        crud.add_span(
                            db=db,
                            span_id=span_id,
                            trace_id=trace_id,
                            name=tool_name,
                            kind=SpanKind.TOOL_CALL,
                            inputs=bound,
                            outputs={"result": result} if status_code == "OK" else {},
                            is_side_effect=side_effect,
                            status_code=status_code,
                            error=error_str,
                            attributes={"tool_name": tool_name, "is_side_effect": side_effect},
                            start_time=start_time,
                            end_time=end_time,
                            duration_ms=duration_ms
                        )

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

def record_state_transition(trace_id: str, node_name: str, state_before: Dict[str, Any], state_after: Dict[str, Any], duration_ms: float = 0.0):
    """Record a LangGraph state graph transition span."""
    span_id = generate_span_id()
    now = datetime.utcnow()
    with SessionLocal() as db:
        crud.add_span(
            db=db,
            span_id=span_id,
            trace_id=trace_id,
            name=f"node:{node_name}",
            kind=SpanKind.STATE_TRANSITION,
            inputs={"state_before": state_before},
            outputs={"state_after": state_after},
            status_code="OK",
            attributes={"node_name": node_name},
            start_time=now,
            end_time=now,
            duration_ms=duration_ms
        )

def record_llm_call(
    trace_id: str,
    prompt: Any,
    response: Any,
    model: str = "open-model",
    temperature: float = 0.7,
    token_usage: Optional[Dict[str, int]] = None,
    duration_ms: float = 0.0,
    error: Optional[str] = None
):
    """Record an LLM reasoning step span."""
    span_id = generate_span_id()
    now = datetime.utcnow()
    with SessionLocal() as db:
        crud.add_span(
            db=db,
            span_id=span_id,
            trace_id=trace_id,
            name=f"llm:{model}",
            kind=SpanKind.LLM_CALL,
            inputs={"prompt": prompt, "model": model, "temperature": temperature},
            outputs={"response": response} if not error else {},
            status_code="ERROR" if error else "OK",
            error=error,
            attributes={"model": model, "temperature": temperature, "token_usage": token_usage or {}},
            start_time=now,
            end_time=now,
            duration_ms=duration_ms
        )
