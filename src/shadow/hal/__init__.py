"""SHADOW HAL — hardware abstraction layer."""

from .base import InferenceBackend
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
from .provider_pool import AllProvidersFailed, ProviderPool, ProviderState

__all__ = [
    "AllProvidersFailed",
    "AuthError",
    "CloudBackend",
    "CloudError",
    "CpuBackend",
    "InferenceBackend",
    "NetworkError",
    "ProviderConfig",
    "ProviderPool",
    "ProviderState",
    "RateLimitError",
    "ServerError",
]
