# Agent Orchestrator: Conversational Agent Chain

**Focus:** Agent orchestration + parallel execution + error handling

## Problem Statement

Build an agent orchestration system that processes user requests through a chain of specialized agents. Each agent performs a specific task and passes context to the next agent in the chain. The orchestrator should manage the conversation flow, handle errors, and support agent collaboration.

## Scenario

You're building a **Travel Planning Assistant** that uses multiple specialized agents working together to:
- Understand natural language travel requests
- Extract and validate required information
- **Fetch travel options from multiple providers in parallel** (mock API calls)
- Compare and select best options
- Return a formatted response to the user

**Your task**: Design the agent architecture and implement the orchestration system.

### Example Flow (One Possible Design)

```
User Input: "Book me a flight to Paris next Friday"

┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Sequential Processing                              │
├─────────────────────────────────────────────────────────────┤
│ Parser Agent (50ms)                                         │
│   → Extracts: destination, date, origin, type              │
│                                                              │
│ Validator Agent (20ms)                                      │
│   → Validates: all required fields present                 │
│   → Output: {destination: "Paris", date: "2026-01-31",     │
│              origin: "NYC", type: "flight"}                 │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: PARALLEL Execution                                 │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│ │ Provider A Agent│  │ Provider B Agent│  │Provider C Agt│ │
│ │   (320ms)       │  │   (180ms)       │  │  (250ms)     │ │
│ │ Air France $450 │  │ Delta $520      │  │ United $480  │ │
│ └─────────────────┘  └─────────────────┘  └──────────────┘ │
│         │                     │                    │         │
│         └──────────┬──────────┴────────────────────┘         │
└────────────────────┼─────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: Sequential Processing                              │
├─────────────────────────────────────────────────────────────┤
│ Aggregator Agent (30ms)                                     │
│   → Collects 3 results, selects best (cheapest)            │
│                                                              │
│ Formatter Agent (10ms)                                      │
│   → Formats user response                                   │
└─────────────────────────────────────────────────────────────┘

Final Output: "I found 3 flights to Paris on Jan 31. Best option:
               Air France $450 (7h 30m direct)"

Total Time: ~410ms (vs ~660ms if sequential)
```

### Example: Handling Partial Failure

```
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: PARALLEL Execution with Failure                    │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│ │ Provider A Agent│  │ Provider B Agent│  │Provider C Agt│ │
│ │   (320ms)       │  │   TIMEOUT       │  │  (250ms)     │ │
│ │ Air France $450 │  │     ❌ FAILED    │  │ United $480  │ │
│ └─────────────────┘  └─────────────────┘  └──────────────┘ │
│         │                     X                    │         │
│         └──────────┬──────────┴────────────────────┘         │
└────────────────────┼─────────────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ Aggregator Agent                                            │
│   → Received 2 of 3 results (Provider B failed)            │
│   → Decision: Continue with 2 results (best-effort)        │
│   → Logs failure but doesn't abort                         │
└─────────────────────────────────────────────────────────────┘

Final Output: "I found 2 flights to Paris on Jan 31. Best option:
               Air France $450 (7h 30m direct)
               Note: Not all providers responded"
```

**Your design must handle**: What if 0, 1, 2, or 3 providers succeed?

### Required Capabilities

Your system must handle:
- Extract structured information from natural language
- Validate data and handle missing information
- **Execute independent agents in parallel** (e.g., multiple provider lookups)
- Aggregate results from parallel agents
- Format user-friendly responses
- Handle errors and timeouts (what if one provider is slow/fails?)

**How you organize these capabilities into agents is up to you, but parallel execution is required.**

## Core Requirements

### 1. Agent Interface
Each agent should implement a common interface:
- Accept input context (from previous agent or user)
- Process and transform the data
- Return output context (for next agent)
- Support error states

### 2. Orchestrator
The orchestrator should:
- Define agent chains (order of execution)
- Execute agents sequentially when dependent
- **Execute independent agents in parallel**
- Pass context between agents
- Handle agent failures gracefully (especially in parallel scenarios)
- Log the conversation flow

### 3. Context Management
- Each agent receives the full context from previous agents
- Agents can add/modify data in the context
- Context should be immutable per agent (create new version)
- Handle context from multiple parallel agents

### 4. Parallel Execution
- **Identify which agents can run concurrently** (e.g., multiple providers)
- Execute them in parallel (threads, async, or your choice)
- Wait for all to complete (or timeout)
- Aggregate results from parallel agents

### 5. Error Handling
- If an agent fails, decide: retry, skip, or abort the chain
- **Handle partial failures in parallel execution** (what if 1 of 3 providers fails?)
- Agents can return a "needs_clarification" state
- Provide meaningful error messages

### 6. Observability
- Log each agent's input, output, and execution time
- Show which agents ran in parallel
- Provide a way to inspect the full execution trace

## Design Decisions to Make

Before you start coding, consider:

1. **How many agents?** (Minimum 3 required)
   - What's the single responsibility of each agent?
   - Should parsing and validation be separate or combined?
   - How many provider agents do you need?
   - Do you need an aggregator agent?

