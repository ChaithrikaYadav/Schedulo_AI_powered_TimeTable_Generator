"""
models/model_registry.py — Central registry for Schedulo trained ML models.

Provides safe load/save helpers that degrade gracefully when model files
don't exist yet (e.g. before training has been run).

Usage:
    from models.model_registry import ModelRegistry

    registry = ModelRegistry()
    model = registry.load("quality_predictor")  # None if not trained yet
    if model:
        score = model.predict([[...]])[0]

    registry.save("quality_predictor", trained_model)
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Canonical model filenames ──────────────────────────────────────────────────
_MODEL_FILES: dict[str, str] = {
    "quality_predictor":  "quality_predictor.pkl",    # XGBoost regressor
    "anomaly_detector":   "anomaly_detector.pkl",     # Isolation Forest
    "rl_policy":          "rl_policy.zip",            # Stable-Baselines3 PPO
}

# Directory containing this file
_MODELS_DIR = Path(__file__).parent


class ModelRegistry:
    """
    Safe model loader / saver for Schedulo ML artefacts.

    All models are stored as pickle files in the `models/` directory.
    The `rl_policy` is stored as a .zip (SB3 format) and requires
    stable-baselines3 for loading — handled transparently.

    Attributes:
        models_dir: Path to the directory where model files are stored.
    """

    def __init__(self, models_dir: str | Path | None = None) -> None:
        self.models_dir = Path(models_dir) if models_dir else _MODELS_DIR
        self.models_dir.mkdir(parents=True, exist_ok=True)

    # ── Core API ────────────────────────────────────────────────────────────────

    def load(self, name: str) -> Any | None:
        """
        Load a trained model by logical name.

        Returns the model object if it exists, or None if not yet trained.
        Never raises — callers should check for None and handle gracefully.

        Args:
            name: Logical model name (e.g. "quality_predictor").

        Returns:
            The deserialized model object, or None.
        """
        if name not in _MODEL_FILES:
            logger.warning(f"ModelRegistry: unknown model name '{name}'. "
                           f"Known names: {list(_MODEL_FILES)}")
            return None

        path = self.models_dir / _MODEL_FILES[name]
        if not path.exists():
            logger.info(f"ModelRegistry: '{name}' not found at {path} — not yet trained.")
            return None

        try:
            if name == "rl_policy":
                return self._load_rl_policy(path)
            with open(path, "rb") as f:
                model = pickle.load(f)
            logger.info(f"ModelRegistry: loaded '{name}' from {path}")
            return model
        except Exception as e:
            logger.error(f"ModelRegistry: failed to load '{name}': {e}")
            return None

    def save(self, name: str, model: Any) -> Path:
        """
        Persist a trained model to disk.

        Args:
            name:  Logical model name (e.g. "quality_predictor").
            model: The trained model object.

        Returns:
            Path where the model was saved.

        Raises:
            ValueError: If name is not a registered model name.
        """
        if name not in _MODEL_FILES:
            raise ValueError(
                f"Unknown model name '{name}'. Registered: {list(_MODEL_FILES)}"
            )

        path = self.models_dir / _MODEL_FILES[name]

        if name == "rl_policy":
            model.save(str(path))
            logger.info(f"ModelRegistry: saved RL policy to {path}")
            return path

        with open(path, "wb") as f:
            pickle.dump(model, f, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info(f"ModelRegistry: saved '{name}' to {path} ({path.stat().st_size:,} bytes)")
        return path

    def exists(self, name: str) -> bool:
        """Return True if the model file exists on disk."""
        if name not in _MODEL_FILES:
            return False
        return (self.models_dir / _MODEL_FILES[name]).exists()

    def list_available(self) -> dict[str, bool]:
        """Return a dict of {model_name: is_trained} for all registered models."""
        return {name: self.exists(name) for name in _MODEL_FILES}

    def delete(self, name: str) -> bool:
        """Delete a model file. Returns True if deleted, False if it didn't exist."""
        if name not in _MODEL_FILES:
            return False
        path = self.models_dir / _MODEL_FILES[name]
        if path.exists():
            path.unlink()
            logger.info(f"ModelRegistry: deleted '{name}'")
            return True
        return False

    # ── Private helpers ─────────────────────────────────────────────────────────

    def _load_rl_policy(self, path: Path) -> Any | None:
        """Load stable-baselines3 PPO policy from .zip file."""
        try:
            from stable_baselines3 import PPO
            model = PPO.load(str(path))
            logger.info(f"ModelRegistry: loaded RL policy from {path}")
            return model
        except ImportError:
            logger.warning(
                "stable-baselines3 not installed — cannot load rl_policy. "
                "Install with: pip install stable-baselines3"
            )
            return None


# ── CLI / Smoke test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    registry = ModelRegistry()
    available = registry.list_available()

    print("\n=== Schedulo Model Registry ===")
    print("=" * 40)
    for model_name, is_trained in available.items():
        status = "[trained]" if is_trained else "[not yet trained]"
        filename = _MODEL_FILES[model_name]
        print(f"  {model_name:<25} {status}  ({filename})")

    trained_count = sum(available.values())
    print(f"\n  {trained_count}/{len(available)} models trained")

    if trained_count == 0:
        print("\n  Run training scripts to populate models:")
        print("     python models/train_quality_predictor.py --dry-run")
        print("     python models/train_anomaly_detector.py --dry-run")

    sys.exit(0)
