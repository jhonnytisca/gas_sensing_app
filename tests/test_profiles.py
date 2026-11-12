"""Portable configurations, local transport assignments and atomic saves."""

import shutil
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from gas_sensing_app.config.config import Config, load_failure_flows
from gas_sensing_app.config.connections import (
    apply_connections,
    connection_problems,
    connection_values,
    load_local_connections,
    save_local_connections,
)
from gas_sensing_app.config.profiles import load_profile, save_profile
from gas_sensing_app.core.recipe import load_recipe


@pytest.fixture
def profile_config(tmp_path):
    path = tmp_path / "startup.yaml"
    template = (
        Path(__file__).parents[1]
        / "src/gas_sensing_app/assets/defaults/config.template.yaml"
    )
    path.write_text(template.read_text())
    (tmp_path / "failure_gases.yaml").write_text("mfc_flows: {1: 12, 2: 3}")
    return Config(path).load()


def test_full_profile_roundtrip_across_computers(profile_config, tmp_path):
    config = profile_config
    config.hardware.keithley_2400.port = "ASRL1::INSTR"
    config.hardware.keithley_2400.baud_rate = 19200
    config.hardware.keithley_2400.read_termination = "\n"
    config.hardware.mfc_controller.port = "ASRL2::INSTR"
    measurement = replace(
        config.measurement,
        mode="constant_current",
        pulsed=True,
        source_current=0.5e-6,
        voltage_compliance=7,
        settling_s=0.02,
        nplc=5,
        source_auto_range=False,
    )
    recipe = tmp_path / "original_recipe.yaml"
    recipe.write_text(
        "# preserve this exact recipe\nsteps:\n  - name: Gas\n"
        "    duration: 2\n    mfc_flows: {1: 21}\n"
    )
    exported = tmp_path / "export" / "test.yaml"
    info = save_profile(
        exported, config, measurement, config.gate, {1: 42}, True, "recipe", recipe
    )
    raw = yaml.safe_load(exported.read_text())
    assert info["sha256"] and raw["configuration_version"] == 1
    for device in connection_values(config):
        assert "port" not in raw["hardware"][device]
        assert "baud_rate" not in raw["hardware"][device]
        assert "read_termination" not in raw["hardware"][device]
    copied = exported.parent / raw["experiment"]["recipe_file"]
    assert copied.read_bytes() == recipe.read_bytes()
    # Repeated saves with the same recipe remain valid.
    save_profile(
        exported, config, measurement, config.gate, {1: 42}, True, "recipe", recipe
    )
    destination = tmp_path / "other_computer"
    shutil.copytree(exported.parent, destination)
    recipe.unlink()
    other = Config(tmp_path / "startup.yaml").load()
    other.hardware.keithley_2400.port = "ASRL9::INSTR"
    other.hardware.keithley_2400.baud_rate = 4800
    other.hardware.keithley_2400.read_termination = "\r"
    loaded = load_profile(destination / "test.yaml", other)
    assert asdict(loaded.measurement) == asdict(measurement)
    assert loaded.hardware.keithley_2400.port == "ASRL9::INSTR"
    assert loaded.hardware.keithley_2400.baud_rate == 4800
    assert loaded.hardware.keithley_2400.read_termination == "\r"
    assert loaded.manual_flows[1] == 42 and loaded.manual_shutter_open
    assert loaded.acquisition_mode == "recipe"
    assert load_recipe(loaded.recipe_file, loaded, loaded.gate)[0].flows[1] == 21
    assert load_failure_flows(loaded)[1] == 12
    assert load_failure_flows(loaded)[2] == 3
    assert loaded.logging == config.logging
    assert loaded.configuration_source["path"] == str(destination / "test.yaml")


def test_local_ports_persist_without_becoming_experiment_settings(
    profile_config, tmp_path
):
    config = profile_config
    config.hardware.keithley_2400.port = "ASRL/dev/ttyUSB0::INSTR"
    config.hardware.keithley_2400.baud_rate = 38400
    path = tmp_path / "local" / "connections.yaml"
    save_local_connections(config, path)
    loaded = Config(tmp_path / "startup.yaml").load()
    load_local_connections(loaded, path)
    assert connection_values(loaded) == connection_values(config)
    assert "measurement" not in yaml.safe_load(path.read_text())
    before = connection_values(loaded)
    with pytest.raises(ValueError):
        apply_connections(loaded, {"keithley_2400": {"port": "new", "baud_rate": -1}})
    assert connection_values(loaded) == before


def test_missing_ports_and_duplicate_serial_aliases(profile_config):
    config = profile_config
    config.hardware.use_mock = False
    config.hardware.shutter.enabled = False
    assert len(connection_problems(config, config.measurement)) == 2
    config.hardware.keithley_2400.port = "COM1"
    config.hardware.mfc_controller.port = "ASRL1::INSTR"
    assert "more than one" in connection_problems(config, config.measurement)[0]
    config.hardware.mfc_controller.port = "ASRL2::INSTR"
    assert connection_problems(config, config.measurement) == []
    config.hardware.shutter.enabled = True
    assert "shutter" in connection_problems(config, config.measurement)[0]
    config.hardware.use_mock = True
    assert connection_problems(config, config.measurement) == []


