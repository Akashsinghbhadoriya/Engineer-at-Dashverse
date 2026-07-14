import asyncio
import time
from models import AgentResult, NodeState, is_terminal


def is_ready(node, execution):
    states = [execution.node_states[dep] for dep in node.dependencies]
    all_terminal = all(is_terminal(s) for s in states)
    if node.join_policy == "ALL":
        satisfied = all(s == NodeState.COMPLETED for s in states)
    else:  # ANY
        satisfied = any(s == NodeState.COMPLETED for s in states)
    return all_terminal, satisfied


def try_claim(node, execution):
    # asyncio is single-threaded cooperative — no await here means no interleaving possible.
    # Check-and-set is already atomic without a lock.
    if execution.node_states[node.id] == NodeState.PENDING:
        execution.node_states[node.id] = NodeState.RUNNING
        return True
    return False


async def run_node(node, execution, bus):
    view = execution.frozen_view(node.id)
    start_time = time.time()
    attempt = 0

    # Detect parallel: any other node currently RUNNING
    parallel = any(
        s == NodeState.RUNNING and nid != node.id
        for nid, s in execution.node_states.items()
    )

    await bus.emit(node, execution, event="START", meta={"parallel": parallel})

    while True:
        try:
            result = await asyncio.wait_for(node.agent.execute(view), timeout=node.timeout)
        except asyncio.TimeoutError:
            result = AgentResult(status="failed", data={}, retryable=True)

        if result.status == "success":
            execution.node_states[node.id] = NodeState.COMPLETED
            execution.context[node.id] = result.data
            break

        attempt += 1
        can_retry = attempt < node.retry_policy.max_attempts and result.retryable
        if not can_retry:
            execution.node_states[node.id] = NodeState.FAILED
            break

        await bus.emit(node, execution, event="RETRY", meta={"attempt": attempt})
        await asyncio.sleep(node.retry_policy.backoff_seconds * attempt)

    end_time = time.time()
    execution.node_meta[node.id] = {
        "start": start_time,
        "end": end_time,
        "attempts": attempt + 1,
        "parallel": parallel,
    }

    await bus.emit(node, execution, event="END")  # exactly one END per node, always


async def scheduler_handler(node, execution, graph, bus):
    tasks = []
    for downstream in graph.dependents(node.id):
        all_terminal, satisfied = is_ready(downstream, execution)
        if not all_terminal:
            continue  # still waiting on other deps
        if not satisfied:
            execution.node_states[downstream.id] = NodeState.SKIPPED
            tasks.append(bus.emit(downstream, execution, event="END"))  # propagate skip
            continue
        if try_claim(downstream, execution):
            tasks.append(asyncio.create_task(run_node(downstream, execution, bus)))

    await asyncio.gather(*tasks)
