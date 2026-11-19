"""Per-process GPU memory budget for processes that share a GPU.

The k3s NVIDIA device plugin time-slices each physical GPU into several
``nvidia.com/gpu`` units (``replicas`` in deploy/k8s/addons/nvidia-device-plugin.yaml).
Time-slicing shares compute but not memory: two pods on one card can each
take as much as they like, and the second to grow gets "CUDA out of memory".
PyTorch also keeps freed memory cached, so a process that once peaked stays at
that peak, and auto batch sizing (auto_batch.find_max_batch_size) fills
whatever happens to be free at the time it probes.

``GPU_MEMORY_FRACTION`` caps this process's share of the card, so each slot
has a fixed budget no neighbour can take: set it to a little under
1 / replicas (0.45 for two slots per card; the rest covers each process's
CUDA context). Within the cap PyTorch frees its cache and retries before it
reports out of memory, and batch-size probes size against the budget, not
against what a neighbour left free.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

logger = logging.getLogger(__name__)

ENV_NAME = "GPU_MEMORY_FRACTION"


def memory_fraction(env: Mapping[str, str] = os.environ) -> Optional[float]:
    """The configured fraction, or None when unset (no cap)."""
    raw = (env.get(ENV_NAME) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{ENV_NAME} must be a number between 0 and 1, got {raw!r}") from exc
    if not 0 < value <= 1:
        raise ValueError(f"{ENV_NAME} must be between 0 and 1, got {raw!r}")
    return value


def apply_memory_budget(env: Mapping[str, str] = os.environ) -> Optional[float]:
    """Cap this process's GPU memory at ``GPU_MEMORY_FRACTION`` of each visible card.

    Call once at start-up, before any model is loaded. Returns the fraction
    applied, or None when unset or when there is no CUDA device.
    """
    fraction = memory_fraction(env)
    if fraction is None:
        return None
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    for device in range(torch.cuda.device_count()):
        torch.cuda.set_per_process_memory_fraction(fraction, device)
    total = torch.cuda.get_device_properties(0).total_memory / 2**30
    logger.info(
        "GPU memory budget: %.0f%% of %.1f GiB = %.1f GiB per process",
        fraction * 100,
        total,
        fraction * total,
    )
    return fraction
