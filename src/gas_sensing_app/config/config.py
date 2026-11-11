import re
from pathlib import Path

import yaml

from .models import (
    AppConfig,
    ConsoleLogConfig,
    DataLogConfig,
    GateSettings,
    HardwareConfig,
    Keithley2400Config,
    Keithley2700Config,
    LoggingConfig,
    MeasurementSettings,
    MFCControllerConfig,
    ShutterConfig,
)
from .validation import finite, flows


class Config:
    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()

    def load(self) -> AppConfig:
        with self.path.open(encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
        if not isinstance(data, dict):
            raise ValueError("Configuration must be a YAML mapping")
        version = data.get("configuration_version")
        if version is not None and (type(version) is not int or version != 1):
            raise ValueError("Unsupported configuration version")
        hw = data.get("hardware", {})
        if version == 1:
            hw = {**hw}
            for device in (
                "keithley_2400",
                "keithley_2700",
                "mfc_controller",
                "shutter",
            ):
                hw[device] = {**hw.get(device, {}), "port": ""}
        mock = hw.get("use_mock", True)
        if not isinstance(mock, bool):
            raise ValueError("hardware.use_mock must be true or false")
        mfc = MFCControllerConfig(**hw.get("mfc_controller", {}))
        mfc.range_sccm = {
            int(k): finite(v, f"range {k}", 1e-9) for k, v in mfc.range_sccm.items()
        }
        if not mfc.range_sccm or not set(mfc.range_sccm) <= {1, 2, 3, 4}:
            raise ValueError("ROD-4 supports gas channels 1–4")
        mfc.gas_names = {
            ch: str(mfc.gas_names.get(ch, mfc.gas_names.get(str(ch), f"mfc{ch}")))
            for ch in mfc.range_sccm
        }
        if any(
            not re.fullmatch(r"[A-Za-z0-9_]+", name) for name in mfc.gas_names.values()
        ):
            raise ValueError("Gas names must use letters, digits and underscores")
        k2400 = Keithley2400Config(**hw.get("keithley_2400", {}))
        settings = dict(data.get("measurement", {}))
        settings.setdefault("wire_mode", 4 if k2400.four_wire else 2)
        settings.setdefault("auto_range", k2400.auto_range)
        settings.setdefault("manual_range", k2400.manual_range)
        logging = data.get("logging", {})
        result = AppConfig(
            hardware=HardwareConfig(
                mock,
                k2400,
                ShutterConfig(**hw.get("shutter", {})),
                mfc,
                Keithley2700Config(**hw.get("keithley_2700", {})),
            ),
            logging=LoggingConfig(
                DataLogConfig(**logging.get("data_log", {})),
                ConsoleLogConfig(**logging.get("console_log", {})),
            ),
            measurement=MeasurementSettings(**settings),
            gate=GateSettings(**data.get("gate", {})),
            safety_file=data.get("safety_file", "failure_gases.yaml"),
            base_dir=str(self.path.parent),
        )
        self.load_experiment(result, data, version)
        from .profiles import source_info

        result.configuration_source = source_info(self.path)
        result.measurement.validate()
        result.gate.points()
        if (
            Path(result.logging.data_log.filename_prefix).name
            != result.logging.data_log.filename_prefix
        ):
            raise ValueError("CSV prefix must be a filename, not a path")
        return result

    def load_experiment(self, result, data, version):
        experiment = data.get("experiment", {})
        if not isinstance(experiment, dict):
            raise ValueError("experiment must be a mapping")
        self.load_annotations(result, experiment)
        result.manual_flows = flows(
            experiment.get("manual_flows_sccm", {}),
            result.hardware.mfc_controller.range_sccm,
        )
        result.manual_shutter_open = experiment.get("manual_shutter_open", False)
        if not isinstance(result.manual_shutter_open, bool):
            raise ValueError("manual_shutter_open must be true or false")
        result.acquisition_mode = experiment.get("mode", "manual")
        if result.acquisition_mode not in ("manual", "recipe"):
            raise ValueError("Experiment mode must be manual or recipe")
        recipe = experiment.get("recipe_file")
        if recipe is not None:
            if not isinstance(recipe, str) or not recipe.strip():
                raise ValueError("recipe_file must be a path")
            result.recipe_file = str((self.path.parent / recipe).resolve())
        if result.acquisition_mode == "recipe" and not result.recipe_file:
            raise ValueError("Recipe mode requires a recipe file")
        if "shutdown_flows_sccm" in data:
            result.shutdown_flows = flows(
                data["shutdown_flows_sccm"], result.hardware.mfc_controller.range_sccm
            )
        if version == 1 and result.shutdown_flows is None:
            raise ValueError("Portable configurations require shutdown_flows_sccm")

    @staticmethod
    def load_annotations(result, experiment):
        for key in (
            "sample_name",
            "device",
            "experiment_name",
            "description",
            "sample_label",
            "experiment_notes",
        ):
            value = experiment.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            setattr(result, key, value)


def load_failure_flows(config):
    if config.shutdown_flows is not None:
        return flows(config.shutdown_flows, config.hardware.mfc_controller.range_sccm)
    path = Path(config.base_dir) / config.safety_file
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict) or "mfc_flows" not in data:
        raise ValueError("Failure gas configuration requires mfc_flows")
    return flows(data["mfc_flows"], config.hardware.mfc_controller.range_sccm)
