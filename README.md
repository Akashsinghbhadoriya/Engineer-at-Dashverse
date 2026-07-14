# Travel Planning Agent Orchestrator

A multi-agent orchestration system for a Travel Planning Assistant, built with Python's `asyncio`. Processes natural-language travel requests through a chain of specialized agents, with parallel provider lookups and graceful error handling.

---

## How to Run

**Requirements:** Python 3.11+ (no external dependencies — stdlib only)

```bash
python3 main.py
```

This runs five scenarios in sequence:
1. Happy path — all 3 providers succeed
2. Partial failure — one provider fails permanently
3. All providers fail
4. Transient failure — one provider fails twice, then succeeds on retry
5. Missing info — vague query triggers clarification response

---

## Agent Architecture

### DAG (Directed Acyclic Graph)

```
                    ┌─────────────────────────────────────────────┐
  Phase 1           │  parser ──► validator                       │
  (sequential)      └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
  Phase 2           │  provider_a  ──┐                            │
  (PARALLEL)        │  provider_b  ──┼──► aggregator ──► formatter│
                    │  provider_c  ──┘                            │
  Phase 3           └─────────────────────────────────────────────┘
  (sequential)
```

### Agent Responsibilities

| Agent | Node ID | Responsibility |
|---|---|---|
| `ParserAgent` | `parser` | Extracts structured fields (destination, origin, date, trip_type) from raw text using regex |
| `ValidatorAgent` | `validator` | Checks all required fields are present; returns list of missing fields |
| `ProviderAgent` × 3 | `provider_a/b/c` | Mocks an airline API call; returns the cheapest flight for that carrier |
| `AggregatorAgent` | `aggregator` | Collects all successful provider results; selects the best price |
| `FormatterAgent` | `formatter` | Builds the final user-facing string, or a clarification request if fields are missing |

---

## Design Decisions & Trade-offs

### Why 7 nodes (5 agent types)?

**Parser and Validator are separate agents.**
Parsing (text → structure) and validation (completeness check) have different concerns. Merging them would mean the regex extraction and field-checking logic live together — harder to test and extend independently. The extra communication overhead (one dict passed between agents) is negligible.

**Three ProviderAgent instances, not one.**
Each provider must run concurrently and independently. A single "multi-provider" agent would force sequential calls internally, defeating the purpose. Three separate nodes let the orchestrator fan them out in parallel natively.

**Aggregator and Formatter are separate agents.**
Aggregation (pick the best from N results) and formatting (render a human string) are distinct transformations. Keeping them separate means you can swap the formatter (e.g., for a different output format) without touching selection logic.

**Why not combine Parser + Validator?**
The validator's `missing_fields` output is needed by the formatter directly (bypassing the provider results when info is missing). If merged, the formatter would need to reach into the combined agent's output with mixed concerns. Keeping them separate preserves the clean contract each downstream node expects.

### Which agents run in parallel, and why?

`provider_a`, `provider_b`, and `provider_c` run **in parallel**. They have no dependency on each other — each only needs the validator's output. Querying three airlines sequentially would cost ~(delay_A + delay_B + delay_C); in parallel it costs ~max(delay_A, delay_B, delay_C).

Everything else is sequential: parser → validator must complete before providers can start (providers need validated structured data), and aggregator → formatter must run after providers (they consume provider results).

### How parallel agent failures are handled

The `aggregator` node uses `join_policy="ANY"`:

- **All terminal + ≥1 completed** → aggregator runs with whatever succeeded
- **All terminal + 0 completed** → the scheduler marks aggregator as `SKIPPED` (and formatter as `SKIPPED` downstream)

Inside `AggregatorAgent.execute`, the context is filtered to drop `None` entries (nodes that failed have no context entry), so the aggregator works naturally over 1, 2, or 3 results. If 0 results arrive, it returns an early response string instead of crashing.

| Providers succeeding | Outcome |
|---|---|
| 3/3 | Best of all three |
| 2/3 | Best of two; third silently excluded |
| 1/3 | That one result returned |
| 0/3 | Aggregator skipped → formatter skipped → `response: None` |

