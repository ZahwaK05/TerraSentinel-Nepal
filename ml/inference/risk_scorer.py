"""
Risk Scorer — Inference Module
================================
Loads a trained model and computes per-grid-cell risk scores with
SHAP-based feature-importance values for explainability.

Data mode: HISTORICAL | SIMULATED | LIVE  (set by caller)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import shap

logger = logging.getLogger(__name__)

RISK_HIGH_THRESHOLD = float(os.getenv("RISK_HIGH_THRESHOLD", "0.7"))
RISK_MEDIUM_THRESHOLD = float(os.getenv("RISK_MEDIUM_THRESHOLD", "0.4"))

FEATURE_NAMES = [
    "ndwi_change",
    "rainfall_72h_mm",
    "dem_slope_deg",
    "flow_accumulation_km2",
    "distance_to_river_m",
    "infrastructure_density_per_km2",
]


@dataclass
class RiskResult:
    """Risk score result for a single grid cell."""
    cell_id: str
    risk_score: float
    risk_level: str
    data_mode: str
    feature_contributions: dict[str, float]
    model_version: str
    timestamp_utc: str


def _risk_level(score: float) -> str:
    if score >= RISK_HIGH_THRESHOLD:
        return "HIGH"
    if score >= RISK_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


class RiskScorer:
    """Loads a scikit-learn model and scores grid cells with SHAP explanations.

    Args:
        model_path: Path to a joblib-serialised scikit-learn pipeline.
        model_version: Version string for auditability (e.g. "v1").
    """

    def __init__(self, model_path: Path, model_version: str = "v1") -> None:
        self.model_version = model_version
        logger.info("Loading risk model from %s (version=%s)", model_path, model_version)
        self.model = joblib.load(model_path)
        self._explainer: shap.Explainer | None = None

    def _get_explainer(self) -> shap.Explainer:
        if self._explainer is None:
            self._explainer = shap.Explainer(self.model)
        return self._explainer

    def score(
        self,
        features: pd.DataFrame,
        cell_ids: list[str],
        *,
        data_mode: str = "HISTORICAL",
        timestamp_utc: str = "unknown",
    ) -> list[RiskResult]:
        """Score a batch of grid cells.

        Args:
            features: DataFrame with columns matching FEATURE_NAMES.
            cell_ids: List of cell identifiers (same length as features).
            data_mode: HISTORICAL | SIMULATED | LIVE.
            timestamp_utc: ISO-8601 UTC timestamp for the prediction.

        Returns:
            List of RiskResult objects.
        """
        if list(features.columns) != FEATURE_NAMES:
            raise ValueError(
                f"Feature columns must be {FEATURE_NAMES}, got {list(features.columns)}"
            )

        probabilities = self.model.predict_proba(features)[:, 1]

        explainer = self._get_explainer()
        shap_values = explainer(features)

        results: list[RiskResult] = []
        for i, (cell_id, score) in enumerate(zip(cell_ids, probabilities)):
            contributions = {
                name: round(float(shap_values.values[i, j]), 4)
                for j, name in enumerate(FEATURE_NAMES)
            }
            results.append(
                RiskResult(
                    cell_id=cell_id,
                    risk_score=round(float(score), 4),
                    risk_level=_risk_level(score),
                    data_mode=data_mode,
                    feature_contributions=contributions,
                    model_version=self.model_version,
                    timestamp_utc=timestamp_utc,
                )
            )

        high_risk = sum(1 for r in results if r.risk_level == "HIGH")
        logger.info(
            "Scored %d cells — HIGH: %d, MEDIUM: %d, LOW: %d [mode=%s]",
            len(results),
            high_risk,
            sum(1 for r in results if r.risk_level == "MEDIUM"),
            sum(1 for r in results if r.risk_level == "LOW"),
            data_mode,
        )
        return results

    def to_geojson(self, results: list[RiskResult]) -> dict[str, Any]:
        """Convert scored results to a GeoJSON FeatureCollection.

        Note: grid cell geometries must be added separately by the
        geospatial module using the cell_id as a join key.
        """
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "cell_id": r.cell_id,
                        "risk_score": r.risk_score,
                        "risk_level": r.risk_level,
                        "data_mode": r.data_mode,
                        "model_version": r.model_version,
                        "timestamp_utc": r.timestamp_utc,
                        **{f"shap_{k}": v for k, v in r.feature_contributions.items()},
                    },
                    "geometry": None,  # populated downstream
                }
                for r in results
            ],
        }
