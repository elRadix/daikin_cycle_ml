"""Online baseline statistics for ML anomaly detection (Batch 7a + 11a).

Pure Python, no numpy.

Baseline            - Welford exact mean/std (v1, backward-compat).
AdaptiveBaseline    - EWMA with optional outlier exclusion (v2, default).
baseline_from_dict  - factory dispatch based on "type" field.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any, Mapping

_LOGGER = logging.getLogger(__name__)

DEFAULT_Z_THRESHOLD = 3.0
MIN_SAMPLES_FOR_Z = 3

# Batch 11a additions
DEFAULT_ALPHA = 0.01
DEFAULT_OUTLIER_Z = 5.0
DEFAULT_MIN_SAMPLES_OUTLIER_SKIP = 20
MIN_ALPHA = 0.001
MAX_ALPHA = 1.0


class Baseline:
    """Exact Welford mean/std. Do not change behaviour (v1 compat)."""

    def __init__(self, dim: int) -> None:
        if dim <= 0:
            raise ValueError("dim must be > 0")
        self._dim = dim
        self._n = 0
        self._mean: list[float] = [0.0] * dim
        self._m2: list[float] = [0.0] * dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def sample_count(self) -> int:
        return self._n

    @property
    def mean(self) -> list[float]:
        return list(self._mean)

    @property
    def std(self) -> list[float]:
        if self._n < 2:
            return [0.0] * self._dim
        return [math.sqrt(max(0.0, m2 / (self._n - 1))) for m2 in self._m2]

    def fit(self, vectors: list[list[float]]) -> "Baseline":
        self._n = 0
        self._mean = [0.0] * self._dim
        self._m2 = [0.0] * self._dim
        for v in vectors:
            self.update(v)
        return self

    def update(self, vector: list[float]) -> bool:
        if len(vector) != self._dim:
            raise ValueError(
                f"vector dim {len(vector)} != baseline dim {self._dim}"
            )
        self._n += 1
        for i, x in enumerate(vector):
            delta = x - self._mean[i]
            self._mean[i] += delta / self._n
            delta2 = x - self._mean[i]
            self._m2[i] += delta * delta2
        return True

    def z_scores(self, vector: list[float]) -> list[float]:
        if len(vector) != self._dim:
            raise ValueError("dim mismatch")
        if self._n < MIN_SAMPLES_FOR_Z:
            return [0.0] * self._dim
        std = self.std
        out: list[float] = []
        for i, x in enumerate(vector):
            s = std[i]
            if s <= 0.0:
                out.append(0.0)
            else:
                out.append((x - self._mean[i]) / s)
        return out

    def max_abs_z(self, vector: list[float]) -> float:
        zs = self.z_scores(vector)
        return max((abs(z) for z in zs), default=0.0)

    def is_anomaly(
        self, vector: list[float], threshold: float = DEFAULT_Z_THRESHOLD
    ) -> bool:
        return self.max_abs_z(vector) > float(threshold)

    def top_dim(self, vector: list[float]) -> int | None:
        zs = self.z_scores(vector)
        if not zs:
            return None
        best_i, best = -1, 0.0
        for i, z in enumerate(zs):
            az = abs(z)
            if az > best:
                best, best_i = az, i
        return best_i if best_i >= 0 else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "welford",
            "dim": self._dim,
            "n": self._n,
            "mean": self.mean,
            "m2": list(self._m2),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Baseline":
        b = cls(int(data["dim"]))
        b._n = int(data.get("n", 0))
        b._mean = [float(x) for x in data.get("mean", [])] or [0.0] * b._dim
        b._m2 = [float(x) for x in data.get("m2", [])] or [0.0] * b._dim
        return b

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, raw: str) -> "Baseline":
        return cls.from_dict(json.loads(raw))


class AdaptiveBaseline(Baseline):
    """EWMA baseline with optional outlier exclusion (Batch 11a).

    EWMA mean:   m_t = (1 - a) * m_(t-1) + a * x_t
    EWMA var:    v_t = (1 - a) * (v_(t-1) + a * (x_t - m_(t-1))^2)

    alpha = 1.0 degenerates to a degenerate one-point baseline.
    alpha = 0.01 -> effective window ~ 100 samples (seasonal adaptation).
    """

    def __init__(
        self,
        dim: int,
        alpha: float = DEFAULT_ALPHA,
        outlier_skip_z: float = DEFAULT_OUTLIER_Z,
        min_samples_before_skip: int = DEFAULT_MIN_SAMPLES_OUTLIER_SKIP,
    ) -> None:
        super().__init__(dim)
        self._alpha = min(MAX_ALPHA, max(MIN_ALPHA, float(alpha)))
        self._outlier_skip_z = float(outlier_skip_z)
        self._min_samples_before_skip = int(min_samples_before_skip)

    @property
    def alpha(self) -> float:
        return self._alpha

    @property
    def outlier_skip_z(self) -> float:
        return self._outlier_skip_z

    @property
    def std(self) -> list[float]:
        if self._n < 2:
            return [0.0] * self._dim
        return [math.sqrt(max(0.0, m2)) for m2 in self._m2]

    def fit(self, vectors: list[list[float]]) -> "AdaptiveBaseline":
        self._n = 0
        self._mean = [0.0] * self._dim
        self._m2 = [0.0] * self._dim
        for v in vectors:
            self.update(v)
        return self

    def update(self, vector: list[float]) -> bool:
        """Update with EWMA. Returns False if skipped as outlier."""
        if len(vector) != self._dim:
            raise ValueError("dim mismatch")
        if (
            self._outlier_skip_z > 0.0
            and self._n >= self._min_samples_before_skip
        ):
            z = self.max_abs_z(vector)
            if z > self._outlier_skip_z:
                _LOGGER.debug(
                    "Baseline: skipping outlier z=%.2f > %.2f",
                    z, self._outlier_skip_z,
                )
                return False
        a = self._alpha
        if self._n == 0:
            for i, x in enumerate(vector):
                self._mean[i] = x
                self._m2[i] = 0.0
            self._n = 1
            return True
        for i, x in enumerate(vector):
            old_mean = self._mean[i]
            new_mean = (1.0 - a) * old_mean + a * x
            new_m2 = (1.0 - a) * (
                self._m2[i] + a * (x - old_mean) ** 2
            )
            self._mean[i] = new_mean
            self._m2[i] = new_m2
        self._n += 1
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "ewma",
            "dim": self._dim,
            "n": self._n,
            "mean": self.mean,
            "m2": list(self._m2),
            "alpha": self._alpha,
            "outlier_skip_z": self._outlier_skip_z,
            "min_samples_before_skip": self._min_samples_before_skip,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdaptiveBaseline":
        b = cls(
            int(data["dim"]),
            alpha=float(data.get("alpha", DEFAULT_ALPHA)),
            outlier_skip_z=float(data.get("outlier_skip_z", DEFAULT_OUTLIER_Z)),
            min_samples_before_skip=int(
                data.get("min_samples_before_skip",
                         DEFAULT_MIN_SAMPLES_OUTLIER_SKIP)
            ),
        )
        b._n = int(data.get("n", 0))
        b._mean = [float(x) for x in data.get("mean", [])] or [0.0] * b._dim
        b._m2 = [float(x) for x in data.get("m2", [])] or [0.0] * b._dim
        return b


def baseline_from_dict(data: Mapping[str, Any]) -> Baseline:
    """Dispatch to the correct class based on the 'type' field."""
    if data.get("type") == "ewma":
        return AdaptiveBaseline.from_dict(data)
    return Baseline.from_dict(data)
