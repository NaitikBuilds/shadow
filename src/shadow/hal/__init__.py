"""SHADOW HAL — hardware abstraction layer."""

from .base import (
    TASK_CAPTION,
    TASK_DETAILED_CAPTION,
    TASK_OCR,
    TASK_QUERY,
    VALID_TASKS,
    InferenceBackend,
)
from .cloud_backend import (
    AuthError,
    CloudBackend,
    CloudError,
    NetworkError,
    ProviderConfig,
    RateLimitError,
    ServerError,
)
from .cpu_backend import CpuBackend
from .health import HealthMonitor
from .hybrid_backend import HybridBackend
from .moondream_backend import Moondream2Backend
from .provider_pool import AllProvidersFailed, ProviderPool, ProviderState
from .vision_router import VisionRouter, VisionRoutingError, VisionRoutingResult
from .vision_service import VisionService

__all__ = [
    "AllProvidersFailed",
    "AuthError",
    "CloudBackend",
    "CloudError",
    "CpuBackend",
    "HealthMonitor",
    "HybridBackend",
    "InferenceBackend",
    "NetworkError",
    "ProviderConfig",
    "ProviderPool",
    "ProviderState",
    "RateLimitError",
    "ServerError",
    "TASK_CAPTION",
    "TASK_DETAILED_CAPTION",
    "TASK_OCR",
    "TASK_QUERY",
    "VALID_TASKS",
    "Moondream2Backend",
    "VisionService",
    "VisionRouter",
    "VisionRoutingError",
    "VisionRoutingResult",
]
