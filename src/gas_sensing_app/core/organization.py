"""Readable session directories; annotation text remains unchanged in metadata."""

import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4


def safe_part(value, fallback, limit=64):
    text = unicodedata.normalize("NFKC", str(value or "").strip())
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", text)
    text = re.sub(r"\s+", "-", text).strip(" .-")
    if text.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(
        r"(COM|LPT)[1-9]", text, re.I
    ):
        text = "_" + text
    return text[:limit].rstrip(" .") or fallback


def conditions(settings):
    mode = settings.get("mode", "")
    if mode == "constant_voltage":
        level = f"{settings.get('bias_voltage', 0):g}V"
        limit = f"Ilim{settings.get('compliance', 0) * 1e6:g}uA"
    elif mode == "constant_current":
        level = f"{settings.get('source_current', 0) * 1e9:g}nA"
        limit = f"Vlim{settings.get('voltage_compliance', 0):g}V"
    else:
        return "resistance" if mode == "resistance" else "unknown-settings"
    parts = ["pulse" if settings.get("pulsed") else "DC", level, limit]
    if settings.get("pulsed"):
        parts.append(f"delay{settings.get('settling_s', 0) * 1000:g}ms")
    parts.append(f"dt{settings.get('interval_s', 0):g}s")
    return "__".join(parts)


def folder_name(stamp, device, experiment, settings, identifier):
    return "__".join(
        (
            stamp,
            safe_part("D" + device if device else "", "unknown-device", 48),
            safe_part(experiment, "unnamed", 48),
            conditions(settings),
            identifier,
        )
    )


def session_folder(root, config, settings):
    from dataclasses import asdict

    now = datetime.now(timezone.utc).astimezone()
    folder = (
        root
        / safe_part(config.sample_name, "unknown-sample")
        / folder_name(
            now.strftime("%Y-%m-%d_%H%M%S"),
            config.device,
            config.experiment_name,
            asdict(settings),
            uuid4().hex[:8],
        )
    )
    folder.mkdir(parents=True, exist_ok=False)
    return folder
