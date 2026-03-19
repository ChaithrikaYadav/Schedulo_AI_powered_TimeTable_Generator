"""
chronoai/ml_pipeline/rl_finetuner.py
PPO Reinforcement Learning fine-tuner for timetable optimization (Stage 5).

This is a fully functional stub that defines the RL environment and training
loop using Gymnasium + stable-baselines3. It is intentionally lightweight
and can run in "dry-run" mode (random agent) when SB3 / Torch are not installed.

Architecture:
  - TimetableEnv: Custom Gymnasium Env representing a timetable as a flat
    observation vector (20 quality features). The agent's actions adjust slot
    assignments; the reward is the change in quality score.
  - RLFineTuner: Wrapper that trains a PPO agent and exposes improve() which
    applies learned improvements to a timetable dict.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

MODEL_FILENAME = "rl_finetuner_ppo.zip"
OBS_DIM = 20    # matches FeatureEngineer output
ACT_DIM = 10    # discrete: 10 possible slot-swap actions per step

try:
    import gymnasium as gym
    from gymnasium import spaces as gym_spaces
    _GYM_AVAILABLE = True
except ImportError:
    _GYM_AVAILABLE = False
    gym = None  # type: ignore[assignment]

try:
    from stable_baselines3 import PPO as _PPO
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    _PPO = None  # type: ignore[assignment]

try:
    import joblib
    _JOBLIB_AVAILABLE = True
except ImportError:
    _JOBLIB_AVAILABLE = False


# ── RL Environment ────────────────────────────────────────────────────────────

if _GYM_AVAILABLE:
    class TimetableEnv(gym.Env):  # type: ignore[misc]
        """
        Minimal Gymnasium environment representing a timetable optimization problem.

        Observation: 20-dimensional quality feature vector (float32, normalized 0–1)
        Action:      Discrete(10) — each action represents a class of slot-swap heuristic
        Reward:      Δ quality score after applying the action
        Done:        After `max_steps` steps, or when quality_score >= 95.0
        """

        metadata = {"render_modes": []}

        def __init__(
            self,
            timetable_dict: dict[str, Any] | None = None,
            max_steps: int = 50,
        ) -> None:
            super().__init__()
            from chronoai.ml_pipeline.feature_engineering import FeatureEngineer
            from chronoai.ml_pipeline.quality_predictor import QualityPredictor

            self._fe = FeatureEngineer()
            self._qp = QualityPredictor.__new__(QualityPredictor)
            # lightweight init
            self._qp._feature_engineer = self._fe
            self._qp._model = None
            self._qp._model_trained = False

            self._timetable = timetable_dict or {}
            self._max_steps = max_steps
            self._step_count = 0
            self._current_score = 0.0

            self.observation_space = gym_spaces.Box(
                low=0.0, high=1.0, shape=(OBS_DIM,), dtype=np.float32
            )
            self.action_space = gym_spaces.Discrete(ACT_DIM)

        # noinspection PyMethodOverriding
        def reset(
            self,
            *,
            seed: int | None = None,
            options: dict | None = None,
        ) -> tuple[np.ndarray, dict]:
            super().reset(seed=seed)
            self._step_count = 0
            obs = self._get_obs()
            self._current_score = self._score()
            return obs.astype(np.float32), {}

        def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
            self._step_count += 1
            # Apply heuristic action (stub: jitter conflict_count)
            self._apply_action(action)
            new_score = self._score()
            reward = float(new_score - self._current_score)
            self._current_score = new_score
            terminated = new_score >= 95.0
            truncated = self._step_count >= self._max_steps
            return self._get_obs().astype(np.float32), reward, terminated, truncated, {}

        def _get_obs(self) -> np.ndarray:
            raw = self._fe.extract_raw(self._timetable)
            arr = np.clip(np.array(raw, dtype=np.float32), 0.0, 1.0)
            return arr

        def _score(self) -> float:
            from chronoai.ml_pipeline.quality_predictor import _heuristic_score
            raw = self._fe.extract_raw(self._timetable)
            return _heuristic_score(raw)

        def _apply_action(self, action: int) -> None:
            """
            Stub action handler — in production each action would correspond to
            a specific slot-swap / reassignment strategy.
            Here we simulate a small improvement by reducing conflict_count.
            """
            conflict_count = self._timetable.get("conflict_count", 0)
            if action < 5 and conflict_count > 0:
                # Actions 0–4: attempt to reduce a conflict
                self._timetable["conflict_count"] = max(0, conflict_count - 1)
            # Actions 5–9: no-op in stub


else:
    class TimetableEnv:  # type: ignore[no-redef]
        """Placeholder when gymnasium is not installed."""
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("gymnasium is required for TimetableEnv")


# ── RL Fine-Tuner ─────────────────────────────────────────────────────────────

class RLFineTuner:
    """
    PPO-based reinforcement learning fine-tuner.

    Usage:
        rft = RLFineTuner(models_dir="./models")
        rft.train(timetable_dict, n_steps=10_000)
        improved = rft.improve(timetable_dict)
    """

    def __init__(self, models_dir: str = "./models") -> None:
        self._models_dir = Path(models_dir)
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._model_path = self._models_dir / MODEL_FILENAME
        self._agent: Any = None
        self._agent_trained = False

        self._try_load_agent()

    def _try_load_agent(self) -> None:
        if not _SB3_AVAILABLE or not _GYM_AVAILABLE:
            return
        if self._model_path.exists():
            try:
                self._agent = _PPO.load(str(self._model_path))
                self._agent_trained = True
                logger.info("RLFineTuner: loaded PPO agent from %s", self._model_path)
            except Exception as exc:
                logger.warning("RLFineTuner: failed to load agent: %s", exc)

    def train(
        self,
        timetable_dict: dict[str, Any],
        n_steps: int = 10_000,
    ) -> "RLFineTuner":
        """
        Train (or continue training) the PPO agent.

        Args:
            timetable_dict: Reference timetable to use as training environment
            n_steps:        Total timesteps to train for
        """
        if not _SB3_AVAILABLE or not _GYM_AVAILABLE:
            logger.warning(
                "stable-baselines3/gymnasium not available — RL training skipped. "
                "Install with: pip install stable-baselines3 gymnasium"
            )
            return self

        env = TimetableEnv(timetable_dict=timetable_dict.copy())

        if self._agent is not None:
            # Continue training existing agent
            self._agent.set_env(env)
            logger.info("RLFineTuner: continuing training for %d steps", n_steps)
        else:
            # First-time training
            self._agent = _PPO(
                "MlpPolicy",
                env,
                verbose=0,
                n_steps=512,
                batch_size=64,
                n_epochs=10,
                learning_rate=3e-4,
                gamma=0.99,
            )
            logger.info("RLFineTuner: starting fresh PPO training for %d steps", n_steps)

        self._agent.learn(total_timesteps=n_steps, progress_bar=False)
        self._agent_trained = True

        # Save
        self._agent.save(str(self._model_path))
        logger.info("RLFineTuner: PPO agent saved to %s", self._model_path)

        return self

    def improve(
        self,
        timetable_dict: dict[str, Any],
        n_steps: int = 50,
    ) -> dict[str, Any]:
        """
        Use the trained PPO agent to iteratively improve a timetable.

        Args:
            timetable_dict: Input timetable dict (will not be mutated)
            n_steps:        Number of improvement steps to apply

        Returns:
            Improved timetable dict (copy with changes applied by the agent)
        """
        import copy
        timetable = copy.deepcopy(timetable_dict)

        if not _SB3_AVAILABLE or not _GYM_AVAILABLE or not self._agent_trained:
            logger.info("RLFineTuner: no trained agent — returning original timetable")
            return timetable

        env = TimetableEnv(timetable_dict=timetable, max_steps=n_steps)
        obs, _ = env.reset()

        for _ in range(n_steps):
            action, _ = self._agent.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(int(action))
            if terminated or truncated:
                break

        # Return the timetable as modified by the env's action handlers
        return env._timetable

    @property
    def is_trained(self) -> bool:
        return self._agent_trained
