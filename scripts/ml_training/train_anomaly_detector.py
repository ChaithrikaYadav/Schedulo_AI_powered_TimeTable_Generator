"""
models/train_anomaly_detector.py — Isolation Forest anomaly detector trainer.

Stage 6 of the ML pipeline (Phase 3).

Trains an IsolationForest to detect abnormal timetable patterns such as:
  - Severely overloaded days (too many classes)
  - Underloaded timetables (too many free periods)
  - Excessive conflicts relative to slot count
  - Faculty overutilisation patterns

Usage:
    # Train from real DB data:
    python models/train_anomaly_detector.py

    # Train from synthetic data (no DB needed):
    python models/train_anomaly_detector.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


# ── Feature names (identical to quality predictor for consistency) ──────────────
FEATURE_NAMES = [
    "conflict_count",
    "conflict_log1p",
    "generation_time_log",
    "slot_fill_ratio",
    "lab_pair_ratio",
    "free_period_std",
    "faculty_util_ratio",
]


# ── Feature engineering ────────────────────────────────────────────────────────

def compute_features(record: dict) -> list[float]:
    """Extract numeric feature vector from an MLTrainingData record dict."""
    feat = record.get("features") or {}
    if isinstance(feat, str):
        import json
        try:
            feat = json.loads(feat)
        except Exception:
            feat = {}

    conflict_count = float(record.get("conflict_count") or 0)
    gen_time_ms    = float(record.get("generation_time_ms") or 1000)

    return [
        conflict_count,
        float(np.log1p(conflict_count)),
        float(np.log1p(gen_time_ms)),
        float(feat.get("slot_fill_ratio", 0.7)),
        float(feat.get("lab_pair_ratio", 0.5)),
        float(feat.get("free_period_std", 2.0)),
        float(feat.get("faculty_util_ratio", 0.6)),
    ]


# ── Data loading ───────────────────────────────────────────────────────────────

async def load_training_data_from_db() -> list[dict]:
    """Load MLTrainingData records from the Schedulo database."""
    from schedulo.database import AsyncSessionLocal
    from schedulo.models import MLTrainingData
    from sqlalchemy import select

    records = []
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(MLTrainingData))
        rows = result.scalars().all()
        for row in rows:
            records.append({
                "conflict_count":     row.conflict_count,
                "generation_time_ms": row.generation_time_ms,
                "features":           row.features,
            })

    logger.info(f"Loaded {len(records)} records from DB")
    return records


def generate_synthetic_data(n: int = 500) -> list[dict]:
    """
    Generate synthetic data for dry-run mode.

    Includes ~15% anomalous samples (very high conflict_count or
    very low slot_fill_ratio) to give the Isolation Forest something
    to learn from.
    """
    rng = np.random.default_rng(seed=42)
    records = []

    for i in range(n):
        is_anomaly = rng.random() < 0.15  # 15% anomalies

        if is_anomaly:
            # Anomalous: extreme values
            records.append({
                "conflict_count":     int(rng.integers(20, 50)),
                "generation_time_ms": int(rng.integers(15000, 60000)),
                "features": {
                    "slot_fill_ratio":    float(rng.uniform(0.05, 0.25)),
                    "lab_pair_ratio":     float(rng.uniform(0.0, 0.2)),
                    "free_period_std":    float(rng.uniform(8.0, 15.0)),
                    "faculty_util_ratio": float(rng.uniform(0.95, 1.5)),
                },
            })
        else:
            # Normal: typical values
            records.append({
                "conflict_count":     int(rng.integers(0, 8)),
                "generation_time_ms": int(rng.integers(200, 5000)),
                "features": {
                    "slot_fill_ratio":    float(rng.uniform(0.50, 0.90)),
                    "lab_pair_ratio":     float(rng.uniform(0.60, 1.0)),
                    "free_period_std":    float(rng.uniform(0.5, 3.5)),
                    "faculty_util_ratio": float(rng.uniform(0.30, 0.80)),
                },
            })

    logger.info(f"Generated {n} synthetic records ({int(n * 0.15)} anomalies)")
    return records


# ── Training ───────────────────────────────────────────────────────────────────

def train(records: list[dict]) -> object:
    """Train an IsolationForest on the provided records."""
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline

    X = np.array([compute_features(r) for r in records])

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("iso_forest", IsolationForest(
            n_estimators=200,
            contamination=0.10,   # assume 10% anomaly rate
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )),
    ])
    model.fit(X)

    # Evaluation on training set (unsupervised — just log anomaly rate)
    preds = model.predict(X)   # -1 = anomaly, 1 = normal
    anomaly_count = int((preds == -1).sum())
    logger.info(
        f"Training complete — {anomaly_count}/{len(records)} "
        f"({100 * anomaly_count / len(records):.1f}%) samples flagged as anomalies"
    )

    # Show score stats
    scores = model.decision_function(X)
    logger.info(
        f"Anomaly scores — min: {scores.min():.3f}  "
        f"mean: {scores.mean():.3f}  max: {scores.max():.3f}"
    )

    return model


# ── Inference helper (exported for use by other modules) ────────────────────────

def predict_anomaly(model: object, record: dict) -> dict:
    """
    Run anomaly detection on a single timetable record.

    Returns:
        {
            "is_anomaly": bool,
            "anomaly_score": float,   # lower = more anomalous
            "label": str              # "NORMAL" or "ANOMALY"
        }
    """
    import numpy as _np
    x = _np.array([compute_features(record)])
    prediction = model.predict(x)[0]          # -1 or 1
    score = float(model.decision_function(x)[0])
    return {
        "is_anomaly":    bool(prediction == -1),
        "anomaly_score": score,
        "label":         "ANOMALY" if prediction == -1 else "NORMAL",
    }


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train Schedulo Isolation Forest anomaly detector."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use synthetic data instead of real DB records"
    )
    parser.add_argument(
        "--n-synthetic", type=int, default=500,
        help="Number of synthetic records to generate (default: 500)"
    )
    args = parser.parse_args()

    print("\n=== Schedulo - Training Anomaly Detector (Isolation Forest) ===")
    print("=" * 60)

    if args.dry_run:
        records = generate_synthetic_data(n=args.n_synthetic)
    else:
        records = asyncio.run(load_training_data_from_db())
        if len(records) < 10:
            logger.warning(
                f"Only {len(records)} DB records found. "
                "Use --dry-run for synthetic training."
            )
            if len(records) == 0:
                logger.error("No training data in DB. Run --dry-run first.")
                sys.exit(1)

    print(f"\n[INFO] Training on {len(records)} records...")
    model = train(records)

    from models.model_registry import ModelRegistry
    registry = ModelRegistry()
    path = registry.save("anomaly_detector", model)
    print(f"\n[OK] Model saved to: {path}")
    print("    Load with: from models.model_registry import ModelRegistry; registry.load('anomaly_detector')")


if __name__ == "__main__":
    main()
