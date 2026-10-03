import React, { useState, useMemo } from 'react';

// Initial forensic dataset of 18 realistic AI agent failures
export const INITIAL_INCIDENTS = [
  {
    id: "inc_1842",
    agentName: "refund_agent",
    version: "v2.4.1",
    commit: "f9a2b0e",
    env: "production / us-east-1",
    timestamp: "2026-10-01 14:02:18 UTC",
    title: "Wrong transaction selected for refund after ambiguous status code",
    status: "Needs review",
    failureBucket: "Tool/data ambiguity",
    confidenceScore: 87,
    dominantCount: 8,
    replaysTotal: 10,
    dominantOutcome: "8/10 replays reproduced identical failure",
    replays: [
      { index: 1, status: "reproduced_failure", latencyMs: 142.1, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 2, status: "reproduced_failure", latencyMs: 139.8, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 3, status: "reproduced_failure", latencyMs: 145.0, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 4, status: "reproduced_failure", latencyMs: 141.2, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 5, status: "divergent_pass",   latencyMs: 131.5, signature: "PASS_safe_halt",             summary: "Model hesitated on disputed status and paused", evidenceSpanRef: "span_tool_tx" },
      { index: 6, status: "reproduced_failure", latencyMs: 144.3, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 7, status: "reproduced_failure", latencyMs: 140.7, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 8, status: "divergent_pass",   latencyMs: 133.0, signature: "PASS_safe_halt",             summary: "Model hesitated on disputed status and paused", evidenceSpanRef: "span_tool_tx" },
      { index: 9, status: "reproduced_failure", latencyMs: 143.9, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
      { index: 10, status: "reproduced_failure", latencyMs: 141.6, signature: "FAIL_tool[get_tx]_err_status", summary: "Interpreted disputed_pending as settled", evidenceSpanRef: "span_eval_refund" },
    ],
    evidenceTrail: [
      {
        id: "span_init",
        name: "state_transition: session_start -> triage",
        timestamp: "14:02:18.012",
        kind: "state_transition",
        isSideEffect: false,
        isOffending: false,
        payload: { user_id: "usr_9921", request: "Refund $142.50 for order #9182 - item never arrived" },
        note: "Initial payload valid; order ID successfully parsed into agent state context."
      },
      {
        id: "span_tool_tx",
        name: "tool_call: get_transaction(order_id='ord_9182')",
        timestamp: "14:02:18.114",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: false,
        payload: {
          order_id: "ord_9182",
          amount: 142.50,
          status: "disputed_pending",
          processor: "stripe_connect",
          ledger_state: "locked"
        },
        note: "Tool executed normally but returned non-standard enum 'disputed_pending'. The tool contract lacks validation for active chargeback hold."
      },
      {
        id: "span_eval_refund",
        name: "model_decision: evaluate_refund_policy",
        timestamp: "14:02:18.342",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Model hallucinated status equivalence: treated 'disputed_pending' as 'settled' instead of halting for chargeback review.",
        payload: {
          prompt_excerpt: "If transaction status is settled or confirmed, proceed to refund. Transaction status: disputed_pending",
          model_reasoning: "The customer order status is disputed_pending, which confirms the charge exists. Proceeding with refund processing.",
          emitted_action: "execute_refund(amount=142.50, txn_id='tx_8819')"
        },
        note: "Offending evidence span. Replayed 10 times against identical recorded mock response: 8 out of 10 times model chose execute_refund without flagging ledger conflict."
      },
      {
        id: "span_side_effect",
        name: "tool_call: execute_refund(amount=142.50, txn_id='tx_8819')",
        timestamp: "14:02:18.502",
        kind: "tool_call",
        isSideEffect: true,
        isOffending: false,
        payload: { status: "MOCKED_IN_SANDBOX", simulated: true, actual_side_effect_prevented: true },
        note: "Safely intercepted in deterministic replay engine. Zero live funds transferred. Recorded response from production trace returned."
      }
    ],
    forensicReport: "During execution, tool get_transaction returned status 'disputed_pending'. The prompt lacked an explicit guardrail distinguishing between settled transactions and payment under active bank dispute. In 8 out of 10 deterministic sandbox replays against identical recorded outputs, the model reasoned that 'disputed_pending' satisfied refund criteria, causing a duplicate payout hazard. Recommended remediation: update tool schema to emit an explicit boolean 'is_refundable: false' and update agent triage node to escalate disputed accounts to human operators."
  },
  {
    id: "inc_1839",
    agentName: "billing_reconciler",
    version: "v1.8.0",
    commit: "3a88cd2",
    env: "production / us-east-1",
    timestamp: "2026-10-01 13:41:05 UTC",
    title: "Exceeded max refund threshold ($450 vs $50 cap) without supervisor approval",
    status: "Confirmed bugs",
    failureBucket: "Model decision failure",
    confidenceScore: 100,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced identical failure",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 164.2 + (i % 3),
      signature: "FAIL_policy_threshold_breach",
      summary: "Emitted execute_refund($450.00) violating hard $50 cap",
      evidenceSpanRef: "span_breach_eval"
    })),
    evidenceTrail: [
      {
        id: "span_load_limits",
        name: "tool_call: get_merchant_policy(merchant_id='merch_41')",
        timestamp: "13:41:05.101",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: false,
        payload: { auto_refund_limit: 50.00, requires_manager_approval: true },
        note: "Policy constraints successfully loaded into prompt memory."
      },
      {
        id: "span_breach_eval",
        name: "model_decision: authorize_disbursement",
        timestamp: "13:41:05.289",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Model ignored policy threshold and chose to disburse $450.00 directly due to conversational customer urgency.",
        payload: {
          requested_amount: 450.00,
          allowed_cap: 50.00,
          model_output: "Customer is VIP tier, overriding auto-refund threshold to issue immediate $450 credit."
        },
        note: "Hard policy breach. Model fabricated an ungrounded 'VIP override' not defined in policy schema."
      }
    ],
    forensicReport: "Model bypassed hard limit of $50.00 auto-approval and executed $450.00 payout based on hallucinated customer tier privilege. All 10 deterministic replays failed identically. Guardrail rule required: enforce deterministic JSON schema validation before side-effect tool execution."
  },
  {
    id: "inc_1835",
    agentName: "support_triage_agent",
    version: "v3.1.0",
    commit: "88c1b29",
    env: "production / eu-west-1",
    timestamp: "2026-10-01 12:15:40 UTC",
    title: "User query references prior chat ticket but memory state was empty",
    status: "Confirmed bugs",
    failureBucket: "Missing context failure",
    confidenceScore: 100,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced identical failure",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 98.4 + (i % 2),
      signature: "FAIL_context_starvation",
      summary: "Agent halted: cannot resolve prior ticket reference",
      evidenceSpanRef: "span_ctx_starvation"
    })),
    evidenceTrail: [
      {
        id: "span_input_msg",
        name: "state_transition: ingress -> parse_intent",
        timestamp: "12:15:40.010",
        kind: "state_transition",
        isSideEffect: false,
        isOffending: false,
        payload: { text: "As discussed in my previous ticket #7712, please release the account block." },
        note: "User query explicitly anchors on external ticket state."
      },
      {
        id: "span_ctx_starvation",
        name: "model_decision: context_resolution",
        timestamp: "12:15:40.180",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Initial state lacked 'ticket_history' and session graph had no retrieval tool for archived tickets.",
        payload: { missing_keys: ["ticket_history", "archived_session_id"], state_keys_present: ["session_id", "user_id"] },
        note: "Context starvation. Agent reached terminal error node with unresolvable state dependency."
      }
    ],
    forensicReport: "10/10 replays deterministically halt on missing conversation state. Session initialization middleware failed to inject previous ticket history into agent working memory."
  },
  {
    id: "inc_1831",
    agentName: "inventory_scheduler",
    version: "v1.2.2",
    commit: "4491de1",
    env: "production / us-east-2",
    timestamp: "2026-10-01 11:28:11 UTC",
    title: "Stochastic branch on shipping warehouse allocation under temp=0.85",
    status: "Flaky",
    failureBucket: "Non-deterministic flake",
    confidenceScore: 40,
    dominantCount: 4,
    replaysTotal: 10,
    dominantOutcome: "Varies run to run (4 reproduced failure, 6 diverged)",
    replays: [
      { index: 1, status: "reproduced_failure", latencyMs: 210.1, signature: "FAIL_wh_east_invalid", summary: "Selected unverified warehouse East-B", evidenceSpanRef: "span_branch_flaky" },
      { index: 2, status: "divergent_pass",   latencyMs: 198.5, signature: "PASS_wh_central",      summary: "Selected correct Central hub", evidenceSpanRef: "span_branch_flaky" },
      { index: 3, status: "reproduced_failure", latencyMs: 205.3, signature: "FAIL_wh_east_invalid", summary: "Selected unverified warehouse East-B", evidenceSpanRef: "span_branch_flaky" },
      { index: 4, status: "divergent_error",  latencyMs: 216.2, signature: "ERR_wh_timeout",       summary: "Standby ping timeout on West-A fallback", evidenceSpanRef: "span_branch_flaky" },
      { index: 5, status: "divergent_pass",   latencyMs: 199.0, signature: "PASS_wh_central",      summary: "Selected correct Central hub", evidenceSpanRef: "span_branch_flaky" },
      { index: 6, status: "reproduced_failure", latencyMs: 208.4, signature: "FAIL_wh_east_invalid", summary: "Selected unverified warehouse East-B", evidenceSpanRef: "span_branch_flaky" },
      { index: 7, status: "divergent_pass",   latencyMs: 202.0, signature: "PASS_wh_central",      summary: "Selected correct Central hub", evidenceSpanRef: "span_branch_flaky" },
      { index: 8, status: "divergent_error",  latencyMs: 214.8, signature: "ERR_wh_unreachable",   summary: "Alternate unverified standby branch East-C", evidenceSpanRef: "span_branch_flaky" },
      { index: 9, status: "reproduced_failure", latencyMs: 207.1, signature: "FAIL_wh_east_invalid", summary: "Selected unverified warehouse East-B", evidenceSpanRef: "span_branch_flaky" },
      { index: 10, status: "divergent_pass",   latencyMs: 200.4, signature: "PASS_wh_central",      summary: "Selected correct Central hub", evidenceSpanRef: "span_branch_flaky" },
    ],
    evidenceTrail: [
      {
        id: "span_wh_query",
        name: "tool_call: list_warehouses(sku='SKU_8912')",
        timestamp: "11:28:11.100",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: false,
        payload: { candidates: ["Central", "East-B (standby)", "West-A"] },
        note: "Candidate list contains ambiguous standby warehouse."
      },
      {
        id: "span_branch_flaky",
        name: "model_decision: route_inventory",
        timestamp: "11:28:11.312",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Model temperature=0.85 generates alternating decisions between Central and unverified East-B standby hub.",
        payload: { temperature: 0.85, seed_variance: "high", distribution: { Central: 6, "East-B": 4 } },
        note: "Stochastic failure. Consistency score is only 40%. Lower temperature to 0.0 to enforce deterministic selection."
      }
    ],
    forensicReport: "High sampling temperature (0.85) caused erratic warehouse selection across replays. The model failed 4 times and passed 6 times on identical inputs. Escalate to human review to evaluate temperature tightening."
  },
  {
    id: "inc_1828",
    agentName: "checkout_orchestrator",
    version: "v2.0.4",
    commit: "91b821a",
    env: "production / us-east-1",
    timestamp: "2026-10-01 10:55:22 UTC",
    title: "Unhandled 429 rate limit during stripe payment intent creation",
    status: "Needs review",
    failureBucket: "Environment issue",
    confidenceScore: 92,
    dominantCount: 9,
    replaysTotal: 10,
    dominantOutcome: "9/10 replays reproduced identical failure",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i === 4 ? "divergent_pass" : "reproduced_failure",
      latencyMs: 512.0 + (i * 8),
      signature: i === 4 ? "PASS_retry_backoff" : "FAIL_http_429_ratelimit",
      summary: i === 4 ? "Rate limit cleared on backoff" : "Upstream HTTP 429 unhandled error",
      evidenceSpanRef: "span_env_http"
    })),
    evidenceTrail: [
      {
        id: "span_env_http",
        name: "tool_call: create_payment_intent(amount=89.00)",
        timestamp: "10:55:22.410",
        kind: "tool_call",
        isSideEffect: true,
        isOffending: true,
        divergenceReason: "Upstream payment provider returned HTTP 429 Too Many Requests with no backoff handler.",
        payload: { http_status: 429, error: "RateLimitError: Rate limit exceeded", retry_after: 2 },
        note: "Environment issue. Replays confirmed downstream graph fails when tool client lacks jittered exponential retry."
      }
    ],
    forensicReport: "External payment gateway rate limit tripped agent execution. In 9 of 10 replays, lack of retry policy caused catastrophic graph abort."
  },
  {
    id: "inc_1824",
    agentName: "sql_analyst_agent",
    version: "v1.4.0",
    commit: "1b088fe",
    env: "staging / us-west-2",
    timestamp: "2026-10-01 09:32:10 UTC",
    title: "Generated SQL with unquoted camelCase identifier failing Postgres dialect",
    status: "Confirmed bugs",
    failureBucket: "Model decision failure",
    confidenceScore: 100,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced identical failure",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 120.5,
      signature: "FAIL_postgres_syntax_case_sensitivity",
      summary: "Generated unquoted userId column reference",
      evidenceSpanRef: "span_sql_divergence"
    })),
    evidenceTrail: [
      {
        id: "span_sql_divergence",
        name: "model_decision: generate_sql_query",
        timestamp: "09:32:10.220",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Model generated SELECT userId FROM users; Postgres folds unquoted identifiers to lowercase userid.",
        payload: { generated_sql: "SELECT userId, totalSpend FROM users WHERE isActive = true;" },
        note: "10/10 replays generate the exact same dialect error. Prompt requires explicit Postgres quoting directive."
      }
    ],
    forensicReport: "PostgreSQL case folding error reproduced in 10/10 replays. The model consistently neglects to wrap camelCase column identifiers in double quotes."
  },
  {
    id: "inc_1820",
    agentName: "email_outreach_agent",
    version: "v2.2.0",
    commit: "55e921d",
    env: "production / us-east-1",
    timestamp: "2026-10-01 08:44:02 UTC",
    title: "Recipient suppression list lookup returned empty string instead of null",
    status: "Resolved",
    failureBucket: "Tool/data ambiguity",
    confidenceScore: 90,
    dominantCount: 9,
    replaysTotal: 10,
    dominantOutcome: "9/10 replays agreed",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i === 2 ? "divergent_pass" : "reproduced_failure",
      latencyMs: 110.0,
      signature: "FAIL_empty_string_suppression",
      summary: "Evaluated '' as truthy suppression reason",
      evidenceSpanRef: "span_suppression_data"
    })),
    evidenceTrail: [
      {
        id: "span_suppression_data",
        name: "tool_call: check_suppression(email='lead@acme.org')",
        timestamp: "08:44:02.110",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Tool returned { is_suppressed: false, reason: '' }. Empty string was evaluated as an active reason.",
        payload: { is_suppressed: false, reason: "" },
        note: "Resolved via PR #412: Normalized empty string reason to null."
      }
    ],
    forensicReport: "Resolved bug: Tool returned an empty string for non-suppressed leads, which python/pydantic validator misparsed as truthy."
  },
  {
    id: "inc_1817",
    agentName: "code_reviewer_agent",
    version: "v1.1.0",
    commit: "7c1209b",
    env: "production / us-west-1",
    timestamp: "2026-10-01 07:19:15 UTC",
    title: "Temperature sampling caused variable AST extraction order",
    status: "Flaky",
    failureBucket: "Non-deterministic flake",
    confidenceScore: 50,
    dominantCount: 5,
    replaysTotal: 10,
    dominantOutcome: "5/10 replays produced distinct order",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i % 2 === 0 ? "reproduced_failure" : "divergent_pass",
      latencyMs: 310.0 + (i * 5),
      signature: i % 2 === 0 ? "FAIL_ast_order_mismatch" : "PASS_canonical_order",
      summary: i % 2 === 0 ? "Emitted warnings in inverted AST sequence" : "Canonical sequence maintained",
      evidenceSpanRef: "span_ast_sampling"
    })),
    evidenceTrail: [
      {
        id: "span_ast_sampling",
        name: "model_decision: prioritize_ast_nodes",
        timestamp: "07:19:15.300",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Non-deterministic sampling causes intermittent test failure on PR linter diffs.",
        payload: { model: "open-model-8b", temperature: 0.7 },
        note: "Set temperature=0.0 and sort findings deterministically by line number."
      }
    ],
    forensicReport: "Flakiness caused by model sorting AST nodes differently across runs with temperature 0.7."
  },
  {
    id: "inc_1812",
    agentName: "claims_adjuster",
    version: "v2.0.1",
    commit: "3d99fa1",
    env: "production / us-east-1",
    timestamp: "2026-10-01 06:12:00 UTC",
    title: "Policy deductible calculation omitted user location state parameter",
    status: "Needs review",
    failureBucket: "Missing context failure",
    confidenceScore: 100,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced identical failure",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 145.0,
      signature: "FAIL_missing_geo_jurisdiction",
      summary: "Cannot compute deductible without state code",
      evidenceSpanRef: "span_jurisdiction_missing"
    })),
    evidenceTrail: [
      {
        id: "span_jurisdiction_missing",
        name: "model_decision: calculate_deductible",
        timestamp: "06:12:00.220",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "State jurisdiction (e.g. CA vs TX) was missing from user profile dictionary.",
        payload: { policy_id: "POL_9918", user_profile: { id: "u_22", state_code: null } },
        note: "Requires context enrichment node before routing to adjuster."
      }
    ],
    forensicReport: "Deductible calculation algorithm mandates geo state code for statutory minimums, but state context was null."
  },
  {
    id: "inc_1808",
    agentName: "notification_dispatcher",
    version: "v1.0.8",
    commit: "10fa89b",
    env: "production / eu-west-1",
    timestamp: "2026-10-01 05:40:11 UTC",
    title: "Upstream webhook gateway timed out after 5000ms",
    status: "Resolved",
    failureBucket: "Environment issue",
    confidenceScore: 95,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced timeout",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 5002.0,
      signature: "FAIL_gateway_timeout_504",
      summary: "Socket timeout at 5000ms threshold",
      evidenceSpanRef: "span_gw_timeout"
    })),
    evidenceTrail: [
      {
        id: "span_gw_timeout",
        name: "tool_call: post_webhook(url='https://hooks.partner.com/events')",
        timestamp: "05:40:11.512",
        kind: "tool_call",
        isSideEffect: true,
        isOffending: true,
        divergenceReason: "Upstream partner gateway had 15 minute outage; response took >5000ms.",
        payload: { timeout_ms: 5000, error: "ConnectTimeout: HTTPSConnectionPool(host='hooks.partner.com', port=443)" },
        note: "Resolved: Partner confirmed infrastructure outage resolved."
      }
    ],
    forensicReport: "Partner webhook gateway outage triggered timeouts. Safely marked resolved as outage was external."
  },
  {
    id: "inc_1804",
    agentName: "kyc_verification_agent",
    version: "v3.0.1",
    commit: "88ab112",
    env: "production / us-east-1",
    timestamp: "2026-10-01 04:22:19 UTC",
    title: "Date format mismatch (DD-MM-YYYY vs ISO8601) in identity document OCR",
    status: "Needs review",
    failureBucket: "Tool/data ambiguity",
    confidenceScore: 88,
    dominantCount: 8,
    replaysTotal: 10,
    dominantOutcome: "8/10 replays failed on date parse",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i < 8 ? "reproduced_failure" : "divergent_pass",
      latencyMs: 135.0,
      signature: i < 8 ? "FAIL_date_parse_locale_confusion" : "PASS_inferred_us_format",
      summary: i < 8 ? "Failed to parse 04-05-1992 (April vs May)" : "Inferred US format by locale",
      evidenceSpanRef: "span_ocr_date"
    })),
    evidenceTrail: [
      {
        id: "span_ocr_date",
        name: "tool_call: extract_passport_ocr(doc_id='doc_771')",
        timestamp: "04:22:19.210",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "OCR tool outputted unstandardized date string '04-05-1992' without format metadata.",
        payload: { raw_dob: "04-05-1992", issuing_country: "GBR" },
        note: "Ambiguous format: UK passport uses DD-MM-YYYY, agent prompt defaulted to MM-DD-YYYY."
      }
    ],
    forensicReport: "OCR payload contained localized date without explicit format specifier. UK vs US date interpretation divergence."
  },
  {
    id: "inc_1799",
    agentName: "travel_booking_agent",
    version: "v2.1.0",
    commit: "220bb91",
    env: "production / us-east-1",
    timestamp: "2026-10-01 03:11:44 UTC",
    title: "Airport code hallucination for regional transit hub",
    status: "Confirmed bugs",
    failureBucket: "Model decision failure",
    confidenceScore: 100,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced identical hallucination",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 140.0,
      signature: "FAIL_iata_code_hallucination",
      summary: "Emitted non-existent IATA code 'ZXZ'",
      evidenceSpanRef: "span_iata_hallucinate"
    })),
    evidenceTrail: [
      {
        id: "span_iata_hallucinate",
        name: "model_decision: resolve_airport_iata",
        timestamp: "03:11:44.310",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Model hallucinated 'ZXZ' instead of querying lookup tool for regional airport.",
        payload: { target_city: "Santa Rosa", hallucinated_code: "ZXZ", valid_code: "STS" },
        note: "Requires forced tool calling instead of relying on parametric LLM memory."
      }
    ],
    forensicReport: "10/10 replays deterministically hallucinated fake airport code 'ZXZ'. The model failed to invoke the airport database tool."
  },
  {
    id: "inc_1795",
    agentName: "crm_sync_agent",
    version: "v1.3.1",
    commit: "99182ab",
    env: "production / us-west-2",
    timestamp: "2026-10-01 02:05:30 UTC",
    title: "Lead assignment rule raced against simultaneous webhook payload",
    status: "Flaky",
    failureBucket: "Non-deterministic flake",
    confidenceScore: 45,
    dominantCount: 4,
    replaysTotal: 10,
    dominantOutcome: "4 failed, 6 succeeded in sandbox",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i < 4 ? "reproduced_failure" : "divergent_pass",
      latencyMs: 180.0,
      signature: i < 4 ? "FAIL_lead_collision" : "PASS_single_owner",
      summary: i < 4 ? "Collision on account owner lock" : "Lock acquired cleanly",
      evidenceSpanRef: "span_lead_race"
    })),
    evidenceTrail: [
      {
        id: "span_lead_race",
        name: "tool_call: assign_lead_owner(lead_id='ld_441')",
        timestamp: "02:05:30.400",
        kind: "tool_call",
        isSideEffect: true,
        isOffending: true,
        divergenceReason: "Intermittent lock contention when lead state is mutated by multiple agents.",
        payload: { lead_id: "ld_441", lock_acquired: false, error: "OptimisticLockException" },
        note: "Non-deterministic behavior under concurrency."
      }
    ],
    forensicReport: "Optimistic locking collision reproduces intermittently (4/10 replays). Recommend backoff with jitter on lead assignment."
  },
  {
    id: "inc_1791",
    agentName: "fraud_detection_agent",
    version: "v2.5.0",
    commit: "77aa100",
    env: "production / us-east-1",
    timestamp: "2026-10-01 01:14:18 UTC",
    title: "Device fingerprint hash missing from initial session payload",
    status: "Needs review",
    failureBucket: "Missing context failure",
    confidenceScore: 95,
    dominantCount: 9,
    replaysTotal: 10,
    dominantOutcome: "9/10 replays failed on missing fingerprint",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i === 7 ? "divergent_pass" : "reproduced_failure",
      latencyMs: 122.0,
      signature: "FAIL_missing_device_hash",
      summary: "Risk scorer rejected payload without fingerprint",
      evidenceSpanRef: "span_fraud_ctx"
    })),
    evidenceTrail: [
      {
        id: "span_fraud_ctx",
        name: "tool_call: calculate_risk_score(tx_id='tx_109')",
        timestamp: "01:14:18.150",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Risk scoring engine rejected calculation due to missing device_fingerprint in session state.",
        payload: { device_fingerprint: null, ip_address: "192.168.1.1" },
        note: "Frontend SDK failed to collect canvas fingerprint prior to submission."
      }
    ],
    forensicReport: "Risk scoring tool threw schema exception because device fingerprint was missing from ingress context."
  },
  {
    id: "inc_1788",
    agentName: "subscription_manager",
    version: "v2.0.0",
    commit: "11ff442",
    env: "production / us-east-1",
    timestamp: "2026-09-30 23:55:01 UTC",
    title: "Downgrade flow triggered immediate cancellation instead of end-of-cycle",
    status: "Confirmed bugs",
    failureBucket: "Model decision failure",
    confidenceScore: 100,
    dominantCount: 10,
    replaysTotal: 10,
    dominantOutcome: "10/10 replays reproduced immediate cancel",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: "reproduced_failure",
      latencyMs: 150.0,
      signature: "FAIL_immediate_cancel_instead_of_prorated",
      summary: "Called cancel_now instead of queue_downgrade",
      evidenceSpanRef: "span_sub_cancel"
    })),
    evidenceTrail: [
      {
        id: "span_sub_cancel",
        name: "model_decision: select_downgrade_method",
        timestamp: "23:55:01.320",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Model called cancel_subscription(immediate=True) instead of schedule_downgrade(effective_date=period_end).",
        payload: { customer_request: "Downgrade me to basic next month", model_action: "cancel_immediately" },
        note: "Policy bug in system prompt: failed to distinguish 'cancel now' from 'downgrade at cycle end'."
      }
    ],
    forensicReport: "System prompt bug caused 10/10 replays to immediately terminate subscriptions rather than queueing a downgrade for end of billing cycle."
  },
  {
    id: "inc_1783",
    agentName: "document_parser_agent",
    version: "v1.2.0",
    commit: "88cc001",
    env: "production / us-west-1",
    timestamp: "2026-09-30 21:04:12 UTC",
    title: "PDF page stream truncated due to memory allocation limit in worker",
    status: "Needs review",
    failureBucket: "Environment issue",
    confidenceScore: 91,
    dominantCount: 9,
    replaysTotal: 10,
    dominantOutcome: "9/10 replays OOM faulted",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i === 3 ? "divergent_pass" : "reproduced_failure",
      latencyMs: 820.0,
      signature: "FAIL_worker_memory_limit",
      summary: "Worker exceeded 512MB RAM on 80-page document",
      evidenceSpanRef: "span_doc_oom"
    })),
    evidenceTrail: [
      {
        id: "span_doc_oom",
        name: "tool_call: parse_pdf_pages(doc_id='doc_9918')",
        timestamp: "21:04:12.600",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Container ran out of memory while buffering 80 high-res scans simultaneously.",
        payload: { pages_loaded: 34, total_pages: 80, exit_code: 137 },
        note: "Container OOM. Increase worker memory limit to 1GB or stream page-by-page."
      }
    ],
    forensicReport: "Worker memory ceiling exceeded on large PDF. 9 of 10 replays crashed with SIGKILL (Exit code 137)."
  },
  {
    id: "inc_1779",
    agentName: "discount_coupon_agent",
    version: "v1.0.4",
    commit: "22aa199",
    env: "production / us-east-1",
    timestamp: "2026-09-30 19:40:55 UTC",
    title: "Discount tool returned float precision rounding error $19.9999999",
    status: "Resolved",
    failureBucket: "Tool/data ambiguity",
    confidenceScore: 85,
    dominantCount: 8,
    replaysTotal: 10,
    dominantOutcome: "8/10 replays produced validation error",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i < 8 ? "reproduced_failure" : "divergent_pass",
      latencyMs: 95.0,
      signature: "FAIL_float_rounding_validation",
      summary: "Schema rejected $19.9999999 exceeding 2 decimal places",
      evidenceSpanRef: "span_float_precision"
    })),
    evidenceTrail: [
      {
        id: "span_float_precision",
        name: "tool_call: compute_percentage_discount(base=25.00, pct=0.20)",
        timestamp: "19:40:55.100",
        kind: "tool_call",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Tool returned raw float 19.999999999999996 which failed strict two-decimal checkout schema.",
        payload: { raw_discount: 19.999999999999996 },
        note: "Resolved: Added decimal.Decimal quantization in tool return."
      }
    ],
    forensicReport: "Floating point precision error tripped downstream validation. Resolved by adopting fixed-point Decimal representation."
  },
  {
    id: "inc_1774",
    agentName: "ticket_escalation_agent",
    version: "v2.3.0",
    commit: "44aa331",
    env: "production / us-east-1",
    timestamp: "2026-09-30 18:12:30 UTC",
    title: "Ambiguous priority prompt caused intermittent P1 vs P2 escalation",
    status: "Flaky",
    failureBucket: "Non-deterministic flake",
    confidenceScore: 55,
    dominantCount: 5,
    replaysTotal: 10,
    dominantOutcome: "5 replays chose P1, 5 chose P2",
    replays: Array.from({ length: 10 }, (_, i) => ({
      index: i + 1,
      status: i % 2 === 0 ? "reproduced_failure" : "divergent_pass",
      latencyMs: 140.0,
      signature: i % 2 === 0 ? "OUTCOME_P1_critical" : "OUTCOME_P2_standard",
      summary: i % 2 === 0 ? "Escalated to on-call engineer as P1" : "Queued in standard P2 pool",
      evidenceSpanRef: "span_priority_prompt"
    })),
    evidenceTrail: [
      {
        id: "span_priority_prompt",
        name: "model_decision: assign_severity",
        timestamp: "18:12:30.200",
        kind: "model_decision",
        isSideEffect: false,
        isOffending: true,
        divergenceReason: "Prompt phrasing 'urgent or important' created bimodal 50/50 split between P1 and P2 across replays.",
        payload: { prompt_instruction: "Tag as P1 if urgent or important to client", split: "5 P1 / 5 P2" },
        note: "Replace subjective words with objective SLA criteria in prompt."
      }
    ],
    forensicReport: "Ambiguous prompt instruction created an even 50/50 bimodal split across 10 identical replays. Escalate for prompt calibration."
  }
];

