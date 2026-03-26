"""
models/train_quality_predictor.py — XGBoost timetable quality predictor trainer.

Stage 4 of the ML pipeline (Phase 3).

Trains an XGBRegressor to predict timetable quality score (0.0–1.0) from
scheduling features extracted from MLTrainingData records in the database.

Usage:
    # Train from real DB data:
    python models/train_quality_predictor.py

    # Train from synthetic data (no DB, for testing):
    python models/train_quality_predictor.py --dry-run

    # Custom DB URL:
    python models/train_quality_predictor.py --db-url sqlite:///./schedulo.db
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)


# ── Feature engineering ────────────────────────────────────────────────────────

def compute_features(record: dict) -> dict[str, float]:
    """
    Engineer features from a single MLTrainingData record dict.

    Features:
        conflict_count          — raw conflict count (lower = better)
        conflict_log1p          — log1p-transformed conflict count
        generation_time_log     — log1p of generation time in ms
        slot_fill_ratio         — fraction of non-free / non-lunch slots
        quality_score           — ground-truth label (target)

    Args:
        record: Dict with keys: conflict_count, generation_time_ms,
                features (JSON dict), quality_score
    """
    feat = record.get("features") or {}
    if isinstance(feat, str):
        import json
        try:
            feat = json.loads(feat)
        except Exception:
            feat = {}

    conflict_count = float(record.get("conflict_count") or 0)
    gen_time_ms = float(record.get("generation_time_ms") or 1000)
    slot_fill_ratio = float(feat.get("slot_fill_ratio", 0.7))
    lab_pair_ratio = float(feat.get("lab_pair_ratio", 0.5))
    free_period_std = float(feat.get("free_period_std", 2.0))
    faculty_util_ratio = float(feat.get("faculty_util_ratio", 0.6))

    return {
        "conflict_count":       conflict_count,
        "conflict_log1p":       float(np.log1p(conflict_count)),
        "generation_time_log":  float(np.log1p(gen_time_ms)),
        "slot_fill_ratio":      slot_fill_ratio,
        "lab_pair_ratio":       lab_pair_ratio,
        "free_period_std":      free_period_std,
        "faculty_util_ratio":   faculty_util_ratio,
    }


FEATURE_NAMES = [
    "conflict_count",
    "conflict_log1p",
    "generation_time_log",
    "slot_fill_ratio",
    "lab_pair_ratio",
    "free_period_std",
    "faculty_util_ratio",
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
                "quality_score":      row.quality_score,
            })

    logger.info(f"Loaded {len(records)} training records from DB")
    return records


def generate_synthetic_data(n: int = 500) -> list[dict]:
    """
    Generate synthetic training data for dry-run / smoke testing.

    Quality score is derived from conflict_count and slot_fill_ratio
    with added noise to simulate real scheduler variance.
    """
    rng = np.random.default_rng(seed=42)
    records = []
    for _ in range(n):
        conflict_count = int(rng.integers(0, 15))
        gen_time_ms    = int(rng.integers(200, 8000))
        fill_ratio     = float(rng.uniform(0.4, 0.9))
        lab_pair       = float(rng.uniform(0.3, 1.0))
        free_std       = float(rng.uniform(0.5, 4.0))
        faculty_util   = float(rng.uniform(0.3, 0.85))

        # Ground truth quality: high fill + low conflicts = high quality
        quality = (
            fill_ratio * 0.4
            + lab_pair * 0.2
            + (1.0 - min(conflict_count, 10) / 10.0) * 0.3
            + faculty_util * 0.1
            + rng.normal(0, 0.05)
        )
        quality = float(np.clip(quality, 0.0, 1.0))

        records.append({
            "conflict_count":     conflict_count,
            "generation_time_ms": gen_time_ms,
            "features": {
                "slot_fill_ratio":   fill_ratio,
                "lab_pair_ratio":    lab_pair,
                "free_period_std":   free_std,
                "faculty_util_ratio": faculty_util,
            },
            "quality_score": quality,
        })

    logger.info(f"Generated {n} synthetic training records (dry-run mode)")
    return records


# ── Training ───────────────────────────────────────────────────────────────────

def train(records: list[dict]) -> object:
    """Train an XGBRegressor on the provided records."""
    try:
        from xgboost import XGBRegressor
    except ImportError:
        logger.error(
            "xgboost not installed. Install with: pip install xgboost"
        )
        sys.exit(1)

    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error, r2_score

    # Build feature matrix
    X = np.array([[compute_features(r)[f] for f in FEATURE_NAMES] for r in records])
    y = np.array([float(r.get("quality_score") or 0.5) for r in records])

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = XGBRegressor(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae  = mean_absolute_error(y_test, y_pred)
    r2   = r2_score(y_test, y_pred)

    logger.info(f"Training complete — MAE: {mae:.4f}  R²: {r2:.4f}")
    logger.info(f"Feature importances:")
    for fname, imp in zip(FEATURE_NAMES, model.feature_importances_):
        logger.info(f"  {fname:<28} {imp:.4f}")

    return model


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train Schedulo XGBoost quality predictor."
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

    print("\n=== Schedulo - Training Quality Predictor (XGBoost) ===")
    print("=" * 55)

    if args.dry_run:
        records = generate_synthetic_data(n=args.n_synthetic)
    else:
        records = asyncio.run(load_training_data_from_db())
        if len(records) < 10:
            logger.warning(
                f"Only {len(records)} DB records found. "
                "Use --dry-run for synthetic training if DB is not seeded."
            )
            if len(records) == 0:
                logger.error(
                    "No training data in DB. Run --dry-run or generate timetables first."
                )
                sys.exit(1)

    print(f"\n[INFO] Training on {len(records)} records...")
    model = train(records)

    # Save via registry
    from models.model_registry import ModelRegistry
    registry = ModelRegistry()
    path = registry.save("quality_predictor", model)
    print(f"\n[OK] Model saved to: {path}")
    print("    Load with: from models.model_registry import ModelRegistry; registry.load('quality_predictor')")


if __name__ == "__main__":
    main()
