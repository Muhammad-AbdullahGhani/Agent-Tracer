import random
from typing import Dict, Any, TypedDict, Optional
from langgraph.graph import StateGraph, END

from agenttrace.tracer import trace_tool, trace_node, AgentTraceGraphRunner
from agenttrace.replay import register_agent_runner

# Define Agent State
class AgentState(TypedDict):
    customer_id: str
    order_id: str
    message: str
    order_data: Optional[Dict[str, Any]]
    action_decision: Optional[str]
    refund_amount: Optional[float]
    policy_breach: Optional[str]
    error: Optional[str]
    status: Optional[str]
    temperature_flake_seed: Optional[float]

# Tools with @trace_tool
@trace_tool(name="get_order_details", is_side_effect=False)
def get_order_details(order_id: str) -> Dict[str, Any]:
    """Pure read-only tool to retrieve order details."""
    orders_db = {
        "ord_101": {"order_id": "ord_101", "amount": 25.0, "status": "delivered", "days_ago": 5},
        "ord_500_breach": {"order_id": "ord_500_breach", "amount": 450.0, "status": "delivered", "days_ago": 10},
        "ord_ambiguous_data": {"order_id": "ord_ambiguous_data", "amount": 40.0, "status": "pending_chargeback", "days_ago": 3},
        "ord_flaky": {"order_id": "ord_flaky", "amount": 35.0, "status": "delivered", "days_ago": 12},
    }
    return orders_db.get(order_id, {"order_id": order_id, "amount": 0.0, "status": "unknown"})

@trace_tool(name="process_refund", is_side_effect=True)
def process_refund(order_id: str, amount: float) -> Dict[str, Any]:
    """Side-effect tool: issues actual money refund. MUST BE MOCKED DURING REPLAY."""
    if amount > 50.0:
        raise ValueError(f"CRITICAL POLICY BREACH: Refund amount ${amount:.2f} exceeds auto-approval limit ($50.00 max).")
    return {"status": "REFUNDED", "order_id": order_id, "amount": amount, "txn_id": f"tx_{order_id}"}

@trace_tool(name="notify_human_agent", is_side_effect=True)
def notify_human_agent(order_id: str, reason: str) -> Dict[str, Any]:
    """Side-effect tool: notifies human support agent."""
    return {"status": "ESCALATED", "order_id": order_id, "reason": reason}

# Graph Node Definitions with @trace_node
@trace_node("triage_request")
def triage_node(state: AgentState) -> AgentState:
    msg = state.get("message", "").lower()
    
    # Check for missing context
    if "previous ticket" in msg or "as discussed" in msg:
        if not state.get("order_data") and not state.get("customer_id"):
            state["error"] = "Missing Context: User referenced previous ticket but no conversation history exists."
            state["status"] = "failed"
            return state

    state["status"] = "triaged"
    return state

@trace_node("fetch_order")
def fetch_order_node(state: AgentState) -> AgentState:
    if state.get("status") == "failed":
        return state
        
    order_id = state.get("order_id", "")
    order_data = get_order_details(order_id)
    state["order_data"] = order_data
    return state

@trace_node("evaluate_policy")
def evaluate_policy_node(state: AgentState) -> AgentState:
    if state.get("status") == "failed":
        return state
        
    order = state.get("order_data", {})
    order_status = order.get("status", "")
    amount = float(order.get("amount", 0.0))
    
    # Tool Data Ambiguity scenario: pending_chargeback trips up agent
    if order_status == "pending_chargeback":
        state["error"] = "Tool Ambiguity: Received unhandled order status 'pending_chargeback'. Cannot determine refund liability."
        state["status"] = "failed"
        return state

    # Flaky scenario (non-deterministic branching)
    if state.get("force_initial_fail"):
        state["action_decision"] = "deny"
        state["status"] = "failed"
        state["error"] = "Agent flaked: randomly rejected valid refund due to prompt ambiguity"
        return state

    if state.get("temperature_flake_seed") is not None:
        # Simulate LLM temperature variance
        dice_roll = random.random()
        if dice_roll < 0.50:
            state["action_decision"] = "deny"
            state["status"] = "failed"
            state["error"] = "Agent flaked: randomly rejected valid refund due to prompt ambiguity"
            return state
        else:
            state["action_decision"] = "refund"
            state["refund_amount"] = amount
            return state

    # Buggy Model Decision scenario: Model attempts refund > $50 without routing to human
    if amount > 50.0:
        # In a buggy agent, model hallucinates policy override instead of escalating
        state["action_decision"] = "refund"
        state["refund_amount"] = amount
        return state

    # Normal valid refund
    state["action_decision"] = "refund"
    state["refund_amount"] = amount
    return state

@trace_node("execute_action")
def execute_action_node(state: AgentState) -> AgentState:
    if state.get("status") in ["failed", "rejected"]:
        return state
        
    decision = state.get("action_decision")
    if decision == "refund":
        amt = state.get("refund_amount", 0.0)
        try:
            res = process_refund(state["order_id"], amt)
            state["status"] = "completed"
            state["action_result"] = res
        except Exception as e:
            state["error"] = str(e)
            state["status"] = "failed"
            state["policy_breach"] = str(e)
    elif decision == "escalate":
        res = notify_human_agent(state["order_id"], "Exceeds automated limits")
        state["status"] = "escalated"
        state["action_result"] = res
    else:
        state["status"] = "noop"
        
    return state

# Compile LangGraph
def build_customer_support_graph():
    builder = StateGraph(AgentState)
    builder.add_node("triage", triage_node)
    builder.add_node("fetch_order", fetch_order_node)
    builder.add_node("evaluate_policy", evaluate_policy_node)
    builder.add_node("execute_action", execute_action_node)

    builder.set_entry_point("triage")
    builder.add_edge("triage", "fetch_order")
    builder.add_edge("fetch_order", "evaluate_policy")
    builder.add_edge("evaluate_policy", "execute_action")
    builder.add_edge("execute_action", END)

    return builder.compile()

# Wrapped Runner
graph_instance = build_customer_support_graph()
support_agent_runner = AgentTraceGraphRunner(
    compiled_graph=graph_instance,
    agent_name="customer_support_refund_agent",
    agent_version="1.2.0"
)

# Register runner with ReplayEngine
register_agent_runner("customer_support_refund_agent", lambda inputs: support_agent_runner.invoke(inputs))
