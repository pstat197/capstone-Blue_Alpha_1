from __future__ import annotations

import os
import json
import re
import csv
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from backend.app.schemas.run import ChannelRunProgress, RunStatus
from backend.app.services.paths import PROJECT_ROOT, RUNS_DIR, ensure_storage_dirs
from backend.app.services.result_locator import locate_result_artifacts
from backend.app.services.saved_result_identity import register_completed_result

MAX_PHASE5A_REAL_RUNS = 3
REQUIRED_MODEL_MODULES = ("platformdirs", "tensorflow", "tensorflow_probability", "meridian")
PROGRESS_LINE_RE = re.compile(
    r"\[done\s+(?P<completed>\d+)\s*/\s*(?P<total>\d+)\]\s+"
    r"run_index=(?P<run_index>\d+)\s+"
    r"mu=(?P<mu>[^\s]+)\s+sigma=(?P<sigma>[^\s]+)\s+dist=(?P<dist>[^\s]+)"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_path(run_id: str) -> Path:
    ensure_storage_dirs()
    return RUNS_DIR / f"{run_id}.json"


def _write_run(status: RunStatus) -> RunStatus:
    path = _run_path(status.run_id)
    raw = status.model_dump_json(indent=2) if hasattr(status, "model_dump_json") else status.json(indent=2)
    path.write_text(raw, encoding="utf-8")
    return status


def _append_message_once(status: RunStatus, message: str) -> None:
    if message not in status.messages:
        status.messages.append(message)


def _config_for_status(status: RunStatus) -> dict[str, Any]:
    if not status.config_path:
        return {}
    try:
        raw = yaml.safe_load(Path(status.config_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _config_from_request_preview(preview: dict[str, Any]) -> dict[str, Any]:
    normalized = preview.get("normalized_config")
    if isinstance(normalized, dict):
        return deepcopy(normalized)
    return deepcopy(preview)


def _first_list_value(raw: Any, fallback: Any) -> Any:
    if isinstance(raw, list) and raw:
        return raw[0]
    return fallback


def _build_tiny_config(base_config: dict[str, Any], run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    model = base_config.setdefault("model", {})
    channels = model.get("channels")
    if not isinstance(channels, list) or not channels:
        channels = ["meta"]

    run_mode = "phase5a_real_tiny"
    source_run_mode = str(base_config.get("run_mode", "roi_full"))
    source_modes = base_config.get("run_modes") if isinstance(base_config.get("run_modes"), dict) else {}
    source_profile = source_modes.get(source_run_mode) if isinstance(source_modes.get(source_run_mode), dict) else {}
    source_channel_grids = source_profile.get("channel_prior_grids") if isinstance(source_profile.get("channel_prior_grids"), dict) else {}
    target_channel = str(channels[0])
    for channel in channels:
        grid = source_channel_grids.get(str(channel))
        if not isinstance(grid, dict) or grid.get("enabled", True):
            target_channel = str(channel)
            break

    sampler = base_config.get("sampler") if isinstance(base_config.get("sampler"), dict) else {}
    target_grid = source_channel_grids.get(target_channel) if isinstance(source_channel_grids.get(target_channel), dict) else {}
    mu = float(_first_list_value(target_grid.get("roi_mu_values") or source_profile.get("roi_mu_values"), 1.0))
    sigma = float(_first_list_value(target_grid.get("roi_sigma_values") or source_profile.get("roi_sigma_values"), 1.0))
    dist = str(_first_list_value(target_grid.get("roi_dist_values") or source_profile.get("roi_dist_values"), "LogNormal"))

    output_tag = f"phase5a_tiny_{run_id}"
    tiny_config: dict[str, Any] = deepcopy(base_config)
    tiny_config["run_mode"] = run_mode
    tiny_config["parallel_workers"] = 1
    tiny_config["run_modes"] = {
        run_mode: {
            "roi_mu_values": [mu],
            "roi_sigma_values": [sigma],
            "roi_dist_values": [dist],
            "n_chains": max(1, int(sampler.get("n_chains", 1))),
            "n_adapt": max(0, min(int(sampler.get("n_adapt", 50)), 50)),
            "n_burnin": max(0, min(int(sampler.get("n_burnin", 50)), 50)),
            "n_keep": max(1, min(int(sampler.get("n_keep", 50)), 50)),
        }
    }
    tiny_config["model"] = {
        **(tiny_config.get("model") if isinstance(tiny_config.get("model"), dict) else {}),
        "channels": [target_channel],
    }
    tiny_config["defaults"] = {"targets": [target_channel], "target_sets": None}
    tiny_config["baseline"] = {"roi_mu": mu, "roi_sigma": sigma, "roi_dist": dist}
    tiny_config["sweep"] = {
        "type": "fixed_full_grid",
        "prior_grid_scope": "full_grid",
        "structural_grid_scope": "full_grid",
        "allow_reduced_prior_grid": True,
    }
    tiny_config["structural"] = {
        "alpha_m_values": [_first_list_value((base_config.get("structural") or {}).get("alpha_m_values"), 0.3)],
        "ec_m_values": [_first_list_value((base_config.get("structural") or {}).get("ec_m_values"), 0.5)],
        "slope_m_values": [_first_list_value((base_config.get("structural") or {}).get("slope_m_values"), 1.2)],
        "max_lag_values": [_first_list_value((base_config.get("structural") or {}).get("max_lag_values"), 4)],
        "adstock_decay_values": [
            _first_list_value((base_config.get("structural") or {}).get("adstock_decay_values"), "geometric")
        ],
    }
    tiny_config["sampler"] = {
        "n_chains": tiny_config["run_modes"][run_mode]["n_chains"],
        "n_adapt": tiny_config["run_modes"][run_mode]["n_adapt"],
        "n_burnin": tiny_config["run_modes"][run_mode]["n_burnin"],
        "n_keep": tiny_config["run_modes"][run_mode]["n_keep"],
        "seed": int(sampler.get("seed", 0)),
    }
    tiny_config["output"] = {
        "tag": output_tag,
        "runs_dir": f"data/output/01_runs/{output_tag}/",
        "tables_dir": f"data/output/02_tables/{output_tag}/",
        "report_dir": f"data/output/03_reports/report/{output_tag}/",
    }

    metadata = {
        "output_tag": output_tag,
        "target_channel": target_channel,
        "mu": mu,
        "sigma": sigma,
        "dist": dist,
        "estimated_run_count": 1,
    }
    return tiny_config, metadata


def _active_channel_totals(config: dict[str, Any]) -> list[tuple[str, int]]:
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    raw_channels = model.get("channels")
    channels = [str(channel) for channel in raw_channels] if isinstance(raw_channels, list) else []

    run_mode = str(config.get("run_mode", "roi_full"))
    modes = config.get("run_modes") if isinstance(config.get("run_modes"), dict) else {}
    active = modes.get(run_mode) if isinstance(modes.get(run_mode), dict) else {}
    default_mu_values = active.get("roi_mu_values") if isinstance(active.get("roi_mu_values"), list) else [1.0]
    default_sigma_values = active.get("roi_sigma_values") if isinstance(active.get("roi_sigma_values"), list) else [1.0]
    default_dist_values = active.get("roi_dist_values") if isinstance(active.get("roi_dist_values"), list) else ["LogNormal"]
    channel_grids = active.get("channel_prior_grids") if isinstance(active.get("channel_prior_grids"), dict) else {}

    totals: list[tuple[str, int]] = []
    for channel in channels:
        grid = channel_grids.get(channel) if isinstance(channel_grids.get(channel), dict) else {}
        if grid and not grid.get("enabled", True):
            continue
        mu_values = grid.get("roi_mu_values") if isinstance(grid.get("roi_mu_values"), list) else default_mu_values
        sigma_values = grid.get("roi_sigma_values") if isinstance(grid.get("roi_sigma_values"), list) else default_sigma_values
        dist_values = grid.get("roi_dist_values") if isinstance(grid.get("roi_dist_values"), list) else default_dist_values
        totals.append((channel, len(mu_values) * len(sigma_values) * len(dist_values)))
    return totals


def _build_full_config(base_config: dict[str, Any], run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    full_config: dict[str, Any] = deepcopy(base_config)
    output_tag = f"full_grid_{run_id}"
    full_config["output"] = {
        "tag": output_tag,
        "runs_dir": f"data/output/01_runs/{output_tag}/",
        "tables_dir": f"data/output/02_tables/{output_tag}/",
        "report_dir": f"data/output/03_reports/report/{output_tag}/",
    }
    channel_totals = _active_channel_totals(full_config)
    total_runs = sum(total for _, total in channel_totals)
    first_channel = channel_totals[0][0] if channel_totals else None
    metadata = {
        "output_tag": output_tag,
        "estimated_run_count": total_runs,
        "channel_totals": channel_totals,
        "target_channel": first_channel,
    }
    return full_config, metadata


def _resolve_pipeline_python() -> str:
    forced = os.environ.get("BLUEALPHA_PIPELINE_PYTHON")
    if forced and Path(forced).exists():
        return forced
    project_venv = PROJECT_ROOT / ".venv" / "bin" / "python"
    if project_venv.exists():
        return str(project_venv)
    return sys.executable


def _pipeline_env() -> dict[str, str]:
    env = os.environ.copy()
    env["TF_CPP_MIN_LOG_LEVEL"] = "3"
    env["TF_ENABLE_ONEDNN_OPTS"] = "0"
    cache_dir = PROJECT_ROOT / ".cache"
    env.setdefault("BLUEALPHA_CACHE_DIR", str(cache_dir))
    env.setdefault("MPLCONFIGDIR", str(cache_dir / "matplotlib"))
    env.setdefault("XDG_CACHE_HOME", str(cache_dir))
    env.setdefault("ARVIZ_HOME", str(cache_dir / "arviz"))
    return env


def _preflight_pipeline_python(python_executable: str, env: dict[str, str]) -> tuple[bool, str]:
    script = (
        "import importlib.util, sys\n"
        f"required = {REQUIRED_MODEL_MODULES!r}\n"
        "missing = [name for name in required if importlib.util.find_spec(name) is None]\n"
        "if missing:\n"
        "    print('Missing required modeling modules: ' + ', '.join(missing))\n"
        "    print('Install root requirements.txt into the selected interpreter or set BLUEALPHA_PIPELINE_PYTHON.')\n"
        "    sys.exit(1)\n"
        "print('Modeling runtime preflight passed.')\n"
    )
    try:
        result = subprocess.run(
            [python_executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
    except Exception as exc:
        return False, f"Could not validate modeling runtime {python_executable}: {exc}"

    output = result.stdout.strip()
    if result.returncode != 0:
        return False, output or "Selected modeling runtime is missing required modeling modules."
    return True, output or "Modeling runtime preflight passed."


def _read_log_tail(log_path: str | None, limit: int = 80) -> list[str]:
    if not log_path:
        return []
    path = Path(log_path)
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]


def _classify_failure(lines: list[str]) -> str:
    text = "\n".join(lines).lower()
    if "modulenotfounderror" in text or "no module named" in text or "importerror" in text:
        return "dependency/environment issue"
    if (
        "config field" in text
        or "config yaml" in text
        or "configured data csv does not exist" in text
        or "missing spend columns" in text
        or "valueerror" in text
    ):
        return "config validation issue"
    if "dashboard payload not found" in text or "missing output" in text:
        return "missing output artifact issue"
    if "runtimeerror" in text or "traceback" in text or "subprocess failed" in text:
        return "pipeline runtime issue"
    return "pipeline failure"


def _failure_summary(lines: list[str]) -> str:
    for line in reversed(lines):
        clean = line.strip()
        if clean and (
            "Error" in clean
            or "Exception" in clean
            or "No module named" in clean
            or "failed" in clean.lower()
        ):
            return clean[-500:]
    return "See run logs for the detailed failure."


def _parse_float(raw: str) -> float | None:
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_progress_line(line: str) -> dict[str, Any] | None:
    match = PROGRESS_LINE_RE.search(line)
    if not match:
        return None
    return {
        "completed": int(match.group("completed")),
        "total": int(match.group("total")),
        "run_index": int(match.group("run_index")),
        "mu": _parse_float(match.group("mu")),
        "sigma": _parse_float(match.group("sigma")),
        "dist": match.group("dist"),
    }


def _channel_for_run_index(status: RunStatus, run_index: int) -> str | None:
    if run_index <= 0:
        return status.channel_progress[0].channel if status.channel_progress else None

    zero_based = run_index - 1
    offset = 0
    for channel in status.channel_progress:
        next_offset = offset + max(0, int(channel.total_runs))
        if offset <= zero_based < next_offset:
            return channel.channel
        offset = next_offset
    return None


def _apply_progress_events(status: RunStatus, events: list[dict[str, Any]]) -> bool:
    if not events:
        return False

    latest = events[-1]
    total_runs = max(int(latest.get("total") or 0), int(status.progress.total_runs or 0))
    completed_runs = min(total_runs, max(int(event.get("completed") or 0) for event in events))
    prior_completed = int(status.progress.completed_runs or 0)
    prior_total = int(status.progress.total_runs or 0)
    prior_active = status.progress.active_target_channel

    channel_run_indexes = {channel.channel: set() for channel in status.channel_progress}
    for event in events:
        channel_name = _channel_for_run_index(status, int(event.get("run_index") or 0))
        if channel_name in channel_run_indexes:
            channel_run_indexes[channel_name].add(int(event.get("run_index") or 0))

    latest_channel = _channel_for_run_index(status, int(latest.get("run_index") or 0))
    first_incomplete: str | None = None
    for channel in status.channel_progress:
        completed_for_channel = min(int(channel.total_runs), len(channel_run_indexes.get(channel.channel, set())))
        if completed_for_channel < int(channel.total_runs) and first_incomplete is None:
            first_incomplete = channel.channel
        channel.completedRuns = completed_for_channel
        channel.failedRuns = 0
        if completed_for_channel >= int(channel.total_runs):
            channel.status = "completed"
        elif completed_for_channel > 0 or channel.channel == latest_channel:
            channel.status = "running"
        else:
            channel.status = "queued"

    active_channel = None if completed_runs >= total_runs else latest_channel or first_incomplete
    if active_channel:
        for channel in status.channel_progress:
            if channel.channel == active_channel and channel.status == "queued":
                channel.status = "running"
                break

    status.progress.total_runs = total_runs
    status.progress.completed_runs = completed_runs
    status.progress.failed_runs = 0
    status.progress.active_target_channel = active_channel
    status.progress.active_mu = latest.get("mu")
    status.progress.active_sigma = latest.get("sigma")
    status.progress.active_dist = latest.get("dist")

    return (
        prior_completed != status.progress.completed_runs
        or prior_total != status.progress.total_runs
        or prior_active != status.progress.active_target_channel
    )


def _is_process_alive(process_id: int | None) -> bool:
    if not process_id:
        return False
    try:
        os.kill(int(process_id), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _age_seconds(raw: str | None) -> float:
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _runs_csv_path(output_tag: str | None) -> Path | None:
    if not output_tag:
        return None
    runs_dir = PROJECT_ROOT / "data" / "output" / "01_runs" / output_tag
    if not runs_dir.exists():
        return None
    matches = sorted(
        runs_dir.glob(f"prior_sensitivity_runs_*{output_tag}.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return matches[0] if matches else None


def _apply_artifact_progress(status: RunStatus) -> bool:
    path = _runs_csv_path(status.output_tag)
    if not path:
        return False

    prior_completed = int(status.progress.completed_runs or 0)
    prior_failed = int(status.progress.failed_runs or 0)
    prior_active = status.progress.active_target_channel
    prior_status = status.status
    prior_result_url = status.result_url
    prior_completed_at = status.completed_at

    seen_run_ids: set[str] = set()
    channel_counts = {channel.channel: 0 for channel in status.channel_progress}
    try:
        with path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row_index, row in enumerate(reader):
                run_key = str(row.get("run_id") or row_index)
                if run_key in seen_run_ids:
                    continue
                seen_run_ids.add(run_key)
                channel_name = str(row.get("target_channel") or "").strip()
                if channel_name in channel_counts:
                    channel_counts[channel_name] += 1
    except Exception:
        return False

    artifact_completed = min(int(status.progress.total_runs or len(seen_run_ids)), len(seen_run_ids))
    status.progress.completed_runs = max(prior_completed, artifact_completed)
    status.progress.failed_runs = max(0, int(status.progress.failed_runs or 0))

    first_incomplete: str | None = None
    for channel in status.channel_progress:
        completed_for_channel = min(int(channel.total_runs), max(channel.completedRuns, channel_counts.get(channel.channel, 0)))
        channel.completedRuns = completed_for_channel
        if completed_for_channel >= int(channel.total_runs):
            channel.status = "completed"
            channel.failedRuns = 0
        elif first_incomplete is None:
            first_incomplete = channel.channel
            channel.status = "running" if _is_process_alive(status.process_id) else channel.status

    total_runs = int(status.progress.total_runs or 0)
    process_alive = _is_process_alive(status.process_id)
    if total_runs > 0 and status.progress.completed_runs >= total_runs:
        status.progress.active_target_channel = None
        status.result_artifacts = locate_result_artifacts(status.output_tag or "")
        if status.result_artifacts.get("dashboard_payload"):
            status.status = "completed"
            status.completed_at = status.completed_at or _now_iso()
            status.result_url = f"/results/overview?run_id={status.run_id}"
            record = register_completed_result(status, _config_for_status(status))
            if record and record.get("history_id"):
                status.history_id = str(record["history_id"])
                status.result_url = f"/results/overview?history_id={record['history_id']}"
            _append_message_once(status, "Recovered completed run state from output artifacts.")
        elif not process_alive and status.status in {"queued", "running"}:
            status.status = "failed"
            status.completed_at = status.completed_at or _now_iso()
            status.progress.failed_runs = 0
            _append_message_once(
                status,
                "Run process is no longer active. Model outputs completed, but dashboard results were not generated.",
            )
    elif not process_alive and status.status in {"queued", "running"} and status.progress.completed_runs > 0:
        status.status = "failed"
        status.completed_at = status.completed_at or _now_iso()
        status.progress.failed_runs = max(0, total_runs - status.progress.completed_runs)
        status.progress.active_target_channel = None
        for channel in status.channel_progress:
            if channel.completedRuns < channel.total_runs:
                channel.failedRuns = channel.total_runs - channel.completedRuns
                channel.status = "failed"
        _append_message_once(status, "Run process is no longer active before all model fits completed.")
    else:
        status.progress.active_target_channel = first_incomplete

    return (
        prior_completed != status.progress.completed_runs
        or prior_failed != status.progress.failed_runs
        or prior_active != status.progress.active_target_channel
        or prior_status != status.status
        or prior_result_url != status.result_url
        or prior_completed_at != status.completed_at
    )


def sync_run_progress_from_logs(status: RunStatus) -> RunStatus:
    if status.mode not in {"real_tiny", "real_full"} or status.status not in {"queued", "running"}:
        return status
    changed = False
    if status.log_path:
        path = Path(status.log_path)
        if path.exists():
            events = [
                event
                for event in (_parse_progress_line(line) for line in path.read_text(encoding="utf-8", errors="replace").splitlines())
                if event is not None
            ]
            if events and status.status == "queued":
                status.status = "running"
                changed = True
            changed = _apply_progress_events(status, events) or changed
    changed = _apply_artifact_progress(status) or changed
    if (
        not changed
        and status.status == "running"
        and status.process_id
        and not _is_process_alive(status.process_id)
        and _age_seconds(status.started_at) > 30
    ):
        status.status = "failed"
        status.completed_at = status.completed_at or _now_iso()
        status.progress.failed_runs = max(1, status.progress.total_runs - status.progress.completed_runs)
        status.progress.active_target_channel = None
        for channel in status.channel_progress:
            if channel.completedRuns < channel.total_runs:
                channel.failedRuns = channel.total_runs - channel.completedRuns
                channel.status = "failed"
        _append_message_once(status, "Run process is no longer active and no completed model-output artifact was found.")
        changed = True
    if changed:
        return _write_run(status)
    return status


def _identity_fields(identity: dict[str, Any] | None) -> dict[str, Any]:
    if not identity:
        return {}
    return {
        "display_result_id": identity.get("display_result_id"),
        "config_fingerprint": identity.get("config_fingerprint"),
        "original_csv_filename": identity.get("original_csv_filename"),
        "csv_name_prefix": identity.get("csv_name_prefix"),
        "dataset_hash": identity.get("dataset_hash"),
    }


def create_real_tiny_run_status(run_id: str, workflow_id: str, approved_config_preview: dict[str, Any], identity: dict[str, Any] | None = None) -> RunStatus:
    base_config = _config_from_request_preview(approved_config_preview)
    tiny_config, metadata = _build_tiny_config(base_config, run_id)
    estimated_run_count = int(metadata["estimated_run_count"])
    if estimated_run_count > MAX_PHASE5A_REAL_RUNS:
        raise ValueError(
            f"Phase 5A real execution is limited to {MAX_PHASE5A_REAL_RUNS} runs; requested {estimated_run_count}."
        )

    work_dir = RUNS_DIR / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "config.yaml"
    log_path = work_dir / "run.log"
    config_path.write_text(yaml.safe_dump(tiny_config, sort_keys=False), encoding="utf-8")
    log_path.write_text(
        "Phase 5A tiny real run queued.\n"
        f"Generated config: {config_path}\n"
        f"Output tag: {metadata['output_tag']}\n",
        encoding="utf-8",
    )

    status = RunStatus(
        run_id=run_id,
        workflow_id=workflow_id,
        status="queued",
        created_at=_now_iso(),
        progress={
            "total_runs": estimated_run_count,
            "completed_runs": 0,
            "failed_runs": 0,
            "active_target_channel": str(metadata["target_channel"]),
            "active_mu": float(metadata["mu"]),
            "active_sigma": float(metadata["sigma"]),
            "active_dist": str(metadata["dist"]),
        },
        channel_progress=[
            ChannelRunProgress(channel=str(metadata["target_channel"]), total_runs=estimated_run_count)
        ],
        messages=[
            "Phase 5A real_tiny run submitted.",
            "Launcher will execute at most one target/channel prior point.",
        ],
        monitor_url=f"/runs/{run_id}/monitor",
        mode="real_tiny",
        work_dir=str(work_dir),
        config_path=str(config_path),
        log_path=str(log_path),
        output_tag=str(metadata["output_tag"]),
        **_identity_fields(identity),
    )
    return _write_run(status)


def create_real_full_run_status(run_id: str, workflow_id: str, approved_config_preview: dict[str, Any], identity: dict[str, Any] | None = None) -> RunStatus:
    base_config = _config_from_request_preview(approved_config_preview)
    full_config, metadata = _build_full_config(base_config, run_id)
    estimated_run_count = int(metadata["estimated_run_count"])
    if estimated_run_count <= 0:
        raise ValueError("Full grid run requires at least one enabled prior-grid model fit.")

    work_dir = RUNS_DIR / run_id
    work_dir.mkdir(parents=True, exist_ok=True)
    config_path = work_dir / "config.yaml"
    log_path = work_dir / "run.log"
    config_path.write_text(yaml.safe_dump(full_config, sort_keys=False), encoding="utf-8")
    log_path.write_text(
        "Full grid real run queued.\n"
        f"Generated config: {config_path}\n"
        f"Output tag: {metadata['output_tag']}\n"
        f"Estimated model fits: {estimated_run_count}\n",
        encoding="utf-8",
    )

    channel_totals = [(str(channel), int(total)) for channel, total in metadata["channel_totals"]]
    first_channel = str(metadata["target_channel"]) if metadata["target_channel"] else None
    status = RunStatus(
        run_id=run_id,
        workflow_id=workflow_id,
        status="queued",
        created_at=_now_iso(),
        progress={
            "total_runs": estimated_run_count,
            "completed_runs": 0,
            "failed_runs": 0,
            "active_target_channel": first_channel,
            "active_mu": None,
            "active_sigma": None,
            "active_dist": None,
        },
        channel_progress=[
            ChannelRunProgress(channel=channel, total_runs=total)
            for channel, total in channel_totals
        ],
        messages=[
            "Full grid real run submitted.",
            "Backend will execute the exact approved prior-grid configuration.",
            f"Estimated model fits: {estimated_run_count}.",
        ],
        monitor_url=f"/runs/{run_id}/monitor",
        mode="real_full",
        work_dir=str(work_dir),
        config_path=str(config_path),
        log_path=str(log_path),
        output_tag=str(metadata["output_tag"]),
        **_identity_fields(identity),
    )
    return _write_run(status)


def launch_real_tiny_run(status: RunStatus) -> RunStatus:
    if status.mode not in {"real_tiny", "real_full"}:
        raise ValueError("Only real runs can be launched by the Phase 5A launcher.")
    if not status.config_path or not status.log_path:
        raise ValueError("Real run is missing config/log paths.")

    dollars_per_subscription = 100.0
    try:
        config = yaml.safe_load(Path(status.config_path).read_text(encoding="utf-8"))
        outcome = config.get("outcome") if isinstance(config, dict) and isinstance(config.get("outcome"), dict) else {}
        maybe_revenue_per_kpi = outcome.get("revenue_per_kpi")
        if maybe_revenue_per_kpi is not None:
            dollars_per_subscription = float(maybe_revenue_per_kpi)
    except Exception:
        dollars_per_subscription = 100.0

    pipeline_python = _resolve_pipeline_python()
    env = _pipeline_env()
    preflight_ok, preflight_message = _preflight_pipeline_python(pipeline_python, env)
    log_path = Path(str(status.log_path))
    if not preflight_ok:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write("Modeling runtime preflight failed.\n")
            log_file.write(f"Python executable: {pipeline_python}\n")
            log_file.write(f"Working directory: {PROJECT_ROOT}\n")
            log_file.write(preflight_message + "\n")
        status.status = "failed"
        status.completed_at = _now_iso()
        status.progress.failed_runs = status.progress.total_runs
        for channel in status.channel_progress:
            channel.status = "failed"
            channel.failedRuns = channel.total_runs
        status.messages.append(f"Modeling runtime preflight failed: {preflight_message}")
        return _write_run(status)

    cmd = [
        pipeline_python,
        "-m",
        "src.pipeline",
        "--config",
        status.config_path,
        "--dollars-per-subscription",
        str(dollars_per_subscription),
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
    except Exception as exc:
        log_path = Path(str(status.log_path))
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write("Failed to start pipeline subprocess: " + str(exc) + "\n")
        status.status = "failed"
        status.completed_at = _now_iso()
        status.progress.failed_runs = status.progress.total_runs
        for channel in status.channel_progress:
            channel.status = "failed"
            channel.failedRuns = channel.total_runs
        status.messages.append(f"Pipeline subprocess could not be started: {exc}")
        return _write_run(status)

    status.status = "running"
    status.started_at = _now_iso()
    status.process_id = int(proc.pid)
    if status.channel_progress:
        status.channel_progress[0].status = "running"
    status.messages.append(
        "Pipeline subprocess started for full grid real run."
        if status.mode == "real_full"
        else "Pipeline subprocess started for Phase 5A tiny real run."
    )
    _write_run(status)

    def _watch() -> None:
        current = status
        progress_events: list[dict[str, Any]] = []
        log_path = Path(str(status.log_path))
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(preflight_message + "\n")
            log_file.write(f"Python executable: {pipeline_python}\n")
            log_file.write(f"Working directory: {PROJECT_ROOT}\n")
            log_file.write("MPLCONFIGDIR: " + env.get("MPLCONFIGDIR", "") + "\n")
            log_file.write("XDG_CACHE_HOME: " + env.get("XDG_CACHE_HOME", "") + "\n")
            log_file.write("Command: " + " ".join(cmd) + "\n")
            if proc.stdout is not None:
                for line in proc.stdout:
                    log_file.write(line)
                    log_file.flush()
                    progress_event = _parse_progress_line(line)
                    if progress_event is not None:
                        progress_events.append(progress_event)
                        try:
                            current = RunStatus(**json.loads(_run_path(status.run_id).read_text(encoding="utf-8")))
                            if current.status in {"queued", "running"}:
                                current.status = "running"
                                _apply_progress_events(current, progress_events)
                                _write_run(current)
                        except Exception:
                            pass
        returncode = proc.wait()
        current = RunStatus(**json.loads(_run_path(status.run_id).read_text(encoding="utf-8")))
        current.completed_at = _now_iso()
        current.result_artifacts = locate_result_artifacts(current.output_tag or "")
        if returncode == 0:
            current.status = "completed"
            current.progress.completed_runs = current.progress.total_runs
            current.progress.failed_runs = 0
            current.progress.active_target_channel = None
            for channel in current.channel_progress:
                channel.status = "completed"
                channel.completedRuns = channel.total_runs
            if current.result_artifacts.get("dashboard_payload"):
                record = register_completed_result(current, _config_for_status(current))
                if record and record.get("history_id"):
                    current.history_id = str(record["history_id"])
                    current.result_url = f"/results/overview?history_id={record['history_id']}"
                else:
                    current.result_url = f"/results/overview?run_id={current.run_id}"
            else:
                current.messages.append("Pipeline completed, but no dashboard_payload.json was discovered.")
            current.messages.append(
                "Full grid real run completed."
                if current.mode == "real_full"
                else "Phase 5A tiny real run completed."
            )
        else:
            log_tail = _read_log_tail(current.log_path)
            failure_type = _classify_failure(log_tail)
            failure_detail = _failure_summary(log_tail)
            current.status = "failed"
            current.progress.failed_runs = max(0, current.progress.total_runs - current.progress.completed_runs)
            current.progress.active_target_channel = None
            for channel in current.channel_progress:
                remaining = max(0, channel.total_runs - channel.completedRuns)
                channel.failedRuns = remaining
                channel.status = "completed" if remaining == 0 else "failed"
            current.messages.append(
                f"Pipeline subprocess failed with exit code {returncode}: {failure_type}. {failure_detail}"
            )
        _write_run(current)

    thread = threading.Thread(target=_watch, name=f"phase5a-{status.run_id}", daemon=True)
    thread.start()
    return status


def launch_real_tiny_run_async(status: RunStatus) -> RunStatus:
    queued_status = status.model_copy(deep=True) if hasattr(status, "model_copy") else status.copy(deep=True)
    thread = threading.Thread(target=launch_real_tiny_run, args=(status,), name=f"phase5a-launch-{status.run_id}", daemon=True)
    thread.start()
    return queued_status


def launch_real_full_run_async(status: RunStatus) -> RunStatus:
    queued_status = status.model_copy(deep=True) if hasattr(status, "model_copy") else status.copy(deep=True)
    thread = threading.Thread(target=launch_real_tiny_run, args=(status,), name=f"full-grid-launch-{status.run_id}", daemon=True)
    thread.start()
    return queued_status


def read_run_logs(run_id: str, limit: int = 200) -> list[str]:
    run_json = _run_path(run_id)
    if not run_json.exists():
        raise FileNotFoundError(f"Run not found: {run_id}")
    status = RunStatus(**json.loads(run_json.read_text(encoding="utf-8")))
    if not status.log_path:
        return status.messages[-limit:]
    path = Path(status.log_path)
    if not path.exists():
        return status.messages[-limit:]
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
