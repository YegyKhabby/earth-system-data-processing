"""
ERA5 daily download + archive script (converted from era5_download_only.ipynb).

Features:
- Mock mode for testing without CDS API
- Validates downloads (if xarray is available)
- Skips dates already archived (configurable)
- Archives files into YYYY/MM folders
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
import shutil

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR_BASE = BASE_DIR / "data" / "era5" / "downloads"
DATA_DIR_MOCK = DATA_DIR_BASE / "mock"
DATA_DIR_REAL = DATA_DIR_BASE / "real"

ARCHIVE_DIR_BASE = BASE_DIR / "data" / "era5" / "archive"
ARCHIVE_DIR_MOCK = ARCHIVE_DIR_BASE / "mock"
ARCHIVE_DIR_REAL = ARCHIVE_DIR_BASE / "real"

# Default configuration
MOCK_MODE = False
ERA5_COMMON = {
    "times": ["00:00", "06:00", "12:00", "18:00"],
    "format": "netcdf",  # 'netcdf' or 'grib'
    "grid": None,  # None = global
}

ERA5_TASKS = [
    {
        "name": "t2m",
        "variable": "2m_temperature",
        "pressure_levels": [],
        "single_level": True,
    },
    {
        "name": "t500",
        "variable": "temperature",
        "pressure_levels": ["500"],
        "single_level": False,
    },
]

DEFAULT_START_DATE = datetime(2026, 1, 19)
DEFAULT_END_DATE = datetime.utcnow() - timedelta(days=4)

# Runtime-selected dirs (initialized below)
DATA_DIR = DATA_DIR_REAL
ARCHIVE_DIR = ARCHIVE_DIR_REAL

# Setup logging
log_dir = BASE_DIR / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"era5_download_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("era5_download")

# Optional dependencies
try:
    import xarray as xr  # type: ignore

    _HAS_XARRAY = True
except Exception:
    _HAS_XARRAY = False
    logger.warning("xarray not available - file validation will be skipped")

try:
    import cdsapi  # type: ignore

    _HAS_CDSAPI = True
except Exception:
    _HAS_CDSAPI = False


def configure_runtime(mock: bool) -> None:
    """Set runtime flags and ensure directories exist."""
    global MOCK_MODE, DATA_DIR, ARCHIVE_DIR
    MOCK_MODE = mock
    DATA_DIR = DATA_DIR_MOCK if mock else DATA_DIR_REAL
    ARCHIVE_DIR = ARCHIVE_DIR_MOCK if mock else ARCHIVE_DIR_REAL

    for d in [DATA_DIR, DATA_DIR_MOCK, DATA_DIR_REAL, ARCHIVE_DIR, ARCHIVE_DIR_MOCK, ARCHIVE_DIR_REAL]:
        d.mkdir(parents=True, exist_ok=True)


def _is_valid_era5_file(file_path: Path) -> bool:
    """Validate ERA5 file by opening and checking structure."""
    if not _HAS_XARRAY:
        logger.warning(f"Cannot validate {file_path.name}: xarray not available")
        return True

    try:
        with xr.open_dataset(file_path) as ds:
            if len(ds.data_vars) == 0:
                logger.warning(f"File has no data variables: {file_path.name}")
                return False

            has_coords = False
            for var in ds.data_vars:
                var_coords = ds[var].coords
                if ("latitude" in var_coords and "longitude" in var_coords) or (
                    "lat" in var_coords and "lon" in var_coords
                ):
                    has_coords = True
                    break

            if not has_coords:
                logger.warning(f"File missing lat/lon coordinates: {file_path.name}")
                return False

            return True

    except Exception as e:
        logger.warning(f"File validation failed for {file_path.name}: {e}")
        return False


def _build_level_tag(task: dict) -> str:
    levels = task.get("pressure_levels", [])
    if not levels:
        return "pl"
    return f"pl{'-'.join(str(l) for l in levels)}hPa"


def _build_output_filename(task: dict, date: datetime, output_format: str) -> str:
    date_str = date.strftime("%Y%m%d")
    ext = "nc" if output_format == "netcdf" else "grib"
    variable = task["variable"]
    if task.get("single_level", False):
        return f"era5_{variable}_{date_str}.{ext}"
    level_tag = _build_level_tag(task)
    return f"era5_{variable}_{level_tag}_{date_str}.{ext}"


def _task_date_for(task: dict, date: datetime) -> datetime:
    if task.get("static"):
        static_date = task.get("static_date")
        if static_date:
            return datetime.strptime(static_date, "%Y-%m-%d")
    return date


def download_era5_daily(
    date: datetime,
    task: dict,
    output_dir: Path | None = None,
    mock: bool | None = None,
) -> Optional[Path]:
    """Download a single day of ERA5 data or create a mock file."""
    if output_dir is None:
        output_dir = DATA_DIR
    if mock is None:
        mock = MOCK_MODE

    variable = task["variable"]
    pressure_levels = task.get("pressure_levels", [])
    times = ERA5_COMMON["times"]
    output_format = ERA5_COMMON["format"]
    grid = ERA5_COMMON["grid"]

    task_date = _task_date_for(task, date)
    output_path = output_dir / _build_output_filename(task, task_date, output_format)

    if output_path.exists():
        if _is_valid_era5_file(output_path):
            logger.info(f"File already exists and is valid: {output_path}")
            return output_path
        logger.warning(f"Existing file is invalid or incomplete, will re-download: {output_path}")
        output_path.unlink()

    output_dir.mkdir(parents=True, exist_ok=True)

    if mock:
        output_path.touch()
        logger.info(f"[MOCK] Created mock file: {output_path}")
        return output_path

    if not _HAS_CDSAPI:
        logger.error("cdsapi is not installed. Install with: pip install cdsapi")
        return None

    client = cdsapi.Client()

    product_name = "reanalysis-era5-single-levels" if task.get("single_level", False) else "reanalysis-era5-pressure-levels"

    request = {
        "product_type": "reanalysis",
        "format": output_format,
        "variable": variable,
        "date": task_date.strftime("%Y-%m-%d"),
        "time": times,
    }
    if not task.get("single_level", False):
        request["pressure_level"] = pressure_levels
    if grid is not None:
        request["grid"] = grid

    try:
        logger.info(f"Downloading {task_date.strftime('%Y-%m-%d')}: {variable} product={product_name}")
        client.retrieve(product_name, request, str(output_path))

        if not _is_valid_era5_file(output_path):
            logger.error(f"Downloaded file failed validation: {output_path}")
            output_path.unlink()
            return None

        logger.info(f"Downloaded to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Download failed: {e}")
        if output_path.exists():
            output_path.unlink()
        return None


def archive_file(downloaded_file: Path, mock: bool | None = None) -> Optional[Path]:
    """Move downloaded file to archive directory organized by YYYY/MM/."""
    if mock is None:
        mock = MOCK_MODE

    archive_dir = ARCHIVE_DIR_MOCK if mock else ARCHIVE_DIR_REAL

    if not downloaded_file.exists():
        logger.error(f"Downloaded file not found: {downloaded_file}")
        return None

    try:
        import re

        filename = downloaded_file.name
        date_match = re.search(r"(\d{8})", filename)
        if not date_match:
            logger.error(f"Could not extract date from filename: {filename}")
            return None

        date_str = date_match.group(1)
        yyyy = date_str[:4]
        mm = date_str[4:6]

        archive_subdir = archive_dir / yyyy / mm
        archive_subdir.mkdir(parents=True, exist_ok=True)

        archived_path = archive_subdir / filename
        shutil.move(str(downloaded_file), str(archived_path))

        logger.info(f"Archived to: {archived_path}")
        return archived_path

    except Exception as e:
        logger.error(f"Failed to archive {downloaded_file}: {e}")
        return None


def check_day_completeness(date: datetime, task: dict, archive_dir: Path | None = None) -> dict:
    """Check if a day's file exists in the archive."""
    if archive_dir is None:
        archive_dir = ARCHIVE_DIR_REAL

    task_date = _task_date_for(task, date)
    yyyy = task_date.strftime("%Y")
    mm = task_date.strftime("%m")

    archive_date_folder = archive_dir / yyyy / mm
    ext = "nc" if ERA5_COMMON["format"] == "netcdf" else "grib"

    if not archive_date_folder.exists():
        return {"complete": False, "archive_path": archive_date_folder}

    archived_file = archive_date_folder / _build_output_filename(task, task_date, ERA5_COMMON["format"])

    return {"complete": archived_file.exists(), "archive_path": archive_date_folder}


