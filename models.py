from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal, Callable

@dataclass
class RetryPolicy:
    max_attempts:int = 1
    backoff_seconds: float = 1.0

@dataclass
class AgentResult:
    status: Literal["success", "failed"]
    data: dict = field(default_factory=dict) #It creates a new dict for every new instance of the class
    retryable: bool = False

class NodeState(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()

def is_terminal(state):
    return state in (NodeState.COMPLETED, NodeState.FAILED, NodeState.SKIPPED)

@dataclass
class Node:
    id: int
    dependencies: list
    retry_policy: RetryPolicy
    timeout: int
    agent: Callable
    join_policy: Literal["ALL", "ANY"] = "ALL"
    label: str = ""

class WorkflowGraph:

    def __init__(self, nodes: list):
        self.nodes = nodes

    def dependents(self, node_id):
        result = []
        for node in self.nodes:
            if node_id in node.dependencies:
                result.append(node)
        return result
    
    def entry_nodes(self):
        result = []
        for node in self.nodes:
            if not node.dependencies:
                result.append(node)
        return result