def test_bad_recipe_and_failed_save_preserve_previous_profile(
    profile_config, tmp_path, monkeypatch
):
    from gas_sensing_app.config import profiles

    path = tmp_path / "experiment.yaml"
    config = profile_config
    save_profile(
        path, config, config.measurement, config.gate, {}, False, "manual", None
    )
    previous = path.read_bytes()
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("steps: []")
    with pytest.raises(ValueError):
        save_profile(
            path, config, config.measurement, config.gate, {}, False, "recipe", invalid
        )
    assert path.read_bytes() == previous
    monkeypatch.setattr(profiles.os, "replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError):
        save_profile(
            path,
            config,
            config.measurement,
            config.gate,
            {1: 20},
            False,
            "manual",
            None,
        )
    assert path.read_bytes() == previous


def test_unsupported_profile_and_missing_recipe_rejected(profile_config, tmp_path):
    path = tmp_path / "profile.yaml"
    path.write_text("configuration_version: 99")
    with pytest.raises(ValueError, match="version"):
        load_profile(path, profile_config)
    save_profile(
        path,
        profile_config,
        profile_config.measurement,
        profile_config.gate,
        {},
        False,
        "manual",
        None,
    )
    raw = yaml.safe_load(path.read_text())
    raw["experiment"] = {"mode": "recipe", "recipe_file": "missing.yaml"}
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(FileNotFoundError):
        load_profile(path, profile_config)


def test_bundle_move_replace_and_manual_without_recipe(profile_config, tmp_path):
    from gas_sensing_app.config.profiles import save_profile_bundle

    config = profile_config
    recipe = tmp_path / "original.yaml"
    recipe.write_text("# exact copy\nsteps: [{duration: 1, mfc_flows: {1: 10}}]")
    folder = tmp_path / "configurations" / "Gas test"

    def save(recipe_path, mode="recipe"):
        return save_profile_bundle(
            folder,
            config,
            config.measurement,
            config.gate,
            {},
            False,
            mode,
            recipe_path,
        )

    info = save(recipe)
    assert Path(info["path"]) == folder / "Gas test.config.yaml"
    assert {p.name for p in folder.iterdir()} == {
        "Gas test.config.yaml",
        "Gas test.recipe.yaml",
    }
    assert (folder / "Gas test.recipe.yaml").read_bytes() == recipe.read_bytes()
    raw = yaml.safe_load((folder / "Gas test.config.yaml").read_text())
    assert raw["experiment"]["recipe_file"] == "Gas test.recipe.yaml"
    moved = tmp_path / "other_computer" / "Gas test"
    moved.parent.mkdir()
    shutil.copytree(folder, moved)
    recipe.unlink()
    loaded = load_profile(moved / "Gas test.config.yaml", config)
    assert load_recipe(loaded.recipe_file, loaded, loaded.gate)[0].flows[1] == 10
    # Updating from the bundle's own recipe must also work.
    (folder / "notes.txt").write_text("Keep my notes")
    save(folder / "Gas test.recipe.yaml")
    save(None, "manual")
    assert not (folder / "Gas test.recipe.yaml").exists()
    assert (folder / "notes.txt").read_text() == "Keep my notes"
    assert load_profile(folder / "Gas test.config.yaml", config).recipe_file is None


def test_bundle_failed_replacement_restores_both_files(
    profile_config, tmp_path, monkeypatch
):
    from gas_sensing_app.config import profiles

    config = profile_config
    folder = tmp_path / "bundle"
    recipe = tmp_path / "recipe.yaml"
    recipe.write_text("steps: [{duration: 1, mfc_flows: {1: 10}}]")

    def save():
        profiles.save_profile_bundle(
            folder,
            config,
            config.measurement,
            config.gate,
            {},
            False,
            "recipe",
            recipe,
        )

    save()
    previous = {p.name: p.read_bytes() for p in folder.iterdir()}
    recipe.write_text("steps: [{duration: 2, mfc_flows: {1: 20}}]")
    original_replace = profiles.os.replace

    def fail_install(source, destination):
        if (
            Path(destination) == folder / "bundle.recipe.yaml"
            and Path(source).name == "bundle.recipe.yaml"
        ):
            raise OSError("disk error")
        return original_replace(source, destination)

    monkeypatch.setattr(profiles.os, "replace", fail_install)
    with pytest.raises(OSError, match="disk error"):
        save()
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == previous
    assert not list(tmp_path.glob(".configuration-*"))
    assert load_profile(folder / "bundle.config.yaml", config).recipe_file


def test_shipped_configuration_example_is_portable(profile_config):
    path = (
        Path(__file__).parents[1]
        / "src/gas_sensing_app/assets/configuration.example"
        / "configuration.example.config.yaml"
    )
    loaded = load_profile(path, profile_config)
    assert loaded.acquisition_mode == "recipe"
    assert Path(loaded.recipe_file) == path.parent / "configuration.example.recipe.yaml"
    assert load_recipe(loaded.recipe_file, loaded, loaded.gate)
