import sys
import asyncio
import uvicorn
from agenttrace.config import settings
from agenttrace.db import init_db, SessionLocal, crud
from agenttrace.regression import RegressionSuiteRunner

def main():
    args = sys.argv[1:]
    command = args[0] if args else "serve"

    if command == "serve":
        port = int(args[1]) if len(args) > 1 else 8000
        print(f"\n[AgentTrace] Starting server on http://127.0.0.1:{port}")
        print(f"[AgentTrace] Dashboard: http://127.0.0.1:{port}")
        print(f"[AgentTrace] OpenAPI docs: http://127.0.0.1:{port}/docs\n")
        uvicorn.run("agenttrace.api.server:app", host="0.0.0.0", port=port, reload=False)

    elif command == "seed":
        from examples.seed_demo_data import seed_and_investigate
        print("[AgentTrace] Seeding demo agent runs and running investigations...")
        asyncio.run(seed_and_investigate())

    elif command == "test-regressions":
        init_db()
        try:
            import examples.customer_support_agent
        except ImportError:
            pass
        print("[AgentTrace] Running CI Regression Suite...")
        runner = RegressionSuiteRunner()
        results = runner.run_all()
        print(f"\nExecuted {len(results)} regression fixtures:")
        for r in results:
            status = "[PASS]" if r["passed"] else "[FAIL]"
            print(f"  {status} [{r['agent_name']}] {r['fixture_name']} ({r['duration_ms']:.1f}ms): {r['details']}")

    elif command == "stats":
        init_db()
        with SessionLocal() as db:
            stats = crud.get_stats(db)
            print("\n" + "="*50)
            print("         AGENTTRACE SYSTEM METRICS")
            print("="*50)
            print(f" Total Traces Captured:    {stats['total_traces']}")
            print(f" Total Failures Flagged:   {stats['total_failures']}")
            print(f" Total Incidents:          {stats['total_incidents']}")
            print(f" Deterministic Bugs:       {stats['deterministic_count']}")
            print(f" Non-Deterministic Flakes: {stats['non_deterministic_count']}")
            print(f" Active Regressions:       {stats['active_regressions']}")
            print("\n Failure Buckets:")
            for bucket, count in stats["failure_buckets"].items():
                print(f"   - {bucket}: {count}")
            print("="*50 + "\n")

    else:
        print(f"Unknown command: '{command}'")
        print("Usage: agenttrace [serve | seed | test-regressions | stats]")

if __name__ == "__main__":
    main()
