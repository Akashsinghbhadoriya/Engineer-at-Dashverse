from agents.base import Agent
from models import AgentResult


class FormatterAgent(Agent):

    def __init__(self, aggregator_node_id: str):
        self.aggregator_node_id = aggregator_node_id

    async def execute(self, context):
        validator_output = context.get("validator") or {}
        missing = validator_output.get("missing_fields", [])

        if missing:
            return AgentResult(status="success", data={
                "response": (
                    f"I need a bit more information to find your flight. "
                    f"Could you please provide: {', '.join(missing)}?"
                ),
                "missing_fields": missing,
            })

        agg = context.get(self.aggregator_node_id) or {}

        if "response" in agg:
            # aggregator had no options
            return AgentResult(status="success", data={"response": agg["response"]})

        best = agg.get("best_provider", "?")
        best_price = agg.get("best_price", 0)
        all_options = agg.get("all_options", [])

        lines = [f"Best option: {best}  ${best_price:.0f}  ({_duration(all_options, best)})"]
        others = [o for o in all_options if o["provider"] != best]
        if others:
            lines.append("Other options:")
            for o in others:
                lines.append(f"  • {o['provider']}  ${o['price']:.0f}  ({o['duration']})")

        return AgentResult(status="success", data={
            "response": "\n".join(lines),
            "best_provider": best,
            "best_price": best_price,
            "all_options": all_options,
            "providers_responded": len(all_options),
        })


def _duration(options, provider):
    for o in options:
        if o["provider"] == provider:
            return o["duration"]
    return "?"
