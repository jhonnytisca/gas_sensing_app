"""Portable experiment profiles and atomic YAML persistence."""

import hashlib
import os
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

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
    config = Config(path, workspace_dir=local_config.workspace_dir).load()
    apply_connections(config, connection_values(local_config))
    # Validate all dependencies before changing the running GUI.
    load_failure_flows(config)
    if config.recipe_file:
        from gas_sensing_app.core.recipe import load_recipe

        load_recipe(config.recipe_file, config, config.gate)
    return config


def save_profile_bundle(
    folder, config, measurement, gate, targets, shutter_open, mode, recipe_path
):
    """Validate and stage a portable folder before replacing its owned files."""
    folder = Path(folder).absolute()
    if folder.is_symlink():
        raise ValueError("Configuration folder must not be a symbolic link")
    config_name = f"{folder.name}.config.yaml"
    recipe_name = f"{folder.name}.recipe.yaml"
    folder.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".configuration-", dir=folder.parent) as temporary:
        staging = Path(temporary)
        staged_config = staging / config_name
        save_profile(
            staged_config,
            config,
            measurement,
            gate,
            targets,
            shutter_open,
            mode,
            recipe_path,
        )
        payload = yaml.safe_load(staged_config.read_text(encoding="utf-8"))
        if payload["experiment"]["recipe_file"]:
            (staging / payload["experiment"]["recipe_file"]).rename(
                staging / recipe_name
            )
            payload["experiment"]["recipe_file"] = recipe_name
            atomic_yaml(staged_config, payload)
        if not folder.exists():
            os.replace(staging, folder)
        else:
            _replace_bundle_files(folder, staging, (config_name, recipe_name))
    return source_info(folder / config_name)


def _replace_bundle_files(folder, staging, names):
    # Keep any recordings or other user files in the existing folder.
    backed_up, installed = [], []
    try:
        for name in names:
            destination = folder / name
            if destination.exists() or destination.is_symlink():
                if destination.is_dir():
                    raise ValueError(f"Expected a file: {destination}")
                os.replace(destination, staging / f"previous-{name}")
                backed_up.append(name)
            if (staging / name).exists():
                os.replace(staging / name, destination)
                installed.append(name)
    except Exception:
        for name in reversed(installed):
            (folder / name).unlink()
        for name in reversed(backed_up):
            os.replace(staging / f"previous-{name}", folder / name)
        raise


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
        "workspace_dir",
        "configuration_source",
        "manual_flows",
        "manual_shutter_open",
        "acquisition_mode",
        "recipe_file",
        "shutdown_flows",
        "sample_name",
        "device",
        "experiment_name",
        "description",
        "sample_label",
        "experiment_notes",
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
        "sample_name": config.sample_name,
        "device": config.device,
        "experiment_name": config.experiment_name,
        "description": config.description,
        "sample_label": config.sample_label,
        "experiment_notes": config.experiment_notes,
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
