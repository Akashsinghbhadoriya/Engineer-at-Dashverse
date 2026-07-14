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

The `EventBus` emits three typed events per node — `"START"`, `"RETRY"`, and `"END"` — each carrying an optional `meta` dict. Two subscribers react:

1. **Trace handler** — reacts to all three events: prints live output (`▶ start`, `↺ retry`, `✓/✗/— end`) during the run, then records a full trace entry (duration, attempts, parallel flag) on `"END"`
2. **Scheduler handler** — only acts on `"END"` to inspect downstream nodes and schedule any that are now ready

Adding a new cross-cutting concern (metrics, alerting) is a new `bus.subscribe(...)` call with zero changes to orchestrator or scheduler.

**Parallel detection:** At node start, the scheduler checks `node_states` for any other `RUNNING` node. If one exists, the node is tagged `parallel=True` in `execution.node_meta`. This flows into the live `[parallel]` tag and the final trace table's `Parallel` column.

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

Each scenario prints a **live execution stream** (nodes as they fire/finish) followed by the final result and a **summary trace table** (Node, Status, Duration, Attempts, Parallel).

### Scenario 1: Happy Path — all 3 providers succeed

```
════════════════════════════════════════════════════════════════════════
  TEST: Happy Path — All 3 Providers Succeed
  Input: "Book a flight from new york to paris today for vacation"
────────────────────────────────────────────────────────────────────────
  Live execution:

    ▶  Parser
    ✓  Parser  0.2ms
    ▶  Validator
    ✓  Validator  0.0ms
    ▶  ProviderA (AirFrance)  [parallel]
    ▶  ProviderB (Delta)  [parallel]
    ▶  ProviderC (United)  [parallel]
    ✓  ProviderA (AirFrance)  101.2ms
    ✓  ProviderC (United)  121.1ms
    ✓  ProviderB (Delta)  151.1ms
    ▶  Aggregator
    ✓  Aggregator  0.0ms
    ▶  Formatter
    ✓  Formatter  0.0ms

────────────────────────────────────────────────────────────────────────
  RESULT:
    Best option: United  $360  (9h 30m)
    Other options:
      • AirFrance  $450  (8h 30m)
      • Delta  $380  (9h 00m)

────────────────────────────────────────────────────────────────────────
  EXECUTION TRACE
────────────────────────────────────────────────────────────────────────
  Node                       Status       Duration       Attempts       Parallel
────────────────────────────────────────────────────────────────────────
  Parser                     ✓  OK        0.2ms          1/1            No
  Validator                  ✓  OK        0.0ms          1/1            No
  ProviderA (AirFrance)      ✓  OK        101.2ms        1/3            Yes
  ProviderC (United)         ✓  OK        121.1ms        1/3            Yes
  ProviderB (Delta)          ✓  OK        151.1ms        1/3            Yes
  Aggregator                 ✓  OK        0.0ms          1/1            No
  Formatter                  ✓  OK        0.0ms          1/1            No
────────────────────────────────────────────────────────────────────────
  Total wall time: 151.6ms  |  3/3 providers responded
────────────────────────────────────────────────────────────────────────
```

All three providers are tagged `[parallel]` in the live stream and `Parallel: Yes` in the table. Wall time ≈ slowest provider (~150ms), not the sum (~370ms). The formatter now lists all options with duration, not just the winner.

---

### Scenario 2: Partial Failure — United fails permanently

