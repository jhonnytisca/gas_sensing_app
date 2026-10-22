"""Validated gas stages. A sweep completes while its stage's flows are held."""

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from gas_sensing_app.config.validation import finite, flows


@dataclass(frozen=True)
class Stage:
    name: str
    duration: float
    flows: dict
    shutter_open: bool
    gate: object

    @property
    def estimated_duration(self):
        settling = 0
        if self.gate.enabled:
            settling = self.gate.dwell_s * (
                len(self.gate.points()) if self.gate.mode == "sweep" else 1
            )
        return max(self.duration, settling)


def load_recipe(path, config, gate):
    with Path(path).open(encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("steps"), list)
        or not raw["steps"]
    ):
        raise ValueError("Recipe requires a non-empty steps list")
    stages = []
    for index, item in enumerate(raw["steps"], 1):
        if not isinstance(item, dict):
            raise ValueError(f"Recipe step {index} must be a mapping")
        stage_gate = replace(gate, **item.get("gate", {}))
        stage_gate.points()
        shutter = item.get("shutter_open", False)
        if not isinstance(shutter, bool):
            raise ValueError("shutter_open must be true or false")
        stages.append(
            Stage(
                str(item.get("name", f"Step {index}")),
                finite(item.get("duration", 1), "duration", 0.01),
                flows(
                    item.get("mfc_flows", {}), config.hardware.mfc_controller.range_sccm
                ),
                shutter,
                stage_gate,
            )
        )
    return stages
