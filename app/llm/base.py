from abc import ABC, abstractmethod

from app.core.exceptions import GenerationError


class LLM(ABC):
    """Minimal text-generation contract for local and test backends."""

    @abstractmethod
    def generate(self, prompt: str) -> str:
        raise NotImplementedError


class StaticLLM(LLM):
    """Deterministic backend useful for tests and CI."""

    def __init__(self, response: str = "No model response configured.") -> None:
        self.response = response

    def generate(self, prompt: str) -> str:
        return self.response
