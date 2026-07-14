import asyncio
from types import MappingProxyType

class Execution:

    def __init__(self, graph, context, nodestate):
        
        self.graph = graph
        self.context = context
        self.node_states = nodestate
        self.node_metadata = {}
        self._state_lock = asyncio.Lock()

    def frozen_view(self, node_id):
        filtered = {k: v for k, v in self.context.items() if k != node_id}

        return MappingProxyType(filtered)
    
    async def set_state(self, node_id, state):
        async with self._state_lock:
            self.node_states[node_id] = state