2. **Which agents run in parallel?**
   - Which agents are independent and can run concurrently?
   - Which agents must run sequentially?
   - How do you represent this in your design?

3. **What should agents communicate?**
   - What data structure for context?
   - Immutable or mutable context?
   - How do parallel agents return results?
   - How do agents signal errors or need for clarification?

4. **How should the orchestrator work?**
   - How to express both sequential AND parallel execution?
   - How to handle failures in parallel agents? (fail-fast? best-effort?)
   - Retry logic? Timeouts?

5. **What's observable?**
   - How to debug agent chains with parallel execution?
   - How to visualize which agents ran in parallel?
   - What logs or traces to capture?

**Time Management Tips:**
- Focus on getting parallel execution working over fancy features
- A simple design with working parallelism beats a complex design without it
- Mock implementations are OK - we care about orchestration, not business logic
- If running short on time, prioritize: Core agents → Parallel execution → Error handling → Polish

## Constraints & Assumptions
- You can use any programming language
- Mock all external API calls (no real HTTP requests needed)
- Focus on architecture and orchestration, not business logic
- Agents can have simple/naive implementations
- No UI required (CLI output is fine)

## Example Test Cases
### Test Case 1: Happy Path with Parallel Execution
```
Input: "Book a flight to Tokyo for December 1st"
Expected:
- Parse and validate input
- Query 3 providers IN PARALLEL
- All succeed, aggregate results
- Return best option with comparison
```

### Test Case 2: Partial Failure in Parallel Agents
```
Scenario: Provider A and B succeed, Provider C fails (timeout/error)
Expected:
- System continues with 2 successful results
- Logs the failure but doesn't abort
- Returns results from working providers
```

### Test Case 3: All Parallel Agents Fail
```
Scenario: All 3 providers fail
Expected:
- Orchestrator detects all failures
- Returns meaningful error to user
- Doesn't hang waiting for results
```

### Test Case 4: Missing Information
```
Input: "I want to travel next month"
Expected:
- Validation phase identifies missing destination and type
- Doesn't proceed to parallel provider calls
- Requests clarification
```

## Stretch Goals (if time permits)
1. **Dynamic Chains**: Allow orchestrator to add/remove agents at runtime
2. **Agent Loop-back**: Allow agents to send requests back to previous agents
3. **Conditional Routing**: Route to different agent chains based on travel type (flight vs hotel)

## Evaluation Criteria
We'll evaluate your solution on:

1. **Design & Architecture**
   - **Agent boundaries**: Clear, logical separation of responsibilities
   - **Parallel execution design**: Which agents run in parallel and why?
   - **Trade-off reasoning**: Can you justify your design decisions?
     - Why N agents instead of N-1 or N+1?
     - What would make you split or merge agents?
   - **Extensibility**: How easy to add new providers or modify the chain?
   - **Abstractions**: Appropriate interfaces and contracts

2. **Parallel Execution**
   - **Correctly identifies** which agents can run in parallel
   - **Properly implements** concurrent execution (threads/async/etc.)
   - **Aggregates results** from parallel agents correctly
   - **Handles partial failures** gracefully
   - **Demonstrates understanding** of concurrency challenges

3. **Functionality**
   - Core orchestration works end-to-end
   - Handles all test cases (including parallel scenarios)
   - Error handling and edge cases
   - Context management

4. **Code Quality**
   - Readable and maintainable
   - Proper naming conventions
   - Well-structured code
   - Documentation of design choices

5. **Problem Solving**
   - How you approached the problem
   - Testing strategy
   - What you prioritized in 2 hours

## What We're Looking For

**Good answers:**
- "I combined parsing and validation into one agent because they share context and it reduces communication overhead"
- "The 3 provider agents run in parallel because they're independent - no provider needs data from another"
- "I use a thread pool for parallel execution with a 5-second timeout per agent to prevent hanging"
- "If 1 of 3 providers fails, I continue with the other 2 - better to show partial results than fail completely"
- "I used immutable context to prevent race conditions when parallel agents write results"

**We want to see:**
- Your reasoning process, not just the end result
- Understanding of when and why to use parallel execution
- Awareness of concurrency challenges (race conditions, deadlocks, timeouts)
- Awareness of trade-offs (no solution is perfect)
- Clean code that demonstrates orchestration AND parallel execution
- Working error handling, especially for parallel scenarios

## Submission

1. **Working code** that runs without errors
2. **README.md** with:
   - How to run your code
   - **Your agent architecture design** (diagram or description)
   - **Design decisions and trade-offs**:
     - Why did you choose N agents?
     - What is each agent's responsibility?
     - **Which agents run in parallel and why?**
     - How do you handle parallel agent failures?
     - Why not combine/split certain agents?
   - Technology choice for parallel execution (threads/async/etc.) and why
   - Any assumptions made
3. **Example output** showing:
   - Agent chain execution with parallel agents clearly visible
   - Execution trace showing timing and parallel execution
   - At least one scenario with partial failure in parallel agents
4. Be prepared to **discuss alternatives** in the follow-up review

**Good luck! Focus on clean architecture and demonstrating orchestration concepts rather than perfect business logic.**

---