export default function AgentTraceConsole() {
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem("agenttrace_auth_user");
      if (saved) return JSON.parse(saved);
    } catch {
      // fallback
    }
    return {
      email: "investigator@agenttrace.io",
      role: "Lead Agent Investigator",
      name: "Lead Investigator"
    };
  });

  const [authEmail, setAuthEmail] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [incidents, setIncidents] = useState(INITIAL_INCIDENTS);
  const [selectedIncidentId, setSelectedIncidentId] = useState(INITIAL_INCIDENTS[0].id);
  const [activeStatusFilter, setActiveStatusFilter] = useState("All");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTickIndex, setSelectedTickIndex] = useState(null);
  const [highlightedSpanId, setHighlightedSpanId] = useState(null);

  // Authentication Handlers
  const handleQuickLogin = (email = "investigator@agenttrace.io", role = "Lead Agent Investigator") => {
    const formattedName = email.split("@")[0].replace(/[._-]/g, " ").replace(/\b\w/g, l => l.toUpperCase()) || "Operator";
    const userObj = { email, role, name: formattedName };
    if (rememberMe) {
      localStorage.setItem("agenttrace_auth_user", JSON.stringify(userObj));
    }
    setCurrentUser(userObj);
    setAuthError("");
  };

  const handleManualLogin = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    setAuthError("");

    const email = authEmail.trim();
    if (!email) {
      setAuthError("Work email is required.");
      return;
    }
    if (!authPassword) {
      setAuthError("Password is required.");
      return;
    }

    setIsSubmitting(true);
    setTimeout(() => {
      const role = email.toLowerCase().includes("admin") ? "Platform Admin" : "Lead Agent Investigator";
      const name = email.split("@")[0].replace(/[._-]/g, " ").replace(/\b\w/g, l => l.toUpperCase()) || "Operator";
      const userObj = { email, role, name };
      if (rememberMe) {
        localStorage.setItem("agenttrace_auth_user", JSON.stringify(userObj));
      }
      setCurrentUser(userObj);
      setIsSubmitting(false);
    }, 200);
  };

  const handleLogout = () => {
    localStorage.removeItem("agenttrace_auth_user");
    setCurrentUser(null);
  };

  // Active Incident
  const incident = useMemo(() => {
    return incidents.find(i => i.id === selectedIncidentId) || incidents[0];
  }, [incidents, selectedIncidentId]);

  // Grouped status counts
  const statusCounts = useMemo(() => {
    const counts = { All: incidents.length, "Needs review": 0, "Confirmed bugs": 0, "Flaky": 0, "Resolved": 0 };
    incidents.forEach(inc => {
      if (counts[inc.status] !== undefined) {
        counts[inc.status]++;
      }
    });
    return counts;
  }, [incidents]);

  // Filtered list
  const filteredIncidents = useMemo(() => {
    return incidents.filter(inc => {
      const matchesStatus = activeStatusFilter === "All" || inc.status === activeStatusFilter;
      const q = searchQuery.trim().toLowerCase();
      const matchesSearch = !q || 
        inc.id.toLowerCase().includes(q) || 
        inc.agentName.toLowerCase().includes(q) || 
        inc.title.toLowerCase().includes(q) ||
        inc.failureBucket.toLowerCase().includes(q);
      return matchesStatus && matchesSearch;
    });
  }, [incidents, activeStatusFilter, searchQuery]);

  // Action handlers
  const handleConfirmBug = () => {
    setIncidents(prev => prev.map(item => {
      if (item.id === incident.id) {
        return { ...item, status: "Confirmed bugs" };
      }
      return item;
    }));
  };

  const handleMarkFalsePositive = () => {
    setIncidents(prev => prev.map(item => {
      if (item.id === incident.id) {
        return { ...item, status: "Resolved" };
      }
      return item;
    }));
  };

  // Replay tick click handler: the deliberate motion moment
  const handleTickClick = (replayRun) => {
    setSelectedTickIndex(replayRun.index);
    setHighlightedSpanId(replayRun.evidenceSpanRef);

    // Scroll evidence span into view smoothly
    if (replayRun.evidenceSpanRef) {
      const el = document.getElementById(`evidence-${replayRun.evidenceSpanRef}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    }
  };

  // Helper color tags
  const getBucketColor = (bucket) => {
    switch (bucket) {
      case "Model decision failure": return "#C2542E"; // Alert rust
      case "Tool/data ambiguity": return "#E8A33D";    // Signal amber
      case "Missing context failure": return "#E8A33D"; // Signal amber
      case "Non-deterministic flake": return "#E8A33D"; // Signal amber
      case "Environment issue": return "#8B93A3";      // Muted
      default: return "#4FB8A6";
    }
  };

  const getTickColor = (run, currentIncident) => {
    if (run.status === "reproduced_failure") {
      return "#C2542E"; // Alert rust (matches original failure)
    }
    if (run.status === "divergent_error" || run.status === "divergent_ambiguous") {
      return "#E8A33D"; // Signal amber (divergent/flaky error)
    }
    if (currentIncident && currentIncident.failureBucket === "Non-deterministic flake") {
      return "#E8A33D"; // Signal amber (stochastic divergence from failure)
    }
    if (run.status === "divergent_pass" || run.status === "passed") {
      return "#232B3B"; // Recessed dark slate (passed without failure)
    }
    return "#252B37";
  };

  const getStatusBadgeStyle = (status) => {
    switch (status) {
      case "Needs review":
        return { color: "#E8A33D", borderColor: "rgba(232, 163, 61, 0.4)", background: "rgba(232, 163, 61, 0.08)" };
      case "Confirmed bugs":
        return { color: "#C2542E", borderColor: "rgba(194, 84, 46, 0.4)", background: "rgba(194, 84, 46, 0.08)" };
      case "Flaky":
        return { color: "#E8A33D", borderColor: "rgba(232, 163, 61, 0.4)", background: "rgba(232, 163, 61, 0.08)" };
      case "Resolved":
        return { color: "#4FB8A6", borderColor: "rgba(79, 184, 166, 0.4)", background: "rgba(79, 184, 166, 0.08)" };
      default:
        return { color: "#8B93A3", borderColor: "rgba(139, 147, 163, 0.3)", background: "rgba(139, 147, 163, 0.05)" };
    }
  };

  return (
    <div className="flex h-screen w-full bg-[#11141B] text-[#F6F4EF] font-sans antialiased overflow-hidden select-none">
      
      {/* =========================================================================
          LEFT RAIL: Incident List (Flat list, grouped by status, searchable)
          ========================================================================= */}
      <aside className="w-[360px] flex-shrink-0 flex flex-col border-r border-[#252B37] bg-[#141720]">
        
        {/* Top Branding / Console Header */}
        <div className="px-4 py-3 border-b border-[#252B37] flex items-center justify-between">
          <a href="/" title="Return to Product Landing Page" className="flex items-center space-x-2.5 group cursor-pointer">
            <div className="w-2.5 h-2.5 rounded-full bg-[#4FB8A6] ring-4 ring-[#4FB8A6]/20"></div>
            <span className="font-sans font-bold text-sm tracking-tight text-[#F6F4EF] group-hover:text-[#4FB8A6] transition-colors">AgentTrace</span>
            <span className="font-mono text-[10px] text-[#4FB8A6] bg-[#1A1E27] px-1.5 py-0.5 rounded border border-[#252B37]">live</span>
          </a>
          
          {/* Active Session & Overview Link */}
          <div className="flex items-center space-x-2.5">
            <div className="flex items-center space-x-1.5 text-xs text-[#8B93A3]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#4FB8A6]"></span>
              <span className="font-mono text-[11px] text-[#F6F4EF]" title={currentUser ? currentUser.email : "investigator@agenttrace.io"}>
                {currentUser ? currentUser.email.split('@')[0] : "investigator"}
              </span>
            </div>
            <a
              href="/"
              title="Return to Product Overview"
              className="px-2 py-0.5 rounded text-[11px] font-sans font-medium text-[#8B93A3] hover:text-[#4FB8A6] bg-[#1A1E27] hover:bg-[#252B37] border border-[#252B37] transition-colors flex items-center gap-1"
            >
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
              <span>Overview</span>
            </a>
          </div>
        </div>

        {/* Search Bar */}
        <div className="p-3 border-b border-[#252B37]">
          <div className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by ID, agent, or symptom..."
              className="w-full bg-[#1A1E27] text-xs font-mono text-[#F6F4EF] placeholder:font-sans placeholder-[#8B93A3] px-3 py-2 rounded border border-[#252B37] focus:outline-none focus:border-[#4FB8A6] transition-colors"
            />
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-2 text-[#8B93A3] hover:text-[#F6F4EF] text-xs font-mono"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Status Filters (Tabs) */}
        <div className="px-3 pt-2.5 pb-2 border-b border-[#252B37] flex items-center space-x-1 overflow-x-auto text-[11px]">
          {["All", "Needs review", "Confirmed bugs", "Flaky", "Resolved"].map(statusKey => {
            const count = statusCounts[statusKey] || 0;
            const isActive = activeStatusFilter === statusKey;
            return (
              <button
                key={statusKey}
                onClick={() => setActiveStatusFilter(statusKey)}
                className={`px-2 py-1 rounded font-sans font-medium whitespace-nowrap transition-colors flex items-center space-x-1.5 ${
                  isActive
                    ? "bg-[#1A1E27] text-[#F6F4EF] border border-[#343B4A]"
                    : "text-[#8B93A3] hover:text-[#F6F4EF] hover:bg-[#1A1E27]/50"
                }`}
              >
                <span>{statusKey}</span>
                <span className={`font-mono text-[10px] ${isActive ? "text-[#4FB8A6]" : "text-[#8B93A3]"}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Flat Incident List */}
        <div className="flex-1 overflow-y-auto divide-y divide-[#202532]">
          {filteredIncidents.length === 0 ? (
            <div className="p-6 text-center text-xs font-sans text-[#8B93A3]">
              No unresolved failures
            </div>
          ) : (
            filteredIncidents.map(inc => {
              const isSelected = inc.id === incident.id;
              
              return (
                <div
                  key={inc.id}
                  onClick={() => {
                    setSelectedIncidentId(inc.id);
                    setSelectedTickIndex(null);
                    setHighlightedSpanId(null);
                  }}
                  className={`px-3.5 py-3 cursor-pointer transition-colors relative border-l-2 ${
                    isSelected
                      ? "bg-[#1A1E27] border-l-[#4FB8A6]"
                      : "hover:bg-[#1A1E27]/40 border-l-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold text-[#F6F4EF]">{inc.id}</span>
                    <span className="font-mono text-[11px] text-[#8B93A3]">{inc.agentName}</span>
                  </div>

                  <p className="font-sans text-xs text-[#8B93A3] mt-1 line-clamp-1 leading-snug">
                    {inc.title}
                  </p>

                  <div className="mt-2.5 flex items-center justify-between">
                    {/* Micro replay pattern */}
                    <div className="flex items-center space-x-0.5">
                      {inc.replays.map((r, idx) => (
                        <div
                          key={idx}
                          className="w-1.5 h-2.5 rounded-[1px]"
                          style={{
                            backgroundColor: getTickColor(r, inc)
                          }}
                        />
                      ))}
                    </div>

                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-[10px] text-[#8B93A3]">
                        {inc.dominantCount}/{inc.replaysTotal}
                      </span>
                      <span
                        className="font-sans text-[10px] font-medium px-1.5 py-0.5 rounded border"
                        style={getStatusBadgeStyle(inc.status)}
                      >
                        {inc.status}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </aside>


      {/* =========================================================================
          MAIN PANEL: Case File / Investigation Board
          ========================================================================= */}
      <main className="flex-1 flex flex-col bg-[#11141B] overflow-y-auto">
        
        {/* Incident Case Header Bar */}
        <header className="px-8 py-5 border-b border-[#252B37] bg-[#141720]">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <span className="font-mono text-base font-bold text-[#4FB8A6]">{incident.id}</span>
              <span className="text-[#8B93A3]">•</span>
              <span className="font-mono text-xs text-[#8B93A3]">{incident.agentName} {incident.version}</span>
              <span className="text-[#8B93A3]">•</span>
              <span className="font-mono text-xs text-[#8B93A3]">{incident.commit}</span>
              <span className="text-[#8B93A3]">•</span>
              <span className="font-mono text-xs text-[#8B93A3]">{incident.env}</span>
            </div>

            <div className="flex items-center space-x-2">
              <span className="font-mono text-xs text-[#8B93A3]">{incident.timestamp}</span>
              <span
                className="font-sans text-xs px-2.5 py-0.5 rounded border font-medium"
                style={getStatusBadgeStyle(incident.status)}
              >
                {incident.status}
              </span>
            </div>
          </div>

          <h1 className="font-sans text-xl font-bold text-[#F6F4EF] tracking-tight leading-snug mt-2.5">
            {incident.title}
          </h1>
        </header>

        {/* Content Body */}
        <div className="px-8 py-6 space-y-7 max-w-5xl">

          {/* =====================================================================
              HERO OBJECT: THE REPLAY STRIP
              Continuous horizontal row of N ticks, each colored by outcome
              ===================================================================== */}
          <section className="bg-[#1A1E27] border border-[#252B37] rounded-lg p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <span className="font-sans text-xs font-semibold text-[#8B93A3]">
                  Replay strip
                </span>
                <span className="font-sans text-xs text-[#8B93A3]">
                  ({incident.replaysTotal} sandbox runs against recorded inputs)
                </span>
              </div>

              <div className="flex items-center space-x-4 text-xs font-sans text-[#8B93A3]">
                <span className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded-[1px] bg-[#C2542E]"></span>
                  <span>reproduced failure</span>
                </span>
                <span className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded-[1px] bg-[#E8A33D]"></span>
                  <span>divergent / flaky</span>
                </span>
                <span className="flex items-center space-x-1.5">
                  <span className="w-2.5 h-2.5 rounded-[1px] bg-[#232B3B] border border-[#3A4354]"></span>
                  <span>passed</span>
                </span>
              </div>
            </div>

            {/* Continuous Strip Track */}
            <div className="bg-[#0D1017] p-1.5 rounded border border-[#252B37] flex items-stretch gap-1.5 h-12 w-full">
              {incident.replays.map((run) => {
                const isSelected = selectedTickIndex === run.index;
                const tickBg = getTickColor(run, incident);
                const isDark = tickBg === "#232B3B";

                return (
                  <button
                    key={run.index}
                    onClick={() => handleTickClick(run)}
                    title={`Run #${run.index}: ${run.summary} (${run.latencyMs.toFixed(0)}ms)`}
                    className={`flex-1 h-full rounded-[2px] transition-all relative flex flex-col items-center justify-end pb-1 select-none group cursor-pointer ${
                      isSelected
                        ? "ring-2 ring-[#4FB8A6] ring-offset-1 ring-offset-[#0D1017] scale-y-[1.04] z-10 brightness-110"
                        : "hover:brightness-125"
                    }`}
                    style={{
                      backgroundColor: tickBg,
                      border: isDark ? "1px solid #343D4E" : "none"
                    }}
                  >
                    {isSelected && (
                      <span className="absolute -top-1 w-1.5 h-1.5 rounded-full bg-[#4FB8A6] ring-2 ring-[#0D1017]"></span>
                    )}
                    <span
                      className={`font-mono text-[10px] font-semibold leading-none ${
                        isDark ? "text-[#8B93A3]" : "text-[#11141B] font-bold"
                      }`}
                    >
                      {run.index}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Selected Tick Detail / Guidance */}
            {selectedTickIndex !== null ? (
              (() => {
                const selectedRun = incident.replays.find(r => r.index === selectedTickIndex);
                if (!selectedRun) return null;
                const isFailure = selectedRun.status === "reproduced_failure";
                return (
                  <div className="mt-3 px-3 py-2 bg-[#141720] rounded border border-[#252B37] flex items-center justify-between text-xs">
                    <div className="flex items-center space-x-2.5">
                      <span className="font-sans font-semibold text-[#F6F4EF]">
                        Run #{selectedTickIndex}
                      </span>
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-mono font-medium"
                        style={{
                          backgroundColor: isFailure ? "rgba(194,84,46,0.15)" : "rgba(232,163,61,0.15)",
                          color: isFailure ? "#C2542E" : "#E8A33D",
                          border: `1px solid ${isFailure ? "rgba(194,84,46,0.3)" : "rgba(232,163,61,0.3)"}`
                        }}
                      >
                        {selectedRun.status.replace("_", " ")}
                      </span>
                      <span className="font-mono text-xs text-[#8B93A3]">
                        {selectedRun.latencyMs.toFixed(1)}ms
                      </span>
                      <span className="text-[#8B93A3]">•</span>
                      <span className="font-sans text-xs text-[#F6F4EF]">
                        {selectedRun.summary}
                      </span>
                    </div>
                    <div className="flex items-center space-x-1.5 font-mono text-[11px] text-[#8B93A3]">
                      <span>highlighting span:</span>
                      <span className="text-[#4FB8A6] font-semibold bg-[#11141B] px-1.5 py-0.5 rounded border border-[#252B37]">
                        {selectedRun.evidenceSpanRef}
                      </span>
                    </div>
                  </div>
                );
              })()
            ) : (
              <div className="mt-2.5 flex items-center justify-between text-xs font-sans text-[#8B93A3]">
                <span>Click any run tick to inspect parameters and highlight matching evidence span below</span>
                <span className="font-mono text-[11px] text-[#8B93A3]">{incident.dominantOutcome}</span>
              </div>
            )}
          </section>


          {/* =====================================================================
              CLASSIFICATION & CONFIDENCE
              Directly below the replay strip
              ===================================================================== */}
          <section className="grid grid-cols-2 gap-4">
            <div className="bg-[#1A1E27] border border-[#252B37] rounded-lg p-4">
              <span className="font-sans text-xs font-semibold text-[#8B93A3] block">
                Classification
              </span>
              <div className="flex items-center space-x-2.5 mt-2">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: getBucketColor(incident.failureBucket) }}
                ></span>
                <span className="font-sans text-base font-bold text-[#F6F4EF]">
                  {incident.failureBucket}
                </span>
              </div>
              <p className="font-sans text-xs text-[#8B93A3] mt-2 leading-relaxed">
                {incident.failureBucket === "Tool/data ambiguity" && "Tool returned payload that confused model reasoning."}
                {incident.failureBucket === "Model decision failure" && "Model selected unauthorized tool or violated policy rule."}
                {incident.failureBucket === "Missing context failure" && "Required conversation context was absent from initial state."}
                {incident.failureBucket === "Non-deterministic flake" && "Intermittent variance caused by temperature or prompt ambiguity."}
                {incident.failureBucket === "Environment issue" && "Infrastructure timeout or upstream connection error."}
              </p>
            </div>

            <div className="bg-[#1A1E27] border border-[#252B37] rounded-lg p-4">
              <span className="font-sans text-xs font-semibold text-[#8B93A3] block">
                Confidence score
              </span>
              <div className="flex items-baseline space-x-2.5 mt-1.5">
                <span className="font-mono text-3xl font-bold text-[#4FB8A6]">
                  {incident.confidenceScore}%
                </span>
                <span className="font-mono text-xs text-[#8B93A3]">
                  ({incident.dominantCount}/{incident.replaysTotal} replays agreed)
                </span>
              </div>
              <div className="w-full bg-[#11141B] h-1.5 rounded-full overflow-hidden mt-3 border border-[#252B37]">
                <div
                  className="h-full bg-[#4FB8A6]"
                  style={{ width: `${incident.confidenceScore}%` }}
                ></div>
              </div>
            </div>
          </section>


          {/* =====================================================================
              EVIDENCE TRAIL (Not a table; chronological forensic trace trail)
              ===================================================================== */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <span className="font-sans text-xs font-semibold text-[#8B93A3]">
                  Evidence trail
                </span>
                <span className="font-sans text-xs text-[#8B93A3]">
                  (original trace spans & recorded mock interactions)
                </span>
              </div>
              <span className="font-mono text-xs text-[#8B93A3]">
                {incident.evidenceTrail.length} spans captured
              </span>
            </div>

            <div className="space-y-3 font-mono text-xs">
              {incident.evidenceTrail.map((span) => {
                const isOffending = span.isOffending;
                const isSelectedByTick = highlightedSpanId === span.id;

                return (
                  <div
                    key={span.id}
                    id={`evidence-${span.id}`}
                    className={`rounded-lg border transition-all duration-200 ${
                      isSelectedByTick
                        ? "border-[#4FB8A6] ring-2 ring-[#4FB8A6]/20 bg-[#1A1E27]"
                        : isOffending
                        ? "border-[#C2542E]/70 bg-[#1A1E27]"
                        : "border-[#252B37] bg-[#141720]"
                    }`}
                  >
                    {/* Span Header Bar */}
                    <div className="px-4 py-2.5 flex items-center justify-between border-b border-[#252B37]/60">
                      <div className="flex items-center space-x-2.5">
                        <span className="text-[#8B93A3] text-[11px] font-mono">{span.timestamp}</span>
                        <span className="text-[#F6F4EF] font-mono font-semibold">{span.name}</span>
                        {span.isSideEffect && (
                          <span className="font-sans px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#E8A33D]/10 text-[#E8A33D] border border-[#E8A33D]/30">
                            side-effect safely mocked
                          </span>
                        )}
                        {isOffending && (
                          <span className="font-sans px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#C2542E]/10 text-[#C2542E] border border-[#C2542E]/30">
                            divergence point
                          </span>
                        )}
                      </div>

                      <span className="text-[#8B93A3] text-[11px] font-mono">{span.id}</span>
                    </div>

                    {/* Span Content */}
                    <div className="p-4 space-y-3">
                      {isOffending && span.divergenceReason && (
                        <div className="text-[#C2542E] text-xs font-sans font-medium bg-[#C2542E]/5 p-2.5 rounded border border-[#C2542E]/20">
                          {span.divergenceReason}
                        </div>
                      )}

                      {/* Paper Area: Forensic Evidence Payload */}
                      <div className="bg-[#F6F4EF] text-[#11141B] p-3.5 rounded font-mono text-[11px] overflow-x-auto shadow-inner border border-[#E2DDD5]">
                        <pre className="font-mono whitespace-pre-wrap leading-relaxed">
                          {JSON.stringify(span.payload, null, 2)}
                        </pre>
                      </div>

                      {span.note && (
                        <p className="text-xs text-[#8B93A3] font-sans leading-relaxed">
                          {span.note}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>


          {/* =====================================================================
              FORENSIC INVESTIGATION REPORT (Paper texture box)
              ===================================================================== */}
          <section className="space-y-2">
            <span className="font-sans text-xs font-semibold text-[#8B93A3]">
              Case file investigation report
            </span>
            <div className="bg-[#F6F4EF] text-[#11141B] p-5 rounded-lg border border-[#E2DDD5] shadow-sm">
              <p className="font-sans text-xs leading-relaxed text-[#11141B]">
                {incident.forensicReport}
              </p>
            </div>
          </section>


          {/* =====================================================================
              ACTION BAR
              Confirm bug / Mark false positive
              ===================================================================== */}
          <section className="pt-4 border-t border-[#252B37] flex items-center justify-between">
            <div className="text-xs font-sans text-[#8B93A3]">
              Confirmed bugs export a regression fixture to CI automatically
            </div>

            <div className="flex items-center space-x-3">
              <button
                onClick={handleMarkFalsePositive}
                className="px-4 py-2 rounded text-xs font-sans font-semibold text-[#8B93A3] hover:text-[#F6F4EF] bg-[#1A1E27] border border-[#252B37] hover:border-[#384252] transition-colors"
              >
                Mark false positive
              </button>

              <button
                onClick={handleConfirmBug}
                className="px-4 py-2 rounded text-xs font-sans font-semibold text-white bg-[#C2542E] hover:bg-[#D46038] border border-[#C2542E] transition-colors flex items-center space-x-2"
              >
                <span>Confirm bug</span>
              </button>
            </div>
          </section>

        </div>
      </main>

    </div>
  );
}