### Technology choice for parallel execution: `asyncio`

Python's `asyncio` cooperative concurrency was chosen over threads or `multiprocessing` because:

- **No race conditions by design.** asyncio is single-threaded; only one coroutine runs at a time, and context switches happen only at `await` points. Shared state (the `context` dict, `node_states`) can be read/written without locks in most places — the check-and-set in `try_claim` is atomic because there's no interleaving between the check and the set.
- **Low overhead.** The bottleneck is I/O latency (simulated with `asyncio.sleep`), not CPU. Threads would add OS-level overhead for no gain here.
- **Timeout support.** `asyncio.wait_for` gives per-node timeouts cleanly without extra machinery.

The only lock in the codebase (`Execution._state_lock`) is there defensively for future thread-safety if the execution model ever changes.

### Immutable context via `MappingProxyType`

Each agent receives a `frozen_view` of the context — a `MappingProxyType` that raises `TypeError` on any write attempt. This enforces that agents are pure transformers: they read existing context and return a new `AgentResult`, never mutating shared state. The orchestrator is the sole writer (via `execution.context[node.id] = result.data`).

### EventBus + scheduler decoupling

When a node finishes, it emits an event to the `EventBus`. Two subscribers handle it:
1. **Trace handler** — appends to the execution trace
2. **Scheduler handler** — inspects all downstream nodes and schedules any that are now ready

This means the `Orchestrator` doesn't contain scheduling logic — it just fires entry nodes and awaits. Adding a new cross-cutting concern (e.g., metrics, alerting) is a new `bus.subscribe(...)` call, with zero changes to orchestrator or scheduler.

### Retry logic

`RetryPolicy(max_attempts, backoff_seconds)` is configured per node. The scheduler retries with `backoff_seconds * attempt` sleep between tries. Provider nodes get `max_attempts=3` by default; parser/validator/aggregator/formatter get `max_attempts=1` (failures there are not transient).

---

## Assumptions

- All external API calls are mocked via `mock_data.json`; no real HTTP requests are made
- NLP parsing is regex-based (sufficient for the structured test inputs; not production NLP)
- "Best" flight means lowest price across all successful providers
- `trip_type` is one of: `vacation`, `business`, `holiday` — extracted by keyword match
- Dates are expressed as `today`, `tomorrow`, or `YYYY-MM-DD` / `M/D/YYYY` patterns
- Scenario behavior (delays, failure modes, retry counts) is fully declarative in `mock_data.json` — no code changes needed to simulate new failure patterns

---

## Example Output

### Scenario 1: Happy Path (all providers succeed)

```
=======================================================
SCENARIO : Happy Path  (mock: 'happy_path')
Input    : Book me a flight from New York to Paris today for vacation

  Execution Trace:
    [COMPLETED ] parser      @ t+0.000s
    [COMPLETED ] validator   @ t+0.000s
    [COMPLETED ] provider_a  @ t+0.101s   ─┐
    [COMPLETED ] provider_c  @ t+0.121s    ├── ran in parallel
    [COMPLETED ] provider_b  @ t+0.151s   ─┘
    [COMPLETED ] aggregator  @ t+0.151s
    [COMPLETED ] formatter   @ t+0.151s

  Response : Your best flight is with United at $360.0
  Duration : 152ms
```

Providers ran concurrently (A finished at ~100ms, C at ~120ms, B at ~150ms). Total wall time ≈ slowest provider (150ms), not sum (370ms).

---

### Scenario 2: Partial Failure — United permanently down

```
=======================================================
SCENARIO : Partial Failure (United down)  (mock: 'partial_failure')
Input    : Book me a flight from New York to Paris today for vacation

  Execution Trace:
    [COMPLETED ] parser      @ t+0.000s
    [COMPLETED ] validator   @ t+0.000s
    [FAILED    ] provider_c  @ t+0.051s   ─┐
    [COMPLETED ] provider_a  @ t+0.101s    ├── ran in parallel; United failed
    [COMPLETED ] provider_b  @ t+0.151s   ─┘
    [COMPLETED ] aggregator  @ t+0.151s       ← join_policy=ANY: continued with 2 results
    [COMPLETED ] formatter   @ t+0.151s

  Response : Your best flight is with Delta at $380.0
  Duration : 152ms
```

