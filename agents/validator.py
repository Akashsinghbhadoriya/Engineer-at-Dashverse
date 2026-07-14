import json, pathlib
from agents.base import Agent
from models import AgentResult

class ValidatorAgent(Agent):

    def __init__(self, parser_node_id: str):
        self.parser_node_id = parser_node_id

        with open(pathlib.Path(__file__).parent.parent / "mock_data.json") as f:
            db = json.load(f)

        self.required_fields = db["required_fields"]

    async def execute(self, context):
        parser_output = context.get(self.parser_node_id) or {}

        missing = []
        for expected in self.required_fields:
            if expected not in parser_output:
                missing.append(expected)

        return AgentResult(
            status="success",
            data={
                "validated": len(missing) == 0,
                "missing_fields": missing
            }
        )
