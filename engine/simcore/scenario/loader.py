"""Load scenarios from YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from simcore.scenario.models import Scenario


def load_scenario(path: str | Path) -> Scenario:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Scenario.model_validate(data)