```
════════════════════════════════════════════════════════════════════════
  TEST: Partial Failure — United fails permanently
  Input: "Book a flight from new york to paris today for vacation"
────────────────────────────────────────────────────────────────────────
  Live execution:

    ▶  ProviderA (AirFrance)  [parallel]
    ▶  ProviderB (Delta)  [parallel]
    ▶  ProviderC (United)  [parallel]
    ✗  ProviderC (United)  FAILED after 2 attempt(s)
    ✓  ProviderA (AirFrance)  101.1ms
    ✓  ProviderB (Delta)  151.1ms
    ▶  Aggregator
    ✓  Aggregator  0.0ms

────────────────────────────────────────────────────────────────────────
  RESULT:
    Best option: Delta  $380  (9h 00m)
    Other options:
      • AirFrance  $450  (8h 30m)

────────────────────────────────────────────────────────────────────────
  EXECUTION TRACE
────────────────────────────────────────────────────────────────────────
  Node                       Status       Duration       Attempts       Parallel
────────────────────────────────────────────────────────────────────────
  ProviderC (United)         ✗  FAIL      51.1ms         2/3            Yes
  ProviderA (AirFrance)      ✓  OK        101.1ms        1/3            Yes
  ProviderB (Delta)          ✓  OK        151.1ms        1/3            Yes
  Aggregator                 ✓  OK        0.0ms          1/1            No
  Formatter                  ✓  OK        0.0ms          1/1            No
────────────────────────────────────────────────────────────────────────
  Total wall time: 151.8ms  |  2/3 providers responded
────────────────────────────────────────────────────────────────────────
```

United exhausted its retry budget (`2/3` attempts shown) and failed. `join_policy="ANY"` let the aggregator continue with AirFrance + Delta. The trace footer reports `2/3 providers responded`.

---

### Scenario 3: All Providers Fail

```
════════════════════════════════════════════════════════════════════════
  TEST: All Providers Fail
  Input: "Book a flight from new york to paris today for vacation"
────────────────────────────────────────────────────────────────────────
  Live execution:

    ▶  ProviderA (AirFrance)  [parallel]
    ▶  ProviderB (Delta)  [parallel]
    ▶  ProviderC (United)  [parallel]
    ✗  ProviderA (AirFrance)  FAILED after 2 attempt(s)
    ✗  ProviderB (Delta)  FAILED after 2 attempt(s)
    ✗  ProviderC (United)  FAILED after 2 attempt(s)
    —  Aggregator  SKIPPED
    —  Formatter  SKIPPED

────────────────────────────────────────────────────────────────────────
  RESULT:
    No response generated.

────────────────────────────────────────────────────────────────────────
  EXECUTION TRACE
────────────────────────────────────────────────────────────────────────
  Node                       Status       Duration       Attempts       Parallel
────────────────────────────────────────────────────────────────────────
  ProviderA (AirFrance)      ✗  FAIL      51.2ms         2/3            Yes
  ProviderB (Delta)          ✗  FAIL      51.2ms         2/3            Yes
  ProviderC (United)         ✗  FAIL      51.2ms         2/3            Yes
  Aggregator                 —  SKIP      —              1/1            No
  Formatter                  —  SKIP      —              1/1            No
────────────────────────────────────────────────────────────────────────
  Total wall time: 51.8ms  |  0/3 providers responded
────────────────────────────────────────────────────────────────────────
```

All providers failed. The scheduler propagated `SKIPPED` down to aggregator and formatter. The system did not hang — total time was just the provider delay (~50ms).

---

### Scenario 4: Transient Failure with Retry (Delta fails 2×, succeeds 3rd)

```
════════════════════════════════════════════════════════════════════════
  TEST: Retry Then Succeed — Delta transient failure
  Input: "Book a flight from new york to paris today for vacation"
────────────────────────────────────────────────────────────────────────
  Live execution:

    ▶  ProviderA (AirFrance)  [parallel]
    ▶  ProviderB (Delta)  [parallel]
    ▶  ProviderC (United)  [parallel]
    ✓  ProviderA (AirFrance)  101.1ms
    ↺  ProviderB (Delta)  retrying (1/3)
    ✓  ProviderC (United)  121.1ms
    ↺  ProviderB (Delta)  retrying (2/3)
    ✓  ProviderB (Delta)  3305.6ms
    ▶  Aggregator
    ✓  Aggregator  0.0ms

────────────────────────────────────────────────────────────────────────
  RESULT:
    Best option: United  $360  (9h 30m)
    Other options:
      • AirFrance  $450  (8h 30m)
      • Delta  $380  (9h 00m)

────────────────────────────────────────────────────────────────────────
  EXECUTION TRACE
────────────────────────────────────────────────────────────────────────
  Node                       Status       Duration       Attempts       Parallel
────────────────────────────────────────────────────────────────────────
  ProviderA (AirFrance)      ✓  OK        101.1ms        1/3            Yes
  ProviderC (United)         ✓  OK        121.1ms        1/3            Yes
  ProviderB (Delta)          ✓  OK        3305.6ms       3/3            Yes
  Aggregator                 ✓  OK        0.0ms          1/1            No
  Formatter                  ✓  OK        0.0ms          1/1            No
────────────────────────────────────────────────────────────────────────
  Total wall time: 3306.2ms  |  3/3 providers responded
────────────────────────────────────────────────────────────────────────
```

