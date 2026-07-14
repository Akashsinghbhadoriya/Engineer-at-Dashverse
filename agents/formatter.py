from agents.base import Agent, AgentResult

class FormatterAgent(Agent):

    def __init__(self, aggregator_node_id: str):
        self.aggregator_node_id = aggregator_node_id

    async def execute(self, context):
        validator_output = context.get("validator") or {}
        missing = validator_output.get("missing_fields", [])

        if missing:
            response = (
                f"I need a bit more information to find your flight. "
                f"Could you please provide: {', '.join(missing)}?"
            )
            return AgentResult(status="success", data={"response": response})

        agg_output = context.get(self.aggregator_node_id) or {}

        if "response" in agg_output:
            response = agg_output["response"]
        else:
            response = (
                f"Your best flight is with {agg_output['best_provider']} "
                f"at ${agg_output['best_price']}"
            )

        return AgentResult(status="success", data={"response": response})