`provider_c` (United) failed. The aggregator's `join_policy="ANY"` allowed the chain to continue. Best result from the two successful providers was returned.

---

### Scenario 3: All Providers Fail

```
=======================================================
SCENARIO : All Providers Fail  (mock: 'all_fail')
Input    : Book me a flight from New York to Paris today for vacation

  Execution Trace:
    [COMPLETED ] parser      @ t+0.000s
    [COMPLETED ] validator   @ t+0.000s
    [FAILED    ] provider_a  @ t+0.052s
    [FAILED    ] provider_b  @ t+0.052s
    [FAILED    ] provider_c  @ t+0.052s
    [SKIPPED   ] aggregator  @ t+0.052s   ← all deps failed; skipped by scheduler
    [SKIPPED   ] formatter   @ t+0.052s   ← propagated skip

  Response : None
  Duration : 52ms
```

All three providers failed. The scheduler detected 0 completed dependencies for aggregator and propagated a SKIPPED state down the chain. The system did not hang.

---

### Scenario 4: Transient Failure with Retry (Delta fails 2×, succeeds 3rd)

```
=======================================================
SCENARIO : Retry Then Succeed (Delta transient)  (mock: 'retry_then_succeed')
Input    : Book me a flight from New York to Paris today for vacation

  Execution Trace:
    [COMPLETED ] parser      @ t+0.000s
    [COMPLETED ] validator   @ t+0.001s
    [COMPLETED ] provider_a  @ t+0.101s   ─┐
    [COMPLETED ] provider_c  @ t+0.121s    ├── AirFrance + United finished quickly
    [COMPLETED ] provider_b  @ t+3.305s   ─┘  Delta retried twice (backoff: 1s, 2s)
    [COMPLETED ] aggregator  @ t+3.305s
    [COMPLETED ] formatter   @ t+3.305s

  Response : Your best flight is with United at $360.0
  Duration : 3306ms
```

Delta (provider_b) failed on attempts 1 and 2, then succeeded on attempt 3. `RetryPolicy(max_attempts=3, backoff_seconds=1.0)` handled this automatically. Other providers completed in parallel and waited at the aggregator.

---

### Scenario 5: Missing Information

```
=======================================================
SCENARIO : Missing Info  (mock: 'happy_path')
Input    : I want to travel somewhere

  Execution Trace:
    [COMPLETED ] parser      @ t+0.000s
    [COMPLETED ] validator   @ t+0.000s
    [COMPLETED ] provider_a  @ t+0.101s
    [COMPLETED ] provider_c  @ t+0.121s
    [COMPLETED ] provider_b  @ t+0.151s
    [COMPLETED ] aggregator  @ t+0.151s
    [COMPLETED ] formatter   @ t+0.151s

  Response : I need a bit more information to find your flight.
             Could you please provide: date, origin, trip_type?
  Duration : 152ms
```

Validator marked `validated=False` with `missing_fields`. The formatter detected this and short-circuited to a clarification response, ignoring the (wasted) provider results.

> **Design note:** An alternative would be to skip provider calls when validation fails. This could be achieved by adding a conditional node or changing the validator to return `status="failed"` — but that would require a `join_policy` change on providers or a new branch node. The current approach keeps the graph simple at the cost of unnecessary provider calls on bad input.

---

## Extensibility

The orchestrator, scheduler, and execution engine are **completely domain-agnostic**. They operate on `WorkflowGraph` — a list of `Node` objects. Nothing in `orchestrator.py`, `scheduler.py`, or `execution.py` knows anything about travel, flights, or providers. Swapping domains means only changing `workflow.py` and writing new agents.

### Different workflows from the same engine

`build_travel_graph()` in `workflow.py` is just one possible graph. The same orchestrator could run:

