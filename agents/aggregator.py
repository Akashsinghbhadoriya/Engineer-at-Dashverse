from agents.base import Agent, AgentResult

class AggregatorAgent(Agent):

    def __init__(self, provider_node_ids: list[str]):
        self.provider_node_ids = provider_node_ids

    async def execute(self, context):
        options = [context.get(node_id) for node_id in self.provider_node_ids]
        options = [o for o in options if o is not None]

        if not options:
            return AgentResult(
                status="success",
                data={"response": "No providers available"}
            )

        best = min(options, key=lambda o: o["price"])

        return AgentResult(
            status="success",
            data={
                "best_provider": best["provider"],
                "best_price": best["price"],
                "all_options": options
            }
        )
