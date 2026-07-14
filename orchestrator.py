import asyncio, time
from models import NodeState
from execution import Execution
from event_bus import EventBus
from scheduler import try_claim, run_node, scheduler_handler


class Orchestrator:

    async def run(self, graph, user_input: str) -> dict:

        context = {"__input__": {"user_input": user_input}}
        node_states = {node.id: NodeState.PENDING for node in graph.nodes}
        execution = Execution(graph=graph, context=context, nodestate=node_states)
        trace = []
        bus = EventBus()

        async def trace_handler(node, execution, event, meta):
            label = node.label or node.id

            if event == "START":
                tag = "  [parallel]" if meta.get("parallel") else ""
                print(f"    ▶  {label}{tag}")

            elif event == "RETRY":
                attempt = meta.get("attempt", "?")
                print(f"    ↺  {label}  retrying ({attempt}/{node.retry_policy.max_attempts})")

            elif event == "END":
                state = execution.node_states[node.id]
                m = execution.node_meta.get(node.id, {})
                duration_ms = (m.get("end", 0) - m.get("start", 0)) * 1000
                attempts = m.get("attempts", 1)

                if state == NodeState.COMPLETED:
                    print(f"    ✓  {label}  {duration_ms:.1f}ms")
                elif state == NodeState.FAILED:
                    print(f"    ✗  {label}  FAILED after {attempts} attempt(s)")
                elif state == NodeState.SKIPPED:
                    print(f"    —  {label}  SKIPPED")

                trace.append({
                    "node": node.id,
                    "label": label,
                    "state": state.name,
                    "duration_ms": duration_ms,
                    "attempts": attempts,
                    "max_attempts": node.retry_policy.max_attempts,
                    "parallel": m.get("parallel", False),
                    "timestamp": time.time(),
                })

        async def schedule_handler(node, execution, event, meta):
            if event == "END":
                await scheduler_handler(node, execution, graph, bus)

        bus.subscribe(trace_handler)
        bus.subscribe(schedule_handler)

        tasks = []
        for node in graph.entry_nodes():
            if try_claim(node, execution):
                tasks.append(asyncio.create_task(run_node(node, execution, bus)))

        await asyncio.gather(*tasks)

        return {
            "response": execution.context.get("formatter", {}).get("response"),
            "trace": trace,
            "context": execution.context,
        }
