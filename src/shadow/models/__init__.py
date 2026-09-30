"""SHADOW model layer — download, verify, and manage local models."""

from .manager import ModelManager
from .registry import ModelSpec, MODELS

__all__ = ["ModelManager", "ModelSpec", "MODELS"]