def should_skip_date(date: datetime, task: dict, mock: bool | None = None) -> bool:
    """Determine if a date should be skipped (already archived)."""
    if mock is None:
        mock = MOCK_MODE

    archive_dir = ARCHIVE_DIR_MOCK if mock else ARCHIVE_DIR_REAL
    completeness = check_day_completeness(date, task, archive_dir)

    task_date = _task_date_for(task, date)
    if completeness["complete"]:
        logger.info(f"Skipping {task_date.strftime('%Y-%m-%d')}: already in archive ({task['variable']})")
        return True

    logger.info(f"Downloading {task_date.strftime('%Y-%m-%d')}: not yet in archive ({task['variable']})")
    return False


def process_single_date(
    date: datetime,
    task: dict,
    mock: bool | None = None,
    skip_if_complete: bool = True,
) -> tuple[bool, str, Optional[Path]]:
    """Download and archive a single date for one task."""
    if mock is None:
        mock = MOCK_MODE

    if skip_if_complete and should_skip_date(date, task, mock=mock):
        return True, "skipped", None

    downloaded = download_era5_daily(date=date, task=task, mock=mock)
    if downloaded is None:
        return False, "failed", None

    archived = archive_file(downloaded, mock=mock)
    if archived is None:
        return False, "failed", None
    return True, "downloaded", archived


