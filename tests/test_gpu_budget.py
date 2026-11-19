"""GPU memory budget parsing and application (torch stubbed)."""
import sys
import types

import pytest

from inference_platform import gpu


def test_memory_fraction_parsing():
    assert gpu.memory_fraction({}) is None
    assert gpu.memory_fraction({"GPU_MEMORY_FRACTION": " "}) is None
    assert gpu.memory_fraction({"GPU_MEMORY_FRACTION": "0.45"}) == 0.45
    for bad in ("0", "1.5", "-1", "half"):
        with pytest.raises(ValueError):
            gpu.memory_fraction({"GPU_MEMORY_FRACTION": bad})


def _fake_torch(available=True, count=2):
    calls = []
    cuda = types.SimpleNamespace(
        is_available=lambda: available,
        device_count=lambda: count,
        set_per_process_memory_fraction=lambda f, d: calls.append((f, d)),
        get_device_properties=lambda d: types.SimpleNamespace(total_memory=16 * 2**30),
    )
    return types.SimpleNamespace(cuda=cuda), calls


def test_apply_memory_budget_caps_every_visible_device(monkeypatch):
    torch, calls = _fake_torch()
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert gpu.apply_memory_budget({"GPU_MEMORY_FRACTION": "0.45"}) == 0.45
    assert calls == [(0.45, 0), (0.45, 1)]


def test_apply_memory_budget_is_a_no_op_when_unset_or_without_cuda(monkeypatch):
    torch, calls = _fake_torch(available=False)
    monkeypatch.setitem(sys.modules, "torch", torch)
    assert gpu.apply_memory_budget({}) is None
    assert gpu.apply_memory_budget({"GPU_MEMORY_FRACTION": "0.45"}) is None
    assert calls == []
