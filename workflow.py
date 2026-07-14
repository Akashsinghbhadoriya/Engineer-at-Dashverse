from models import Node, WorkflowGraph, RetryPolicy
from agents import ParserAgent, ValidatorAgent, ProviderAgent, AggregatorAgent, FormatterAgent


def build_travel_graph(scenario: str = "happy_path") -> WorkflowGraph:
    return WorkflowGraph([
        Node(id="parser",
             label="Parser",
             dependencies=[],
             retry_policy=RetryPolicy(),
             timeout=5.0,
             agent=ParserAgent(input_node_id="__input__")),

        Node(id="validator",
             label="Validator",
             dependencies=["parser"],
             retry_policy=RetryPolicy(),
             timeout=5.0,
             agent=ValidatorAgent(parser_node_id="parser")),

        Node(id="provider_a",
             label="ProviderA (AirFrance)",
             dependencies=["validator"],
             retry_policy=RetryPolicy(max_attempts=3),
             timeout=5.0,
             agent=ProviderAgent("AirFrance", validator_node_id="validator", scenario=scenario)),

        Node(id="provider_b",
             label="ProviderB (Delta)",
             dependencies=["validator"],
             retry_policy=RetryPolicy(max_attempts=3),
             timeout=5.0,
             agent=ProviderAgent("Delta", validator_node_id="validator", scenario=scenario)),

        Node(id="provider_c",
             label="ProviderC (United)",
             dependencies=["validator"],
             retry_policy=RetryPolicy(max_attempts=3),
             timeout=5.0,
             agent=ProviderAgent("United", validator_node_id="validator", scenario=scenario)),

        Node(id="aggregator",
             label="Aggregator",
             dependencies=["provider_a", "provider_b", "provider_c"],
             join_policy="ANY",
             retry_policy=RetryPolicy(),
             timeout=5.0,
             agent=AggregatorAgent(provider_node_ids=["provider_a", "provider_b", "provider_c"])),

        Node(id="formatter",
             label="Formatter",
             dependencies=["aggregator"],
             retry_policy=RetryPolicy(),
             timeout=5.0,
             agent=FormatterAgent(aggregator_node_id="aggregator")),
    ])
