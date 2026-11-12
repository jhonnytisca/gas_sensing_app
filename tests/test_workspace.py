"""First-run setup and shared workspace output paths."""

from pathlib import Path

import pytest
import yaml

from gas_sensing_app.config.config import Config, load_failure_flows
from gas_sensing_app.config.profiles import load_profile, save_profile_bundle
from gas_sensing_app.config.workspace import (
    DEFAULTS_DIR,
    WORKSPACE_FOLDERS,
    initialize_workspace,
    output_root,
    startup_config,
)
from gas_sensing_app.core.engine import ExperimentEngine
from gas_sensing_app.results import default_data_folder


def test_first_start_creates_defaults_and_preserves_user_settings(tmp_path):
    config = initialize_workspace(tmp_path)
    root = tmp_path / "workspace"
    assert output_root(config) == root
    assert config.hardware.use_mock
    assert not config.hardware.keithley_2400.port
    assert not config.hardware.mfc_controller.port
    assert all(value == 0 for value in load_failure_flows(config).values())
    assert all((root / name).is_dir() for name in WORKSPACE_FOLDERS)
    path = root / "settings/config.yaml"
    safety = root / "settings/failure_gases.yaml"
    original = path.read_bytes()
    safety.write_text("mfc_flows: {1: 17}\n")
    config = initialize_workspace(tmp_path)
    assert path.read_bytes() == original
    assert load_failure_flows(config)[1] == 17
    safety.unlink()
    initialize_workspace(tmp_path)
    assert safety.is_file()
    safety.write_text("mfc_flows: {1: invalid}\n")
    with pytest.raises(ValueError):
        initialize_workspace(tmp_path)
    assert "invalid" in safety.read_text()
    path.write_text("configuration_version: 99\n")
    with pytest.raises(ValueError, match="version"):
        initialize_workspace(tmp_path)
    assert path.read_text() == "configuration_version: 99\n"


def test_explicit_missing_configuration_does_not_create_files(tmp_path):
    path = tmp_path / "typo/config.yaml"
    with pytest.raises(FileNotFoundError):
        startup_config(path)
    assert not path.parent.exists()
    assert not (tmp_path / "workspace").exists()


def test_previous_structure_is_ignored_and_left_for_manual_migration(tmp_path):
    legacy = tmp_path / "config.yaml"
    legacy.write_text("invalid: old settings are not read")
    safety = tmp_path / "failure_gases.yaml"
    safety.write_text("mfc_flows: {1: 15}\n")
    data = tmp_path / "data"
    data.mkdir()
    (data / "keep.csv").write_text("existing recording")
    config = initialize_workspace(tmp_path)
    assert config.hardware.use_mock
    assert load_failure_flows(config)[1] == 0
    assert legacy.read_text() == "invalid: old settings are not read"
    assert safety.read_text() == "mfc_flows: {1: 15}\n"
    assert (data / "keep.csv").read_text() == "existing recording"
    assert not (tmp_path / "workspace/data/keep.csv").exists()


def test_workspace_outputs_remain_shared_after_loading_profile(tmp_path):
    local = initialize_workspace(tmp_path)
    root = tmp_path / "workspace"
    recipe = root / "recipes/test.yaml"
    recipe.write_text("steps: [{duration: 1, mfc_flows: {1: 10}}]")
    folder = root / "configurations/test"
    save_profile_bundle(
        folder, local, local.measurement, local.gate, {}, False, "recipe", recipe
    )
    loaded = load_profile(folder / "test.config.yaml", local)
    assert output_root(loaded) == root
    assert Path(loaded.recipe_file) == folder / "test.recipe.yaml"
    assert default_data_folder(folder / "test.config.yaml") == root / "data"
    assert default_data_folder(root / "settings/config.yaml") == root / "data"
    assert "workspace_dir" not in yaml.safe_load(
        (folder / "test.config.yaml").read_text()
    )
    engine = ExperimentEngine(loaded, loaded.measurement, loaded.gate)
    try:
        engine.prepare()
        assert Path(engine.log_path).is_relative_to(root / "data")
        assert not (folder / "data").exists()
    finally:
        engine.shutdown()
    # External profiles still use the active workspace for output.
    external = tmp_path / "external.yaml"
    external.write_text((DEFAULTS_DIR / "config.template.yaml").read_text())
    (tmp_path / "failure_gases.yaml").write_text("mfc_flows: {1: 0}")
    assert output_root(load_profile(external, local)) == root
    # Absolute user-selected output paths remain absolute.
    loaded.logging.data_log.folder = str(tmp_path / "custom-results")
    assert (
        output_root(loaded) / loaded.logging.data_log.folder
        == tmp_path / "custom-results"
    )


def test_explicit_configuration_uses_workspace_output_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "custom.yaml"
    path.write_text((DEFAULTS_DIR / "config.template.yaml").read_text())
    (tmp_path / "failure_gases.yaml").write_text("mfc_flows: {1: 8}")
    config = startup_config(path)
    assert output_root(config) == tmp_path / "workspace"
    assert Config(path).load().base_dir == str(tmp_path)
    assert (tmp_path / "workspace/recipes").is_dir()
    assert not (tmp_path / "workspace/settings/config.yaml").exists()