def process_date_range(
    start_date: datetime,
    end_date: datetime,
    tasks: list[dict],
    mock: bool | None = None,
    skip_if_complete: bool = True,
):
    """Download a range of dates with optional intelligent skipping."""
    if mock is None:
        mock = MOCK_MODE

    current = start_date
    results = {"downloaded": 0, "skipped": 0, "failed": 0}
    manifest_rows: list[dict] = []
    static_done: set[str] = set()

    while current <= end_date:
        for task in tasks:
            if task.get("static"):
                task_key = task.get("name") or task.get("variable", "static")
                if task_key in static_done:
                    continue
            if skip_if_complete and should_skip_date(current, task, mock=mock):
                results["skipped"] += 1
                status = "skipped"
                archived_path = None
            else:
                ok, status, archived_path = process_single_date(current, task, mock=mock, skip_if_complete=False)
                if ok and status == "downloaded":
                    results["downloaded"] += 1
                elif status == "skipped":
                    results["skipped"] += 1
                else:
                    results["failed"] += 1

            manifest_rows.append(
                {
                    "date": _task_date_for(task, current).strftime("%Y-%m-%d"),
                    "variable": task["variable"],
                    "single_level": task.get("single_level", False),
                    "pressure_levels": ",".join(str(p) for p in task.get("pressure_levels", [])),
                    "format": ERA5_COMMON["format"],
                    "status": status,
                    "file": archived_path.name if archived_path else _build_output_filename(task, _task_date_for(task, current), ERA5_COMMON["format"]),
                    "archive_path": str(archived_path) if archived_path else "",
                }
            )
            if task.get("static"):
                static_done.add(task_key)

        current += timedelta(days=1)

    _write_manifest(manifest_rows, DATA_DIR)
    return results


def find_oldest_missing_file(
    start_date: datetime = DEFAULT_START_DATE,
    end_date: datetime = DEFAULT_END_DATE,
    mock: bool | None = None,
    tasks: list[dict] | None = None,
) -> Optional[datetime]:
    """Return the first missing date in a range, or None if complete."""
    if mock is None:
        mock = MOCK_MODE

    if tasks is None:
        tasks = ERA5_TASKS

    current = start_date
    archive_dir = ARCHIVE_DIR_MOCK if mock else ARCHIVE_DIR_REAL

    while current <= end_date:
        for task in tasks:
            completeness = check_day_completeness(current, task, archive_dir)
            if not completeness["complete"]:
                logger.info(f"Found missing date: {current.strftime('%Y-%m-%d')} ({task['variable']})")
                return current
        current += timedelta(days=1)

    logger.info("No missing files found")
    return None


