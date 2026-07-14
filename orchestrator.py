import asyncio, time
from models import NodeState
from execution import Execution
from event_bus import EventBus
from scheduler import try_claim, run_node, scheduler_handler

class Orchestrator:

    async def run(self, graph, user_input: str) -> dict:

        context = {"__input__": {"user_input": user_input}}
        node_states = {node.id: NodeState.PENDING for node in graph.nodes}
        execution = Execution(graph=graph, 
                              context=context,
                              nodestate=node_states
                            )
        trace = []
        bus = EventBus()

        async def trace_handler(node, execution):
            trace.append({
                "node": node.id,
                "state": execution.node_states[node.id].name,
                "timestamp": time.time()
            })

        async def schedule_handler(node, execution):
            await scheduler_handler(node, execution, graph, bus)

        bus.subscribe(trace_handler)
        bus.subscribe(schedule_handler)

        tasks = []
        for node in graph.entry_nodes():
            if try_claim(node, execution):
                tasks.append(asyncio.create_task(run_node(node, execution, bus)))
        
        await asyncio.gather(*tasks)

        return {
            "response": execution.context.get("formatter",{}).get("response"),
            "trace": trace,
            "context": execution.context
        }