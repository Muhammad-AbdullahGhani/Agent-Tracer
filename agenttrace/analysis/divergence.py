from typing import List, Dict, Any, Optional
from agenttrace.models import Trace, Span, SpanKind, FailureBucket

def locate_divergence_span(trace: Trace, baseline: Optional[Trace] = None) -> Dict[str, Any]:
    """
    Analyzes the spans of a failed trace to locate the exact divergence point.
    Delineates between:
    1. Environment / Infra issues (timeouts, network, 5xx)
    2. Missing context failure (input referenced data missing from prompt/state)
    3. Model decision failure (policy breach, unauthorized action, model picking wrong action given valid inputs)
    4. Tool / Data ambiguity (tool returned error, malformed or empty data, unexpected/ambiguous status)
    """
    spans: List[Span] = trace.spans or []
    initial_inputs = trace.initial_inputs or {}
    trace_err = (trace.error_message or "").lower()

    # Check 1: Environment Issue (Infra, Timeout, Connection Reset)
    for span in spans:
        err = (span.error or "").lower()
        if span.status_code == "ERROR" and any(keyword in err for keyword in ["timeout", "connection refused", "503", "502", "network", "reset by peer"]):
            return {
                "bucket": FailureBucket.ENVIRONMENT_ISSUE,
                "span_id": span.span_id,
                "step_name": span.name,
                "reason": f"Infrastructure / Environment error encountered during {span.name}: {span.error}",
                "evidence": {
                    "span_id": span.span_id,
                    "kind": span.kind.value if hasattr(span.kind, "value") else str(span.kind),
                    "inputs": span.inputs,
                    "outputs": span.outputs,
                    "error": span.error
                }
            }

    # Check 2: Missing Context Failure
    # Did the user request something referencing previous conversation or missing fields?
    user_prompt = str(initial_inputs.get("prompt", "") or initial_inputs.get("message", "") or "").lower()
    if any(phrase in user_prompt for phrase in ["as discussed earlier", "previous ticket", "last order", "as mentioned", "prior chat"]):
        has_history = bool(initial_inputs.get("history") or initial_inputs.get("context") or initial_inputs.get("prior_ticket"))
        if not has_history:
            first_llm_or_node = next((s for s in spans if s.kind in [SpanKind.LLM_CALL, SpanKind.STATE_TRANSITION]), spans[0] if spans else None)
            return {
                "bucket": FailureBucket.MISSING_CONTEXT_FAILURE,
                "span_id": first_llm_or_node.span_id if first_llm_or_node else "span_ctx_0",
                "step_name": first_llm_or_node.name if first_llm_or_node else "initial_context",
                "reason": "User input referenced prior context ('as discussed earlier / previous ticket') but no prior history was provided in state.",
                "evidence": {
                    "span_id": first_llm_or_node.span_id if first_llm_or_node else "span_ctx_0",
                    "initial_inputs": initial_inputs,
                    "missing_keys": ["history", "prior_ticket_context"]
                }
            }

    # Check 3: Model Decision Failure (Policy Breach / Unauthorized Action / Invalid Model Output)
    for span in spans:
        err = (span.error or "").lower()
        if any(keyword in err for keyword in ["policy breach", "policy violation", "unauthorized", "exceeds auto-approval", "hallucin"]):
            return {
                "bucket": FailureBucket.MODEL_DECISION_FAILURE,
                "span_id": span.span_id,
                "step_name": span.name,
                "reason": f"Model invoked '{span.name}' breaching policy: {span.error}",
                "evidence": {
                    "span_id": span.span_id,
                    "kind": span.kind.value if hasattr(span.kind, "value") else str(span.kind),
                    "inputs": span.inputs,
                    "outputs": span.outputs,
                    "error": span.error
                }
            }
        if span.kind == SpanKind.TOOL_CALL and span.is_side_effect:
            args = span.inputs or {}
            amount = args.get("amount") or args.get("refund_amount")
            if amount is not None:
                try:
                    val = float(amount)
                    if val > 50.0:
                        return {
                            "bucket": FailureBucket.MODEL_DECISION_FAILURE,
                            "span_id": span.span_id,
                            "step_name": span.name,
                            "reason": f"Model invoked '{span.name}' with amount ${val:.2f}, violating policy threshold ($50.00 max).",
                            "evidence": {
                                "span_id": span.span_id,
                                "kind": span.kind.value if hasattr(span.kind, "value") else str(span.kind),
                                "tool": span.name,
                                "inputs": span.inputs,
                                "outputs": span.outputs
                            }
                        }
                except (ValueError, TypeError):
                    pass

    # Check if trace-level error indicates policy breach
    if any(keyword in trace_err for keyword in ["policy breach", "policy violation", "unauthorized", "exceeds auto-approval"]):
        last_span = spans[-1] if spans else None
        return {
            "bucket": FailureBucket.MODEL_DECISION_FAILURE,
            "span_id": last_span.span_id if last_span else "span_policy",
            "step_name": last_span.name if last_span else "policy_check",
            "reason": f"Model decision triggered policy violation: {trace.error_message}",
            "evidence": {
                "span_id": last_span.span_id if last_span else "span_policy",
                "inputs": last_span.inputs if last_span else {},
                "outputs": last_span.outputs if last_span else {},
                "error": trace.error_message
            }
        }

    # Check 4: Tool / Data Ambiguity
    for span in spans:
        if span.kind == SpanKind.TOOL_CALL:
            output = span.outputs.get("result", span.outputs) if span.outputs else {}
            if isinstance(output, dict):
                status_val = str(output.get("status", "")).lower()
                if "ambiguous" in status_val or "pending_chargeback" in status_val or "disputed" in status_val:
                    return {
                        "bucket": FailureBucket.TOOL_DATA_AMBIGUITY,
                        "span_id": span.span_id,
                        "step_name": span.name,
                        "reason": f"Tool '{span.name}' returned ambiguous state '{status_val}' which misled downstream agent reasoning.",
                        "evidence": {
                            "span_id": span.span_id,
                            "kind": span.kind.value if hasattr(span.kind, "value") else str(span.kind),
                            "tool": span.name,
                            "inputs": span.inputs,
                            "outputs": span.outputs
                        }
                    }
            if span.status_code == "ERROR" or (isinstance(output, dict) and output.get("error")):
                return {
                    "bucket": FailureBucket.TOOL_DATA_AMBIGUITY,
                    "span_id": span.span_id,
                    "step_name": span.name,
                    "reason": f"Tool '{span.name}' returned error or malformed payload.",
                    "evidence": {
                        "span_id": span.span_id,
                        "kind": span.kind.value if hasattr(span.kind, "value") else str(span.kind),
                        "tool": span.name,
                        "inputs": span.inputs,
                        "outputs": span.outputs,
                        "error": span.error or (output.get("error") if isinstance(output, dict) else None)
                    }
                }

    # Default fallback: last executed step before trace failed
    last_span = spans[-1] if spans else None
    return {
        "bucket": FailureBucket.MODEL_DECISION_FAILURE,
        "span_id": last_span.span_id if last_span else "unknown_span",
        "step_name": last_span.name if last_span else "end_of_trace",
        "reason": f"Agent reached terminal failure at step '{last_span.name if last_span else 'unknown'}'. Error: {trace.error_message}",
        "evidence": {
            "span_id": last_span.span_id if last_span else "unknown_span",
            "inputs": last_span.inputs if last_span else {},
            "outputs": last_span.outputs if last_span else {},
            "error": trace.error_message
        }
    }
