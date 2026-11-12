"""Workspace layout and first-run defaults."""

from pathlib import Path

DEFAULTS_DIR = Path(__file__).resolve().parents[1] / "assets" / "defaults"
WORKSPACE_FOLDERS = (
    "settings",
    "configurations",
    "recipes",
    "data",
    "console_logs",
    "logs",
)


def workspace_for_path(path):
    """Recognize files inside the standard workspace layout."""
    path = Path(path).resolve()
    for parent in path.parents:
        if parent.name == "workspace":
            return parent
    return None


def output_root(config):
    return Path(config.workspace_dir or config.base_dir)


def default_config_path(directory=None):
    return Path(directory or Path.cwd()).resolve() / "workspace/settings/config.yaml"


def initialize_workspace(directory=None):
    """Create only missing defaults; existing invalid files must be corrected."""
    from .config import Config, load_failure_flows
    from .profiles import atomic_bytes

    path = default_config_path(directory)
    workspace = path.parent.parent
    if not path.exists():
        atomic_bytes(path, (DEFAULTS_DIR / "config.template.yaml").read_bytes())
    config = Config(path).load()
    if config.shutdown_flows is None:
        safety = Path(config.base_dir) / config.safety_file
        if not safety.exists():
            atomic_bytes(
                safety, (DEFAULTS_DIR / "failure_gases.template.yaml").read_bytes()
            )
        load_failure_flows(config)
    for name in WORKSPACE_FOLDERS:
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return config


def startup_config(path=None):
    """Only default startup generates settings; explicit paths must exist."""
    if path is None:
        return initialize_workspace()
    from .config import Config, load_failure_flows

    path = Path(path).expanduser().resolve()
    workspace = workspace_for_path(path) or default_config_path().parent.parent
    config = Config(path, workspace_dir=workspace).load()
    load_failure_flows(config)
    for name in WORKSPACE_FOLDERS:
        (workspace / name).mkdir(parents=True, exist_ok=True)
    return config
