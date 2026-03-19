"""
chronoai/ml_pipeline/anomaly_detector.py
Isolation Forest anomaly detector for timetable quality audit.

Detects structurally anomalous timetables (e.g. all labs on one day,
no Saturday usage, extreme faculty load imbalance) by learning the
distribution of "normal" timetables and flagging outliers.

Used by QualityAuditAgent to flag suspicious schedules for human review.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from chronoai.ml_pipeline.feature_engineering import FeatureEngineer

logger = logging.getLogger(__name__)

MODEL_FILENAME = "anomaly_detector.joblib"

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

try:
    from sklearn.ensemble import IsolationForest
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


# Heuristic anomaly thresholds for when the model is not trained
_HEURISTIC_THRESHOLDS = {
    "conflict_rate":       0.15,   # >15% conflict rate = anomalous
    "slot_utilization_rate": 0.30, # <30% utilization = anomalous
    "free_slot_rate":      0.60,   # >60% free = anomalous (ghost timetable)
    "saturday_utilization": 0.0,   # ==0 on Saturday = possible flag
    "faculty_load_variance": 200,  # variance > 200 = extreme imbalance
}


def _heuristic_is_anomaly(features: list[float]) -> tuple[bool, str]:
    """
    Simple threshold-based anomaly detection (no trained model needed).
    Returns (is_anomaly, reason).
    """
    conflict_rate       = features[4]
    utilization         = features[0]
    free_rate           = features[13]
    saturday_util       = features[7]
    load_variance       = features[5]
    section_count       = features[6]

    if conflict_rate > _HEURISTIC_THRESHOLDS["conflict_rate"]:
        return True, f"High conflict rate: {conflict_rate:.1%}"
    if utilization < _HEURISTIC_THRESHOLDS["slot_utilization_rate"]:
        return True, f"Very low slot utilization: {utilization:.1%}"
    if free_rate > _HEURISTIC_THRESHOLDS["free_slot_rate"]:
        return True, f"Excessive free slots: {free_rate:.1%}"
    if section_count > 5 and saturday_util <= 0.0:
        return True, "No Saturday usage in a large multi-section timetable"
    if load_variance > _HEURISTIC_THRESHOLDS["faculty_load_variance"]:
        return True, f"Extreme faculty load imbalance (variance={load_variance:.0f})"

    return False, ""


class AnomalyDetector:
    """
    Isolation Forest anomaly detector for timetable feature vectors.

    Usage:
        ad = AnomalyDetector(models_dir="./models")
        ad.fit(list_of_normal_timetable_dicts)

        result = ad.predict_one(timetable_dict)
        # result = {"is_anomaly": bool, "anomaly_score": float, "reason": str}

        results = ad.predict(list_of_timetable_dicts)
        # list of above dicts
    """

    def __init__(
        self,
        models_dir: str = "./models",
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
    ) -> None:
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._model_path = self._models_dir / MODEL_FILENAME
        self._feature_engineer = FeatureEngineer()
        self._contamination = contamination
        self._n_estimators = n_estimators
        self._random_state = random_state
        self._model: Any = None
        self._model_trained = False

        self._try_load_model()

    def _try_load_model(self) -> None:
        if not _JOBLIB_AVAILABLE:
            return
        if self._model_path.exists():
            try:
                self._model = joblib.load(str(self._model_path))
                self._model_trained = True
                logger.info("AnomalyDetector: loaded model from %s", self._model_path)
            except Exception as exc:
                logger.warning("AnomalyDetector: failed to load model: %s", exc)

    def fit(self, timetable_dicts: list[dict[str, Any]]) -> "AnomalyDetector":
        """
        Fit the Isolation Forest on a collection of timetable dicts.

        Args:
            timetable_dicts: List of "normal" timetable feature dicts
        """
        if not _SKLEARN_AVAILABLE:
            logger.warning("scikit-learn not available — anomaly detection will use heuristics")
            return self

        raw = [self._feature_engineer.extract_raw(d) for d in timetable_dicts]
        X = np.array(raw, dtype=float)

        model = IsolationForest(
            n_estimators=self._n_estimators,
            contamination=self._contamination,
            random_state=self._random_state,
            n_jobs=-1,
        )
        model.fit(X)
        self._model = model
        self._model_trained = True

        if _JOBLIB_AVAILABLE:
            try:
                joblib.dump(model, str(self._model_path))
                logger.info("AnomalyDetector: model saved to %s", self._model_path)
            except Exception as exc:
                logger.warning("AnomalyDetector: could not save model: %s", exc)

        return self

    def predict_one(self, timetable_dict: dict[str, Any]) -> dict[str, Any]:
        """
        Detect whether a single timetable is anomalous.

        Returns:
            {
                "is_anomaly": bool,
                "anomaly_score": float,    # 0–1, higher = more anomalous
                "reason": str,             # human-readable explanation
            }
        """
        raw = self._feature_engineer.extract_raw(timetable_dict)

        if self._model_trained and self._model is not None:
            try:
                X = np.array([raw], dtype=float)
                # IsolationForest predict: -1 = anomaly, 1 = normal
                label = int(self._model.predict(X)[0])
                # decision_function: lower = more anomalous (negative)
                score_raw = float(self._model.decision_function(X)[0])
                # Normalize to 0–1 where 1 = most anomalous
                anomaly_score = max(0.0, min(1.0, 0.5 - score_raw))
                is_anomaly = label == -1
                reason = (
                    f"Model anomaly score: {anomaly_score:.3f}" if is_anomaly
                    else "Normal timetable structure"
                )
                return {
                    "is_anomaly": is_anomaly,
                    "anomaly_score": round(anomaly_score, 4),
                    "reason": reason,
                }
            except Exception as exc:
                logger.warning("IsolationForest predict failed, using heuristics: %s", exc)

        # Heuristic fallback
        is_anom, reason = _heuristic_is_anomaly(raw)
        anomaly_score = 0.8 if is_anom else 0.1
        return {
            "is_anomaly": is_anom,
            "anomaly_score": anomaly_score,
            "reason": reason or "No anomalies detected (heuristic check)",
        }

    def predict(self, timetable_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect anomalies in a batch of timetables."""
        return [self.predict_one(d) for d in timetable_dicts]

    @property
    def is_trained(self) -> bool:
        return self._model_trained
