import hashlib
import json
from collections import Counter
from typing import List, Dict, Any, Tuple

def compute_run_signature(status: str, execution_steps: List[Dict[str, Any]], error: str = None) -> str:
    """
    Computes a deterministic fingerprint of an execution run based on:
    - Final status (SUCCESS, FAILURE, ERROR)
    - Sequence of tools invoked
    - Error message category
    """
    tools_invoked = [step.get("tool", "") for step in execution_steps if "tool" in step]
    error_summary = (error or "").strip()[:60]
    
    signature_raw = f"{status}|{'->'.join(tools_invoked)}|{error_summary}"
    # Return a clean human-readable slug + short hash
    slug = f"{status}_{len(tools_invoked)}tools"
    h = hashlib.md5(signature_raw.encode("utf-8")).hexdigest()[:6]
    return f"{slug}_{h}"

def analyze_replays_consistency(runs_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyzes consistency across N replays.
    Returns:
    - total_runs: N
    - dominant_outcome: string signature
    - dominant_outcome_count: count
    - consistency_score: dominant_outcome_count / N (0.0 to 1.0)
    - outcome_distribution: {signature: count}
    - is_deterministic: bool (True if consistency_score == 1.0)
    - is_mixed_majority: bool (True if 0.6 <= consistency_score < 1.0)
    - is_non_deterministic: bool (True if consistency_score < 0.6)
    """
    n = len(runs_data)
    if n == 0:
        return {
            "total_runs": 0,
            "dominant_outcome": "UNKNOWN",
            "dominant_outcome_count": 0,
            "consistency_score": 0.0,
            "outcome_distribution": {},
            "is_deterministic": False,
            "is_mixed_majority": False,
            "is_non_deterministic": True
        }
        
    signatures = [r["outcome_signature"] for r in runs_data]
    counter = Counter(signatures)
    dominant_outcome, dominant_count = counter.most_common(1)[0]
    
    consistency_score = round(dominant_count / n, 4)
    
    is_deterministic = (dominant_count == n)
    is_mixed_majority = (not is_deterministic) and (consistency_score >= 0.60)
    is_non_deterministic = consistency_score < 0.60

    return {
        "total_runs": n,
        "dominant_outcome": dominant_outcome,
        "dominant_outcome_count": dominant_count,
        "consistency_score": consistency_score,
        "outcome_distribution": dict(counter),
        "is_deterministic": is_deterministic,
        "is_mixed_majority": is_mixed_majority,
        "is_non_deterministic": is_non_deterministic
    }
