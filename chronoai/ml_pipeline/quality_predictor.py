"""
chronoai/ml_pipeline/quality_predictor.py
XGBoost-based timetable quality predictor.

Predicts a quality score (0–100) for a generated timetable.
Falls back to a deterministic heuristic formula when the trained model file
is not available (i.e. before any training data is collected).

Training data comes from MLTrainingData rows written by the scheduler after
each successful generation run.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

from chronoai.ml_pipeline.feature_engineering import FeatureEngineer

logger = logging.getLogger(__name__)

MODEL_FILENAME = "quality_predictor.joblib"

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False

try:
    from xgboost import XGBRegressor
    _XGBOOST_AVAILABLE = True
except ImportError:
    _XGBOOST_AVAILABLE = False


def _heuristic_score(features: list[float]) -> float:
    """
    Deterministic quality score from raw features — used when model not trained.
    Score = 100 × weighted combination of key indicators.

    Feature indices (see feature_engineering.py FEATURE_NAMES):
      F01=0 slot_utilization_rate, F04=3 conflict_count, F05=4 conflict_rate,
      F11=10 lunch_consistency_score, F13=12 avg_lab_pair_integrity,
      F14=13 free_slot_rate, F19=18 slot_type_entropy
    """
    utilization   = features[0]   # higher = better (max ~0.85 in real data)
    conflict_rate = features[4]   # lower = better
    lunch_cons    = features[10]  # 1.0 = perfect
    lab_integrity = features[12]  # 1.0 = all labs paired
    free_rate     = features[13]  # moderate is OK, very high = bad
    entropy       = features[18]  # moderate entropy is good

    # Conflict penalty: each 1% conflict rate removes 5 points
    conflict_penalty = min(50, conflict_rate * 500)

    # Utilization bonus: 85% utilization → full 30 pts
    util_bonus = min(30, utilization * 35)

    # Consistency bonuses
    lunch_bonus     = lunch_cons * 15
    lab_bonus       = lab_integrity * 15
    free_penalty    = max(0, (free_rate - 0.3) * 20)   # penalty if >30% free
    entropy_bonus   = min(10, entropy * 3)             # reward diversity

    score = 30 + util_bonus + lunch_bonus + lab_bonus + entropy_bonus - conflict_penalty - free_penalty
    return float(max(0.0, min(100.0, score)))


class QualityPredictor:
    """
    Predicts timetable quality score (0–100).

    Usage:
        qp = QualityPredictor(models_dir="./models")
        score = qp.predict(timetable_dict)   # always works (heuristic fallback)

        # After collecting training data:
        X, y = ..., ...
        qp.train(X, y)                       # fits XGBoost, saves model
        score = qp.predict(timetable_dict)   # now uses trained model
    """

    def __init__(self, models_dir: str = "./models") -> None:
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._model_path = self._models_dir / MODEL_FILENAME
        self._feature_engineer = FeatureEngineer()
        self._model: Any = None
        self._model_trained = False

        # Try to load a pre-existing model
        self._try_load_model()

    def _try_load_model(self) -> None:
        if not _JOBLIB_AVAILABLE:
            return
        if self._model_path.exists():
            try:
                self._model = joblib.load(str(self._model_path))
                self._model_trained = True
                logger.info("QualityPredictor: loaded model from %s", self._model_path)
            except Exception as exc:
                logger.warning("QualityPredictor: failed to load model: %s", exc)

    def train(self, X: np.ndarray, y: np.ndarray) -> "QualityPredictor":
        """
        Train the XGBoost regressor.

        Args:
            X: Feature matrix (N, 20) from FeatureEngineer.fit_transform()
            y: Quality score labels (N,) in range 0–100
        """
        if not _XGBOOST_AVAILABLE:
            logger.warning("XGBoost not available — model will use heuristic fallback")
            return self
        if not _JOBLIB_AVAILABLE:
            logger.warning("joblib not available — model will not be persisted")

        model = XGBRegressor(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            verbosity=0,
        )
        model.fit(X, y)
        self._model = model
        self._model_trained = True

        # Persist model
        if _JOBLIB_AVAILABLE:
            try:
                joblib.dump(model, str(self._model_path))
                logger.info("QualityPredictor: model saved to %s", self._model_path)
            except Exception as exc:
                logger.warning("QualityPredictor: could not save model: %s", exc)

        return self

    def predict(self, timetable_dict: dict[str, Any]) -> float:
        """
        Predict quality score for a single timetable.

        Returns:
            float in [0, 100]
        """
        raw = self._feature_engineer.extract_raw(timetable_dict)

        if self._model_trained and self._model is not None:
            try:
                X = np.array([raw], dtype=float)
                score = float(self._model.predict(X)[0])
                return max(0.0, min(100.0, score))
            except Exception as exc:
                logger.warning("XGBoost predict failed, falling back to heuristic: %s", exc)

        return _heuristic_score(raw)

    def predict_batch(self, timetable_dicts: list[dict[str, Any]]) -> list[float]:
        """Predict quality scores for multiple timetables."""
        return [self.predict(d) for d in timetable_dicts]

    @property
    def is_trained(self) -> bool:
        return self._model_trained

    def feature_importances(self) -> dict[str, float] | None:
        """Return feature importances from trained XGBoost model."""
        from chronoai.ml_pipeline.feature_engineering import FEATURE_NAMES
        if self._model is None or not hasattr(self._model, "feature_importances_"):
            return None
        return dict(zip(FEATURE_NAMES, self._model.feature_importances_.tolist()))