```python
# E-commerce order pipeline
WorkflowGraph([
    Node(id="intent_parser",    dependencies=[],                    agent=IntentParserAgent()),
    Node(id="inventory_check",  dependencies=["intent_parser"],     agent=InventoryAgent()),
    Node(id="pricing_engine",   dependencies=["intent_parser"],     agent=PricingAgent()),
    Node(id="fraud_check",      dependencies=["intent_parser"],     agent=FraudAgent()),
    Node(id="checkout",         dependencies=["inventory_check",
                                              "pricing_engine",
                                              "fraud_check"],       agent=CheckoutAgent()),
])

# Content moderation pipeline
WorkflowGraph([
    Node(id="text_classifier",  dependencies=[],                    agent=TextClassifierAgent()),
    Node(id="image_classifier", dependencies=[],                    agent=ImageClassifierAgent()),
    Node(id="policy_checker",   dependencies=["text_classifier",
                                              "image_classifier"],  agent=PolicyAgent()),
    Node(id="action_router",    dependencies=["policy_checker"],    agent=ActionRouterAgent()),
])
```

Any DAG — any number of nodes, any fan-out/fan-in shape — works without touching the core engine.

### Dynamic workflow construction

`workflow.py` can be replaced with a planner agent that builds the graph at runtime based on the request. For example:

```python
# A PlannerAgent could return a list of node specs:
# "user wants flight + hotel" → build a graph with both provider sub-chains
# "user wants flight only"    → build a leaner graph, skip hotel nodes

async def build_dynamic_graph(user_input: str) -> WorkflowGraph:
    plan = await PlannerAgent().execute(user_input)
    nodes = []
    for step in plan["steps"]:
        nodes.append(Node(id=step["id"],
                          dependencies=step["deps"],
                          agent=AGENT_REGISTRY[step["agent_type"]](),
                          retry_policy=RetryPolicy(**step.get("retry", {})),
                          timeout=step.get("timeout", 5.0)))
    return WorkflowGraph(nodes)
```

The orchestrator receives the graph and runs it — it doesn't care how the graph was built.

### Expanding `RetryPolicy`

`RetryPolicy` currently exposes `max_attempts` and `backoff_seconds`. It can be extended without changing the scheduler's core loop:

| Field | What it enables |
|---|---|
| `strategy: "fixed" \| "exponential" \| "jitter"` | Different backoff curves |
| `retry_on: list[type]` | Retry only on specific exception types |
| `deadline_seconds: float` | Total time budget across all attempts (not per attempt) |
| `on_retry: Callable` | Hook to log, alert, or mutate context before each retry |

### Expanding `join_policy`

`Node.join_policy` currently supports `"ALL"` (every dep must complete) and `"ANY"` (at least one dep must complete). Additional policies that fit naturally:

| Policy | Semantics |
|---|---|
| `"MAJORITY"` | ≥ ⌈N/2⌉ deps must complete — useful for quorum-based decisions |
| `"N_OF_M"` | Exactly N successes required out of M deps — configurable threshold |
| `"FIRST"` | Start as soon as any dep completes, cancel the rest — racing pattern |
| `"TIMEOUT_GATE"` | Wait up to T seconds, then proceed with whatever arrived |

Each policy is a pure function of `node_states` — a new `elif` branch in `is_ready()` inside `scheduler.py` is the only change needed.

---

## File Structure

```
.
├── main.py          # Entry point; defines and runs 5 test scenarios
├── models.py        # Core data types: AgentResult, Node, WorkflowGraph, RetryPolicy
├── orchestrator.py  # Kicks off entry nodes, wires EventBus, returns final result
├── scheduler.py     # try_claim, run_node (with retry/timeout), scheduler_handler
├── execution.py     # Shared execution state: context dict + node_states + frozen_view
├── event_bus.py     # Pub/sub: emit(node, execution) calls all subscribers
├── workflow.py      # build_travel_graph() — declarative graph definition
├── mock_data.json   # Flight data + per-scenario behavior config
└── agents/
    ├── base.py      # Abstract Agent interface
    ├── parser.py    # ParserAgent
    ├── validator.py # ValidatorAgent
    ├── provider.py  # ProviderAgent (instantiated 3× with different names)
    ├── aggregator.py# AggregatorAgent
    └── formatter.py # FormatterAgent
```
