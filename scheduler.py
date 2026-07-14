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
    attempt = 0
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
        await asyncio.sleep(node.retry_policy.backoff_seconds * attempt)

    await bus.emit(node, execution)  # exactly one emission per node, always


async def scheduler_handler(node, execution, graph, bus):
    tasks = []
    for downstream in graph.dependents(node.id):
        all_terminal, satisfied = is_ready(downstream, execution)
        if not all_terminal:
            continue  # still waiting on other deps
        if not satisfied:
            execution.node_states[downstream.id] = NodeState.SKIPPED
            tasks.append(bus.emit(downstream, execution))  # propagate skip
            continue
        if try_claim(downstream, execution):
            tasks.append(asyncio.create_task(run_node(downstream, execution, bus)))

    await asyncio.gather(*tasks)
