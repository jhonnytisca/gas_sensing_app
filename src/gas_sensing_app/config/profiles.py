"""Portable experiment profiles and atomic YAML persistence."""

import hashlib
import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from .config import Config, load_failure_flows
from .connections import apply_connections, connection_values
from .validation import flows


def atomic_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def atomic_yaml(path, data):
    atomic_bytes(
        path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True).encode("utf-8")
    )


def source_info(path):
    path = Path(path).resolve()
    return {
        "path": str(path),
        "name": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def load_profile(path, local_config):
    config = Config(path).load()
    apply_connections(config, connection_values(local_config))
    # Validate all dependencies before changing the running GUI.
    load_failure_flows(config)
    if config.recipe_file:
        from gas_sensing_app.core.recipe import load_recipe

        load_recipe(config.recipe_file, config, config.gate)
    return config


def save_profile(
    path, config, measurement, gate, targets, shutter_open, mode, recipe_path
):
    from gas_sensing_app.core.recipe import load_recipe

    path = Path(path).resolve()
    measurement.validate()
    gate.points()
    targets = flows(targets, config.hardware.mfc_controller.range_sccm)
    if mode not in ("manual", "recipe") or not isinstance(shutter_open, bool):
        raise ValueError("Invalid experiment mode or shutter state")
    payload = deepcopy(asdict(config))
    for key in (
        "base_dir",
        "configuration_source",
        "manual_flows",
        "manual_shutter_open",
        "acquisition_mode",
        "recipe_file",
        "shutdown_flows",
    ):
        payload.pop(key)
    # Device addresses and transport settings belong to the local computer.
    for device, fields in connection_values(config).items():
        for key in fields:
            payload["hardware"][device].pop(key, None)
    payload.pop("safety_file")
    payload["configuration_version"] = 1
    payload["measurement"] = asdict(measurement)
    payload["gate"] = asdict(gate)
    payload["shutdown_flows_sccm"] = load_failure_flows(config)
    payload["experiment"] = {
        "mode": mode,
        "manual_flows_sccm": targets,
        "manual_shutter_open": shutter_open,
        "recipe_file": None,
    }
    if recipe_path:
        load_recipe(recipe_path, config, gate)
        content = Path(recipe_path).read_bytes()
        digest = hashlib.sha256(content).hexdigest()[:12]
        recipe_name = f"{path.stem}.recipe.{digest}.yaml"
        destination = path.parent / recipe_name
        # Immutable sidecar names keep previous profile versions valid on failure.
        if destination.exists() and destination.read_bytes() != content:
            raise ValueError(f"Recipe copy conflicts with existing file: {destination}")
        if not destination.exists():
            atomic_bytes(destination, content)
        payload["experiment"]["recipe_file"] = recipe_name
    if mode == "recipe" and not recipe_path:
        raise ValueError("Choose a recipe before saving a recipe configuration")
    atomic_yaml(path, payload)
    return source_info(path)
