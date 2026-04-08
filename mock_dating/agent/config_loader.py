"""YAML config loader with small schemas.

We use plain dicts internally and only validate the shape. Nothing
here is performance-sensitive.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(__file__).parent / "config"


@dataclass
class Preferences:
    likes: list[str] = field(default_factory=list)
    dislikes: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    deal_breakers: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)
    threshold: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Preferences":
        return cls(
            likes=list(d.get("likes") or []),
            dislikes=list(d.get("dislikes") or []),
            red_flags=list(d.get("red_flags") or []),
            deal_breakers=list(d.get("deal_breakers") or []),
            weights={k: float(v) for k, v in (d.get("weights") or {}).items()},
            threshold={k: float(v) for k, v in (d.get("threshold") or {}).items()},
        )


@dataclass
class Persona:
    display_name: str
    voice: dict[str, Any]
    goals: list[str]
    hard_rules: list[str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Persona":
        return cls(
            display_name=str(d.get("display_name", "Agent")),
            voice=dict(d.get("voice") or {}),
            goals=list(d.get("goals") or []),
            hard_rules=list(d.get("hard_rules") or []),
        )


@dataclass
class Runtime:
    mode: str = "auto"
    tick_interval_s: float = 2.0
    tick_timeout_s: float = 15.0
    max_ticks: int = 500
    model: str = "claude-sonnet-4-6"
    retries: int = 1
    min_confidence: float = 0.5
    ambiguity_safe_stop: bool = True
    log_level: str = "INFO"
    no_progress_window: int = 3
    loop_window: int = 8
    loop_threshold: int = 4
    quiesce_max_wait_s: float = 1.5
    quiesce_poll_s: float = 0.1

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Runtime":
        return cls(
            mode=str(d.get("mode", "auto")),
            tick_interval_s=float(d.get("tick_interval_s", 2.0)),
            tick_timeout_s=float(d.get("tick_timeout_s", 15.0)),
            max_ticks=int(d.get("max_ticks", 500)),
            model=str(d.get("model", "claude-sonnet-4-6")),
            retries=int(d.get("retries", 1)),
            min_confidence=float(d.get("min_confidence", 0.5)),
            ambiguity_safe_stop=bool(d.get("ambiguity_safe_stop", True)),
            log_level=str(d.get("log_level", "INFO")),
            no_progress_window=int(d.get("no_progress_window", 3)),
            loop_window=int(d.get("loop_window", 8)),
            loop_threshold=int(d.get("loop_threshold", 4)),
            quiesce_max_wait_s=float(d.get("quiesce_max_wait_s", 1.5)),
            quiesce_poll_s=float(d.get("quiesce_poll_s", 0.1)),
        )


@dataclass
class Config:
    persona: Persona
    preferences: Preferences
    runtime: Runtime

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping at top level, got {type(data).__name__}")
    return data


def load_config(config_dir: Path | None = None) -> Config:
    """Load persona + preferences + runtime from a config directory.

    If ``config_dir`` is ``None``, the package default in
    ``mock_dating/agent/config/`` is used.
    """
    cdir = Path(config_dir) if config_dir else CONFIG_DIR
    persona = Persona.from_dict(_load_yaml(cdir / "persona.yaml"))
    preferences = Preferences.from_dict(_load_yaml(cdir / "preferences.yaml"))
    runtime = Runtime.from_dict(_load_yaml(cdir / "runtime.yaml"))
    return Config(persona=persona, preferences=preferences, runtime=runtime)
