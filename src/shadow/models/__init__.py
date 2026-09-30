"""SHADOW model layer — download, verify, and manage local models."""

from .manager import ModelManager
from .registry import MODELS, ModelSpec

__all__ = ["ModelManager", "ModelSpec", "MODELS"]