def run_era5_pipeline(
    single_date: datetime | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    mock: bool | None = None,
    skip_if_complete: bool = True,
    tasks: list[dict] | None = None,
) -> dict:
    """Main pipeline: download and archive ERA5 data."""
    if single_date is not None:
        start_date = single_date
        end_date = single_date

    if start_date is None:
        start_date = DEFAULT_START_DATE
    if end_date is None:
        end_date = DEFAULT_END_DATE
    if mock is None:
        mock = MOCK_MODE
    if tasks is None:
        tasks = ERA5_TASKS

    logger.info("\n" + "=" * 70)
    logger.info("ERA5 DOWNLOAD PIPELINE")
    logger.info("=" * 70)
    logger.info(f"Start date: {start_date.date()}")
    logger.info(f"End date: {end_date.date()}")
    logger.info(f"Mode: {'MOCK' if mock else 'REAL'}")
    logger.info(f"Tasks: {[t['variable'] for t in tasks]}")

    results = process_date_range(start_date, end_date, tasks=tasks, mock=mock, skip_if_complete=skip_if_complete)

    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE RESULTS")
    logger.info("=" * 70)
    logger.info(f"✓ Downloaded: {results['downloaded']} files")
    logger.info(f"⊘ Skipped (already in archive): {results['skipped']} files")
    logger.info(f"✗ Failed: {results['failed']} files")
    logger.info("=" * 70 + "\n")

    return results


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def _parse_times(value: str) -> List[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def _parse_pressure_levels(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _parse_grid(value: str) -> List[float]:
    parts = [p.strip() for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("grid must be 'N,W,S,E'")
    return [float(p) for p in parts]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ERA5 daily download + archive")
    parser.add_argument("--mock", action="store_true", help="Use mock mode (no CDS API)")
    parser.add_argument("--single-date", type=_parse_date, help="Download a single date (YYYY-MM-DD)")
    parser.add_argument("--start-date", type=_parse_date, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=_parse_date, help="End date (YYYY-MM-DD)")
    parser.add_argument("--no-skip", action="store_true", help="Do not skip dates already in archive")

    parser.add_argument("--times", default=",".join(ERA5_COMMON["times"]), help="Comma list of UTC times")
    parser.add_argument("--format", choices=["netcdf", "grib"], default=ERA5_COMMON["format"], help="Output format")
    parser.add_argument("--grid", type=_parse_grid, help="Spatial subset N,W,S,E")

    parser.add_argument("--pressure-levels", default="500", help="Comma list of pressure levels for temperature")
    parser.add_argument("--no-2m", action="store_true", help="Disable 2m temperature (single-level) task")
    parser.add_argument("--pressure-variable", default="temperature", help="Pressure-level variable name")
    parser.add_argument("--single-variable", default="2m_temperature", help="Single-level variable name")
    parser.add_argument("--include-lsm", action="store_true", help="Include land-sea mask (static)")
    parser.add_argument("--lsm-date", default="1979-01-01", help="Date used to store LSM (YYYY-MM-DD)")

    return parser


def _apply_cli_config(args: argparse.Namespace) -> None:
    ERA5_COMMON["times"] = _parse_times(args.times)
    ERA5_COMMON["format"] = args.format
    ERA5_COMMON["grid"] = args.grid

    tasks = []
    if not args.no_2m:
        tasks.append(
            {
                "name": "t2m",
                "variable": args.single_variable,
                "pressure_levels": [],
                "single_level": True,
            }
        )

    pressure_levels = _parse_pressure_levels(args.pressure_levels)
    if not pressure_levels:
        raise ValueError("pressure-level task requires --pressure-levels")
    tasks.append(
        {
            "name": "tpl",
            "variable": args.pressure_variable,
            "pressure_levels": pressure_levels,
            "single_level": False,
        }
    )
    if args.include_lsm:
        tasks.append(
            {
                "name": "lsm",
                "variable": "land_sea_mask",
                "pressure_levels": [],
                "single_level": True,
                "static": True,
                "static_date": args.lsm_date,
            }
        )

    global ERA5_TASKS
    ERA5_TASKS = tasks


def _write_manifest(rows: list[dict], output_dir: Path) -> None:
    if not rows:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    fieldnames = ["date", "variable", "single_level", "pressure_levels", "format", "status", "file", "archive_path"]
    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Manifest written: {manifest_path}")


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    configure_runtime(args.mock)
    try:
        _apply_cli_config(args)
    except Exception as e:
        logger.error(f"Invalid configuration: {e}")
        return 2

    if args.start_date and args.end_date and args.end_date < args.start_date:
        logger.error("end_date must be >= start_date")
        return 2

    results = run_era5_pipeline(
        single_date=args.single_date,
        start_date=args.start_date,
        end_date=args.end_date,
        mock=args.mock,
        skip_if_complete=not args.no_skip,
    )
    return 0 if results.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
