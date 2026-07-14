from abc import ABC, abstractmethod
from types import MappingProxyType
from models import AgentResult

class Agent(ABC):

    @abstractmethod
    async def execute(self, context: MappingProxyType) -> AgentResult:
        pass