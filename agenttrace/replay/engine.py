import time
import copy
import traceback
from typing import Dict, Any, List, Optional, Callable
from sqlalchemy.orm import Session

from agenttrace.config import settings
from agenttrace.models import (
    Incident, IncidentStatus, ReplayJob, ReplayRun, Trace, SpanKind
)
from agenttrace.replay.mock_context import ReplaySandbox, extract_mock_fixtures_from_trace
from agenttrace.replay.consistency import compute_run_signature, analyze_replays_consistency
from agenttrace.analysis.classifier import classify_incident_investigation
from agenttrace.db import SessionLocal, crud

# Registry mapping agent_name -> runnable function/graph
_AGENT_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Any]] = {}

def register_agent_runner(agent_name: str, runner: Callable[[Dict[str, Any]], Any]):
    """Registers an agent invocation function or graph runner for deterministic replays."""
    _AGENT_REGISTRY[agent_name] = runner

def get_agent_runner(agent_name: str) -> Optional[Callable[[Dict[str, Any]], Any]]:
    return _AGENT_REGISTRY.get(agent_name)

class ReplayEngine:
    """
    Executes N replays of a failed agent run against recorded mock fixtures,
    evaluates determinism vs flakiness, and triggers classification.
    """
    def __init__(self, db: Optional[Session] = None):
        self.db = db

    async def execute_investigation(
        self,
        incident_id: int,
        n_replays: int = 10,
        custom_runner: Optional[Callable[[Dict[str, Any]], Any]] = None
    ) -> Incident:
        db = self.db or SessionLocal()
        should_close = (self.db is None)
        
        try:
            incident = crud.get_incident(db, incident_id)
            if not incident:
                raise ValueError(f"Incident {incident_id} not found")

            incident.status = IncidentStatus.REPLAYING
            db.commit()

            trace = incident.trace
            initial_inputs = copy.deepcopy(trace.initial_inputs or {})
            mock_map = extract_mock_fixtures_from_trace(trace)

            # Look up agent runner
            runner = custom_runner or get_agent_runner(incident.agent_name)
            
            # Create ReplayJob record
            job = crud.create_replay_job(db, incident_id=incident.id, n_replays=n_replays)
            
            runs_collected: List[Dict[str, Any]] = []

            for run_idx in range(1, n_replays + 1):
                t0 = time.perf_counter()
                status = "SUCCESS"
                err_str = None
                output = None
                exec_log = []

                try:
                    with ReplaySandbox(mock_map) as sandbox:
                        if runner:
                            # Re-execute agent within sandbox
                            output = runner(copy.deepcopy(initial_inputs))
                        else:
                            # Default simulation playback if runner not registered
                            output = self._simulate_step_playback(trace, sandbox)
                            
                        exec_log = sandbox.execution_log
                        
                        # Check if agent indicated logical error
                        if isinstance(output, dict) and (output.get("error") or output.get("status") in ["failed", "failure", "error"]):
                            status = "FAILURE"
                            err_str = output.get("error") or f"Reached status: {output.get('status')}"

                except Exception as e:
                    status = "FAILURE"
                    err_str = str(e)
                    exec_log = sandbox.execution_log if 'sandbox' in locals() else []
                finally:
                    duration_ms = (time.perf_counter() - t0) * 1000.0

                signature = compute_run_signature(status, exec_log, err_str)
                
                # Check divergence against original trace
                orig_status = "FAILURE" if trace.status.value == "FAILURE" else "SUCCESS"
                divergence_detected = (status != orig_status)

                # Record replay run
                crud.add_replay_run(
                    db=db,
                    replay_job_id=job.id,
                    run_index=run_idx,
                    status=status,
                    outcome_signature=signature,
                    divergence_detected=divergence_detected,
                    divergence_step=exec_log[-1].get("tool") if exec_log else None,
                    steps_count=len(exec_log),
                    output=output,
                    error=err_str,
                    execution_steps=exec_log,
                    duration_ms=duration_ms
                )

                runs_collected.append({
                    "run_index": run_idx,
                    "status": status,
                    "outcome_signature": signature,
                    "output": output,
                    "error": err_str,
                    "execution_steps": exec_log
                })

            # Complete job
            consistency_stats = analyze_replays_consistency(runs_collected)
            crud.complete_replay_job(
                db=db,
                job_id=job.id,
                status="COMPLETED",
                dominant_outcome=consistency_stats["dominant_outcome"],
                consistency_ratio=consistency_stats["consistency_score"]
            )

            # Trigger Classification & Escalation
            updated_incident = await classify_incident_investigation(
                db=db,
                incident_id=incident.id,
                runs_data=runs_collected
            )
            return updated_incident

        finally:
            if should_close:
                db.close()

    def _simulate_step_playback(self, trace: Trace, sandbox: ReplaySandbox) -> Dict[str, Any]:
        """Playback recorded spans through the sandbox when runner is executed in headless mode."""
        for span in trace.spans:
            if span.kind == SpanKind.TOOL_CALL:
                # Read through sandbox interceptor
                mock_res = sandbox.mock_map.get(span.name, span.outputs.get("result", span.outputs))
                sandbox.execution_log.append({
                    "tool": span.name,
                    "inputs": span.inputs,
                    "mock_response": mock_res,
                    "is_side_effect": span.is_side_effect
                })
        if trace.status.value == "FAILURE":
            raise RuntimeError(trace.error_message or "Playback reproduced original failure")
        return trace.final_output or {"status": "completed"}
