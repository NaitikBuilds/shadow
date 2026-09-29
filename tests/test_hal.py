import pytest

from shadow.hal.base import InferenceBackend
from shadow.hal.cpu_backend import CpuBackend


@pytest.mark.slow
def test_cpu_backend_is_inference_backend():
    assert issubclass(CpuBackend, InferenceBackend)
