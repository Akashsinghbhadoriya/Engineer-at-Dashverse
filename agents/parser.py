import re
from agents.base import Agent
from models import AgentResult

class ParserAgent(Agent):

    def __init__(self, input_node_id: str):
        self.input_node_id = input_node_id

    async def execute(self, context):
        raw = context.get(self.input_node_id) or {}
        query = raw.get("user_input", "").lower()

        data = {}

        # origin — word(s) after "from"
        origin_match = re.search(r'\bfrom\s+([a-z\s]+?)(?:\s+to\b|\s+today\b|\s+tomorrow\b|$)', query)
        if origin_match:
            data["origin"] = origin_match.group(1).strip()

        # destination — word(s) after "to"
        destination_match = re.search(r'\bto\s+([a-z\s]+?)(?:\s+today\b|\s+tomorrow\b|\s+for\b|$)', query)
        if destination_match:
            data["destination"] = destination_match.group(1).strip()

        # date — today, tomorrow, or a simple date pattern
        if "today" in query:
            data["date"] = "today"
        elif "tomorrow" in query:
            data["date"] = "tomorrow"
        else:
            date_match = re.search(r'\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\b', query)
            if date_match:
                data["date"] = date_match.group(1)

        # trip_type — explicit keywords
        for trip_type in ("vacation", "business", "holiday"):
            if trip_type in query:
                data["trip_type"] = trip_type
                break

        return AgentResult(status="success", data=data)
