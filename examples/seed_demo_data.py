import asyncio
from agenttrace.db import init_db, SessionLocal, crud
from agenttrace.models import TraceStatus, IncidentStatus
from agenttrace.replay import ReplayEngine
from examples.customer_support_agent import support_agent_runner

async def seed_and_investigate():
    init_db()
    print("AgentTrace DB initialized.")

    # 1. Healthy Baseline Run ($25 standard refund)
    print("\n[1/5] Executing Healthy Baseline run...")
    healthy_inputs = {
        "customer_id": "cust_1",
        "order_id": "ord_101",
        "message": "I would like a return for order ord_101"
    }
    out_healthy = support_agent_runner.invoke(healthy_inputs)
    print(" -> Healthy Baseline completed successfully.")

    # 2. Deterministic Bug: Model Decision Failure (Refund > $50 policy breach)
    print("\n[2/5] Executing Model Decision Failure scenario ($450 refund breach)...")
    model_fail_inputs = {
        "customer_id": "cust_2",
        "order_id": "ord_500_breach",
        "message": "Please refund order ord_500_breach immediately"
    }
    out_model_fail = support_agent_runner.invoke(model_fail_inputs)
    print(f" -> Execution completed with error: {out_model_fail.get('error')}")

    # 3. Deterministic Bug: Tool / Data Ambiguity ('pending_chargeback' unexpected status)
    print("\n[3/5] Executing Tool Data Ambiguity scenario ('pending_chargeback')...")
    tool_fail_inputs = {
        "customer_id": "cust_3",
        "order_id": "ord_ambiguous_data",
        "message": "Refund requested for ord_ambiguous_data"
    }
    out_tool_fail = support_agent_runner.invoke(tool_fail_inputs)
    print(f" -> Execution completed with error: {out_tool_fail.get('error')}")

    # 4. Non-Deterministic Flake (High-temperature stochastic variance)
    print("\n[4/5] Executing Non-Deterministic Flake scenario...")
    flaky_inputs = {
        "customer_id": "cust_4",
        "order_id": "ord_flaky",
        "message": "Could you check my order ord_flaky and refund shipping?",
        "temperature_flake_seed": 0.85
    }
    # Loop or simulate initial run that flagged failure
    out_flaky = support_agent_runner.invoke(flaky_inputs)
    # If the first attempt randomly passed, force one that failed so we have a queued incident to investigate
    if out_flaky.get("status") != "failed":
        # Mark as failed trace for replay investigation
        flaky_inputs["force_initial_fail"] = True
        support_agent_runner.invoke(flaky_inputs)
    print(" -> Flaky run executed and queued.")

    # 5. Missing Context Failure
    print("\n[5/5] Executing Missing Context Failure scenario...")
    missing_ctx_inputs = {
        "customer_id": "",
        "order_id": "",
        "message": "As discussed earlier in my previous ticket, please refund me."
    }
    support_agent_runner.invoke(missing_ctx_inputs)
    print(" -> Missing context run executed.")

    # Now investigate queued incidents!
    print("\n" + "="*60)
    print("AGENTTRACE DETERMINISTIC REPLAY & CLASSIFICATION ENGINE")
    print("="*60)

    replay_engine = ReplayEngine()
    with SessionLocal() as db:
        incidents = crud.get_incidents(db, status=IncidentStatus.QUEUED)
        print(f"Found {len(incidents)} queued incidents for replay investigation.\n")

        for inc in incidents:
            print(f"-> Investigating Incident #{inc.id} (Agent: {inc.agent_name})...")
            # Run 10 replays against recorded mock inputs
            updated_inc = await replay_engine.execute_investigation(
                incident_id=inc.id,
                n_replays=10
            )
            print(f"   Bucket:      {updated_inc.failure_bucket.value}")
            print(f"   Consistency: {updated_inc.consistency_score:.0%} ({updated_inc.dominant_outcome})")
            print(f"   Confidence:  {updated_inc.confidence_score:.0%}")
            print(f"   Status:      {updated_inc.status.value}")
            print(f"   Explanation: {updated_inc.explanation[:110]}...")
            print(f"   Remediation: {updated_inc.remediation[:110]}...\n")

    print("Seeding and replay investigations completed successfully!")

if __name__ == "__main__":
    asyncio.run(seed_and_investigate())
