import json
import logging
from typing import Dict, Any, Optional
import httpx
from agenttrace.config import settings
from agenttrace.models import FailureBucket

logger = logging.getLogger("agenttrace.llm_analyzer")

ANALYSIS_SYSTEM_PROMPT = """You are AgentTrace Root Cause Analyzer.
Your task is to analyze a failed AI Agent run that has been replayed multiple times in a deterministic sandbox.

Given:
1. Replay Consistency Data (N replays, dominant outcome, consistency ratio)
2. Divergence Step & Evidence Span
3. Tool Call History and Context

You must produce a precise diagnosis JSON with:
- "failure_bucket": One of ["DETERMINISTIC_BUG", "NON_DETERMINISTIC", "MODEL_DECISION_FAILURE", "TOOL_DATA_AMBIGUITY", "MISSING_CONTEXT_FAILURE", "ENVIRONMENT_ISSUE"]
- "explanation": Clear, human-readable paragraph explaining exactly why the agent failed and what happened.
- "evidence_span": The exact step or tool call that triggered the failure cascade.
- "remediation": Concrete fix recommendation (prompt tweak, tool schema update, context enrichment, retry logic, or guardrail).
- "confidence_score": Float between 0.0 and 1.0.

Respond strictly in valid JSON format with no markdown wrappers.
"""

def generate_heuristic_diagnosis(
    failure_bucket: FailureBucket,
    consistency_data: Dict[str, Any],
    divergence_info: Dict[str, Any],
    trace_error: Optional[str] = None
) -> Dict[str, Any]:
    """Fallback high-precision diagnostic synthesizer when external LLM is not called."""
    consistency_score = consistency_data.get("consistency_score", 1.0)
    step_name = divergence_info.get("step_name", "unknown_step")
    evidence = divergence_info.get("evidence", {})
    reason = divergence_info.get("reason", "")
    
    if consistency_score < 0.60:
        bucket = FailureBucket.NON_DETERMINISTIC
        explanation = (
            f"Non-deterministic execution detected across {consistency_data.get('total_runs', 10)} replays. "
            f"The agent produced varying tool calls and outcomes with a low consistency score of {consistency_score:.0%}. "
            "This flakiness is commonly caused by high temperature sampling, ambiguous prompt branching, or race conditions."
        )
        remediation = "Reduce model temperature (e.g., to 0.0 or 0.2), enforce structured output schemas (JSON mode), and eliminate ambiguous prompt instructions."
        confidence = consistency_score
    elif failure_bucket == FailureBucket.MODEL_DECISION_FAILURE:
        bucket = FailureBucket.MODEL_DECISION_FAILURE
        explanation = (
            f"Deterministic model decision failure detected at step '{step_name}'. "
            f"Across {consistency_data.get('total_runs', 10)} replays against identical recorded inputs, "
            f"the model consistently picked an incorrect or policy-violating action ({reason}). "
            "The tool outputs and inputs were valid, indicating the error originated in model reasoning."
        )
        remediation = f"Add explicit guardrails or system prompt constraints around '{step_name}' to validate tool input arguments before execution."
        confidence = max(0.85, consistency_score)
    elif failure_bucket == FailureBucket.TOOL_DATA_AMBIGUITY:
        bucket = FailureBucket.TOOL_DATA_AMBIGUITY
        explanation = (
            f"Tool/data ambiguity failure identified at '{step_name}'. "
            f"The tool returned data that downstream agent reasoning failed to interpret correctly ({reason}). "
            "The model followed the tool's returned state, but the lack of a standardized status schema caused the agent to crash or halt."
        )
        remediation = f"Standardize return schema of '{step_name}' tool. Provide explicit status enums in tool docstrings so the agent has deterministic guidance."
        confidence = max(0.88, consistency_score)
    elif failure_bucket == FailureBucket.MISSING_CONTEXT_FAILURE:
        bucket = FailureBucket.MISSING_CONTEXT_FAILURE
        explanation = (
            f"Missing context failure. The user's input referenced conversation history or prior state, "
            "but the agent was invoked without the necessary context in its initial state. "
            "Replaying against identical state consistently reproduced this context starvation."
        )
        remediation = "Ensure session history and conversation memory are injected into the agent state graph before executing user requests."
        confidence = max(0.90, consistency_score)
    elif failure_bucket == FailureBucket.ENVIRONMENT_ISSUE:
        bucket = FailureBucket.ENVIRONMENT_ISSUE
        explanation = (
            f"Environment/infrastructure failure at step '{step_name}'. "
            f"The agent encountered an infrastructure error: {trace_error or reason}."
        )
        remediation = "Implement exponential backoff retry policies on the external tool client or verify network timeouts."
        confidence = max(0.92, consistency_score)
    else:
        bucket = FailureBucket.DETERMINISTIC_BUG
        explanation = f"Deterministic failure reproduced across all replays at '{step_name}'. Details: {reason}."
        remediation = "Inspect the evidence span and review agent node transition logic."
        confidence = consistency_score

    return {
        "failure_bucket": bucket.value if hasattr(bucket, "value") else str(bucket),
        "explanation": explanation,
        "evidence_span": evidence,
        "remediation": remediation,
        "confidence_score": confidence
    }

async def analyze_failure_with_llm(
    failure_bucket: FailureBucket,
    consistency_data: Dict[str, Any],
    divergence_info: Dict[str, Any],
    trace_spans_summary: Dict[str, Any],
    trace_error: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calls configured Open Model (Qwen/Llama via Ollama or OpenAI-compatible endpoint)
    or falls back to high-precision heuristic synthesizer.
    """
    if settings.LLM_PROVIDER in ["ollama", "openai"] and settings.LLM_API_BASE:
        try:
            prompt_content = {
                "preliminary_bucket": failure_bucket.value if hasattr(failure_bucket, "value") else str(failure_bucket),
                "replay_consistency": consistency_data,
                "divergence": divergence_info,
                "spans_summary": trace_spans_summary,
                "trace_error": trace_error
            }

            headers = {"Content-Type": "application/json"}
            if settings.LLM_API_KEY:
                headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

            payload = {
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(prompt_content, indent=2)}
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"}
            }

            url = f"{settings.LLM_API_BASE.rstrip('/')}/chat/completions"
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return parsed
        except Exception as e:
            logger.warning(f"Failed to query LLM provider ({e}), falling back to heuristic diagnosis.")

    # Return intelligent heuristic diagnosis
    return generate_heuristic_diagnosis(
        failure_bucket=failure_bucket,
        consistency_data=consistency_data,
        divergence_info=divergence_info,
        trace_error=trace_error
    )
