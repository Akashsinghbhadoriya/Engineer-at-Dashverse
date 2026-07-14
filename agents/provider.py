import json, pathlib, asyncio
from agents.base import Agent
from models import AgentResult

class ProviderAgent(Agent):

    def __init__(self, name: str, validator_node_id: str, scenario: str = "happy_path"):
        self.name = name
        self.validator_node_id = validator_node_id
        self._attempt = 0  # tracks retries internally

        with open(pathlib.Path(__file__).parent.parent / "mock_data.json") as f:
            db = json.load(f)

        self.flights = db["flights"].get(name, [])
        self.behavior = db["scenarios"].get(scenario, {}).get(name, {
            "fail": False, "retryable": False, "fail_for_attempts": 0, "delay": 0.1
        })

    async def execute(self, context):
        context.get(self.validator_node_id)  # acknowledge dep
        await asyncio.sleep(self.behavior["delay"])

        self._attempt += 1

        # Transient failure: fail for N attempts, then succeed
        if self._attempt <= self.behavior["fail_for_attempts"]:
            return AgentResult(status="failed", data={}, retryable=True)

        # Permanent failure
        if self.behavior["fail"]:
            return AgentResult(status="failed", data={}, retryable=self.behavior["retryable"])

        best = min(self.flights, key=lambda x: x["price"])
        return AgentResult(status="success", data={"provider": self.name, **best})
