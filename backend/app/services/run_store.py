from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from backend.app.schemas.run import ChannelRunProgress, RunCreateRequest, RunStatus
from backend.app.services.paths import RUNS_DIR, ensure_storage_dirs
from backend.app.services.pipeline_launcher import (
    create_real_full_run_status,
    create_real_tiny_run_status,
    launch_real_full_run_async,
    launch_real_tiny_run_async,
)
from backend.app.services.workflow_store import get_workflow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_path(run_id: str):
    ensure_storage_dirs()
    return RUNS_DIR / f"{run_id}.json"


def _write_run(status: RunStatus) -> RunStatus:
    path = _run_path(status.run_id)
    if hasattr(status, "model_dump_json"):
        raw = status.model_dump_json(indent=2)
    else:
        raw = status.json(indent=2)
    path.write_text(raw, encoding="utf-8")
    return status


def _config_from_request(request: RunCreateRequest) -> dict:
    preview = request.approved_config_preview or {}
    normalized = preview.get("normalized_config")
    if isinstance(normalized, dict):
        return normalized
    return preview


def _active_grid(config: dict) -> tuple[list[str], list[float], list[float], list[str]]:
    model = config.get("model") if isinstance(config.get("model"), dict) else {}
    channels = model.get("channels")
    if not isinstance(channels, list) or not channels:
        channels = ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"]

    run_mode = config.get("run_mode", "roi_full")
    modes = config.get("run_modes") if isinstance(config.get("run_modes"), dict) else {}
    active = modes.get(run_mode) if isinstance(modes.get(run_mode), dict) else {}
    mu_values = active.get("roi_mu_values") if isinstance(active.get("roi_mu_values"), list) else [0.5, 1.0, 1.5]
    sigma_values = active.get("roi_sigma_values") if isinstance(active.get("roi_sigma_values"), list) else [0.5, 1.0]
    dist_values = active.get("roi_dist_values") if isinstance(active.get("roi_dist_values"), list) else ["LogNormal"]
    return channels, mu_values, sigma_values, dist_values


def create_run(request: RunCreateRequest) -> RunStatus:
    get_workflow(request.workflow_id)
    if request.mode == "real_full":
        run_id = f"run_{uuid4().hex[:12]}"
        status = create_real_full_run_status(run_id, request.workflow_id, request.approved_config_preview)
        return launch_real_full_run_async(status)
    if request.mode == "real_tiny":
        run_id = f"run_{uuid4().hex[:12]}"
        status = create_real_tiny_run_status(run_id, request.workflow_id, request.approved_config_preview)
        return launch_real_tiny_run_async(status)

    config = _config_from_request(request)
    channels, mu_values, sigma_values, dist_values = _active_grid(config)
    per_channel_total = len(mu_values) * len(sigma_values) * len(dist_values)
    total_runs = len(channels) * per_channel_total
    run_id = f"run_{uuid4().hex[:12]}"

    status = RunStatus(
        run_id=run_id,
        workflow_id=request.workflow_id,
        status="queued",
        created_at=_now_iso(),
        progress={
            "total_runs": total_runs,
            "completed_runs": 0,
            "failed_runs": 0,
            "active_target_channel": channels[0] if channels else None,
            "active_mu": mu_values[0] if mu_values else None,
            "active_sigma": sigma_values[0] if sigma_values else None,
            "active_dist": dist_values[0] if dist_values else None,
        },
        channel_progress=[
            ChannelRunProgress(channel=str(channel), total_runs=per_channel_total)
            for channel in channels
        ],
        messages=[
            "Mock run submitted. No Meridian process has been started.",
            "Use mode=real_tiny for the guarded Phase 5A launcher path.",
        ],
        monitor_url=f"/runs/{run_id}/monitor",
    )
    return _write_run(status)


def get_run(run_id: str) -> RunStatus:
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"Run not found: {run_id}")
    return RunStatus(**json.loads(path.read_text(encoding="utf-8")))


def advance_mock_run(run_id: str) -> RunStatus:
    status = get_run(run_id)
    if status.mode != "mock":
        raise ValueError("Mock advance is only available for mock runs.")
    if status.status in {"completed", "failed", "cancelled"}:
        status.messages.append(f"Mock advance ignored because run is already {status.status}.")
        return _write_run(status)

    if status.status == "queued":
        status.status = "running"
        status.started_at = _now_iso()
        status.messages.append("Mock worker picked up the queued run.")

    remaining_channels = [
        channel for channel in status.channel_progress
        if channel.completedRuns + channel.failedRuns < channel.total_runs
    ]
    if not remaining_channels:
        status.status = "completed"
        status.completed_at = status.completed_at or _now_iso()
        status.result_url = "/results/overview"
        status.messages.append("Mock run completed. Demo result pages remain read-only.")
        return _write_run(status)

    active = remaining_channels[0]
    active.status = "running"
    increment = max(1, min(10, active.total_runs - active.completedRuns))
    active.completedRuns += increment
    status.progress.completed_runs = sum(channel.completedRuns for channel in status.channel_progress)
    status.progress.failed_runs = sum(channel.failedRuns for channel in status.channel_progress)
    status.progress.active_target_channel = active.channel
    status.messages.append(f"Mock progress advanced {increment} run(s) for {active.channel}.")

    if active.completedRuns >= active.total_runs:
        active.status = "completed"
        status.messages.append(f"Mock channel completed: {active.channel}.")

    next_channels = [
        channel for channel in status.channel_progress
        if channel.completedRuns + channel.failedRuns < channel.total_runs
    ]
    if next_channels:
        next_channels[0].status = "running"
        status.progress.active_target_channel = next_channels[0].channel
    else:
        status.status = "completed"
        status.completed_at = _now_iso()
        status.progress.active_target_channel = None
        status.result_url = "/results/overview"
        status.messages.append("Mock run completed. Results link points to the existing demo payload.")

    return _write_run(status)


def demo_run_status() -> RunStatus:
    now = _now_iso()
    channels = ["meta", "google", "snapchat", "tiktok", "moloco", "liveintent", "beehiiv", "amazon"]
    return RunStatus(
        run_id="demo_32run",
        workflow_id="demo_workflow",
        status="completed",
        created_at=now,
        started_at=now,
        completed_at=now,
        progress={
            "total_runs": 32,
            "completed_runs": 32,
            "failed_runs": 0,
            "active_target_channel": None,
            "active_mu": None,
            "active_sigma": None,
            "active_dist": None,
        },
        channel_progress=[
            ChannelRunProgress(channel=channel, total_runs=4, completedRuns=4, status="completed")
            for channel in channels
        ],
        messages=["Demo artifacts are available. This status did not launch Meridian."],
        monitor_url="/runs/demo_32run/monitor",
        result_url="/results/overview",
    )