The live stream shows two `↺` retry events for Delta before it succeeds. The trace table shows `3/3` attempts used and `3305.6ms` total duration (includes backoff sleeps of 1s + 2s). AirFrance and United completed normally while Delta retried in the background.

---

### Scenario 5: Validation Failure — Missing fields

```
════════════════════════════════════════════════════════════════════════
  TEST: Validation Failure — Missing fields
  Input: "I want to travel somewhere"
────────────────────────────────────────────────────────────────────────
  Live execution:

    ▶  Parser
    ✓  Parser  0.2ms
    ▶  Validator
    ✓  Validator  0.0ms
    ▶  ProviderA (AirFrance)  [parallel]
    ▶  ProviderB (Delta)  [parallel]
    ▶  ProviderC (United)  [parallel]
    ✓  ProviderA (AirFrance)  101.2ms
    ✓  ProviderC (United)  121.1ms
    ✓  ProviderB (Delta)  150.6ms
    ▶  Aggregator
    ✓  Aggregator  0.0ms
    ▶  Formatter
    ✓  Formatter  0.0ms

────────────────────────────────────────────────────────────────────────
  RESULT:
    I need a bit more information to find your flight.
    Could you please provide: date, origin, trip_type?

────────────────────────────────────────────────────────────────────────
  EXECUTION TRACE
────────────────────────────────────────────────────────────────────────
  Node                       Status       Duration       Attempts       Parallel
────────────────────────────────────────────────────────────────────────
  Parser                     ✓  OK        0.2ms          1/1            No
  Validator                  ✓  OK        0.0ms          1/1            No
  ProviderA (AirFrance)      ✓  OK        101.2ms        1/3            Yes
  ProviderC (United)         ✓  OK        121.1ms        1/3            Yes
  ProviderB (Delta)          ✓  OK        150.6ms        1/3            Yes
  Aggregator                 ✓  OK        0.0ms          1/1            No
  Formatter                  ✓  OK        0.0ms          1/1            No
────────────────────────────────────────────────────────────────────────
  Total wall time: 151.3ms  |  3/3 providers responded
────────────────────────────────────────────────────────────────────────
```

Validator set `missing_fields: ["date", "origin", "trip_type"]`. The formatter detected this and short-circuited to a clarification response, ignoring the provider results.

> **Design note:** Providers still run here even though validation failed. An alternative is to have the validator return `status="failed"` to skip providers entirely — but that requires a `join_policy` change or a branch node. The current design keeps the graph simple at the cost of unnecessary provider calls on bad input.

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
├── main.py          # Entry point; 5 test scenarios + live output + trace table printer
├── models.py        # Core types: AgentResult, Node (with label), WorkflowGraph, RetryPolicy
├── orchestrator.py  # Kicks off entry nodes, wires EventBus, live-prints START/RETRY/END events
├── scheduler.py     # try_claim, run_node (retry/timeout/parallel detection), scheduler_handler
├── execution.py     # Shared state: context dict, node_states, node_meta (timing/attempts), frozen_view
├── event_bus.py     # Pub/sub: emit(node, execution, event, meta) — START | RETRY | END
├── workflow.py      # build_travel_graph() — declarative DAG with human-readable labels
├── mock_data.json   # Flight data + per-scenario behavior config (delays, fail modes, retry counts)
└── agents/
    ├── base.py      # Abstract Agent interface
    ├── parser.py    # ParserAgent — regex NLP → structured fields
    ├── validator.py # ValidatorAgent — required field completeness check
    ├── provider.py  # ProviderAgent — mock airline API (instantiated 3× with different names)
    ├── aggregator.py# AggregatorAgent — picks best price from successful providers
    └── formatter.py # FormatterAgent — renders full option list or clarification request
```
