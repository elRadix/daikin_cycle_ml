"""Per-mode baseline wrapper (Batch 11a).

Heat pumps behave very differently in Heating vs Cooling vs DHW cycles.
A single baseline blurs the modes and produces false anomalies on every
mode switch. MultiBaseline keeps one AdaptiveBaseline per mode.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from .features import VECTOR_LEN, VECTOR_LEN_LEGACY
from .baseline import (
    AdaptiveBaseline,
    DEFAULT_ALPHA,
    DEFAULT_MIN_SAMPLES_OUTLIER_SKIP,
    DEFAULT_OUTLIER_Z,
)

_LOGGER = logging.getLogger(__name__)

MODE_UNKNOWN = "unknown"


class MultiBaseline:
    """One AdaptiveBaseline per operation mode."""

    def __init__(
        self,
        dim: int,
        alpha: float = DEFAULT_ALPHA,
        outlier_skip_z: float = DEFAULT_OUTLIER_Z,
        min_samples_before_skip: int = DEFAULT_MIN_SAMPLES_OUTLIER_SKIP,
    ) -> None:
        self._dim = int(dim)
        self._alpha = float(alpha)
        self._outlier_skip_z = float(outlier_skip_z)
        self._min_samples_before_skip = int(min_samples_before_skip)
        self._baselines: dict[str, AdaptiveBaseline] = {}

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def alpha(self) -> float:
        return self._alpha

    def modes(self) -> list[str]:
        return sorted(self._baselines.keys())

    def get(self, mode: str | None) -> AdaptiveBaseline:
        key = mode if isinstance(mode, str) and mode else MODE_UNKNOWN
        b = self._baselines.get(key)
        if b is None:
            b = AdaptiveBaseline(
                self._dim,
                alpha=self._alpha,
                outlier_skip_z=self._outlier_skip_z,
                min_samples_before_skip=self._min_samples_before_skip,
            )
            self._baselines[key] = b
        return b

    def update(self, mode: str | None, vector: list[float]) -> bool:
        return self.get(mode).update(vector)

    def z_scores(self, mode, vector):
        return self.get(mode).z_scores(vector)

    def max_abs_z(self, mode, vector):
        return self.get(mode).max_abs_z(vector)

    def is_anomaly(self, mode, vector, threshold: float = 3.0) -> bool:
        return self.get(mode).is_anomaly(vector, threshold)

    def top_dim(self, mode, vector):
        return self.get(mode).top_dim(vector)

    def sample_count(self, mode) -> int:
        return self.get(mode).sample_count

    def reset(self, mode: str | None = None) -> None:
        if mode is None:
            self._baselines.clear()
            return
        key = mode if isinstance(mode, str) and mode else MODE_UNKNOWN
        self._baselines.pop(key, None)

    def total_samples(self) -> int:
        return sum(b.sample_count for b in self._baselines.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "dim": self._dim,
            "alpha": self._alpha,
            "outlier_skip_z": self._outlier_skip_z,
            "min_samples_before_skip": self._min_samples_before_skip,
            "baselines": {
                k: v.to_dict() for k, v in self._baselines.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MultiBaseline":
        saved_dim = data.get("dim")
        # Only reset for KNOWN obsolete dims. Other dims (small test baselines
        # or future-proof values) load normally.
        if not isinstance(saved_dim, int) or saved_dim in (VECTOR_LEN_LEGACY, 11):
            _LOGGER.warning(
                "MultiBaseline state has dim=%s (obsolete/missing), "
                "resetting to %d-dim",
                saved_dim, VECTOR_LEN,
            )
            return cls(VECTOR_LEN)
        mb = cls(
            saved_dim,
            alpha=float(data.get("alpha", DEFAULT_ALPHA)),
            outlier_skip_z=float(data.get("outlier_skip_z", DEFAULT_OUTLIER_Z)),
            min_samples_before_skip=int(
                data.get("min_samples_before_skip",
                         DEFAULT_MIN_SAMPLES_OUTLIER_SKIP)
            ),
        )
        for key, sub in (data.get("baselines") or {}).items():
            mb._baselines[key] = AdaptiveBaseline.from_dict(sub)
        return mb
    
    

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "MultiBaseline":
        import json
        return cls.from_dict(json.loads(raw))
