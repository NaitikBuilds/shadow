from abc import ABC, abstractmethod


class InferenceBackend(ABC):
    """Hardware-agnostic inference interface.

    Every backend (CPU, Snapdragon NPU, GPU) implements this so the rest of
    SHADOW never needs to know which hardware it runs on.
    """

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        ...

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        ...

    @property
    @abstractmethod
    def info(self) -> dict:
        ...