from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "data" / "output"

RUNS_DIR = OUTPUT_ROOT / "01_runs"
TABLES_DIR = OUTPUT_ROOT / "02_tables"
REPORTS_DIR = OUTPUT_ROOT / "03_reports"


def ensure_output_dirs() -> None:
    for d in (RUNS_DIR, TABLES_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _run_csv_name(tag: str) -> str:
    return f"prior_sensitivity_runs_multi_{tag}.csv"


def _roi_csv_name(tag: str) -> str:
    return f"prior_sensitivity_roi_multi_{tag}.csv"


def _tornado_csv_name(tag: str) -> str:
    return f"tornado_{tag}.csv"


def _report_input_csv_name(tag: str) -> str:
    return f"prior_sensitivity_report_input_{tag}.csv"


def runs_tag_dir(tag: str, base_dir: Path = RUNS_DIR) -> Path:
    return base_dir / tag


def tables_tag_dir(tag: str, base_dir: Path = TABLES_DIR) -> Path:
    return base_dir / tag


def reports_tag_dir(tag: str, base_dir: Path = REPORTS_DIR) -> Path:
    return base_dir / tag


def run_csv_path(tag: str, base_dir: Path = RUNS_DIR) -> Path:
    return runs_tag_dir(tag, base_dir) / _run_csv_name(tag)


def roi_csv_path(tag: str, base_dir: Path = RUNS_DIR) -> Path:
    return runs_tag_dir(tag, base_dir) / _roi_csv_name(tag)


def tornado_csv_path(tag: str, base_dir: Path = TABLES_DIR) -> Path:
    return tables_tag_dir(tag, base_dir) / _tornado_csv_name(tag)


def report_input_csv_path(tag: str, base_dir: Path = TABLES_DIR) -> Path:
    return tables_tag_dir(tag, base_dir) / _report_input_csv_name(tag)
