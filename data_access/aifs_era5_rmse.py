"""
Reproducible RMSE pipeline helpers for AIFS vs ERA5 at valid time.

Core tasks:
1) Index AIFS GRIB files (init_dt, step_hours, valid_dt, path, levtype, params)
2) Index ERA5 daily NetCDF files (date, path)
3) Pair AIFS forecasts with ERA5 files at matching valid time

Note: AIFS longitude may be wrapped (e.g., starts at 180 then wraps to 0),
so grid alignment may require a longitude roll before point-wise RMSE.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

try:
    import xarray as xr  # type: ignore

    _HAS_XARRAY = True
except Exception:
    _HAS_XARRAY = False


_AIFS_RE = re.compile(
    r"^(?P<model>[^_]+)_(?P<date>\d{8})_(?P<hour>\d{2})_(?P<levtype>[^_]+)_(?P<params>.+?)_"
    r"(?:(?P<level>\d+)hPa_)?step(?P<step>\d{3})_0p25\.grib2$"
)


def _parse_aifs_filename(path: Path) -> Optional[dict]:
    match = _AIFS_RE.match(path.name)
    if not match:
        return None

    date_str = match.group("date")
    hour_str = match.group("hour")
    step_str = match.group("step")

    init_dt = datetime.strptime(date_str + hour_str, "%Y%m%d%H")
    step_hours = int(step_str)
    valid_dt = init_dt + timedelta(hours=step_hours)

    return {
        "init_dt": init_dt,
        "step_hours": step_hours,
        "valid_dt": valid_dt,
        "path": str(path),
        "levtype": match.group("levtype"),
        "params": match.group("params"),
        "level": match.group("level"),
        "model": match.group("model"),
    }


def index_aifs_files(aifs_root: Path) -> pd.DataFrame:
    """Scan AIFS directory and parse filenames into a table."""
    rows = []
    for path in aifs_root.rglob("*.grib2"):
        parsed = _parse_aifs_filename(path)
        if parsed:
            rows.append(parsed)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["init_dt", "step_hours", "path"]).reset_index(drop=True)
    return df


def index_era5_archive(era5_archive_root: Path, variable: str = "2m_temperature") -> pd.DataFrame:
    """Scan ERA5 archive and map each day to a file path."""
    rows = []
    for path in era5_archive_root.rglob("*.nc"):
        if variable not in path.name:
            continue
        date_match = re.search(r"(\d{8})", path.name)
        if not date_match:
            continue
        date = datetime.strptime(date_match.group(1), "%Y%m%d").date()
        rows.append({"date": date, "path": str(path)})

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "path"]).reset_index(drop=True)
    return df


def _era5_has_time(era5_path: Path, hour: int) -> bool:
    if not _HAS_XARRAY:
        return True

    try:
        with xr.open_dataset(era5_path) as ds:
            if "time" not in ds:
                return False
            hours = pd.to_datetime(ds["time"].values).hour
            return int(hour) in set(int(h) for h in hours)
    except Exception:
        return False


def pair_aifs_with_era5(aifs_index_df: pd.DataFrame, era5_index_df: pd.DataFrame, verify_era5_times: bool = True) -> pd.DataFrame:
    """Pair AIFS forecasts with ERA5 valid times."""
    era5_map = {row["date"]: row["path"] for _, row in era5_index_df.iterrows()}

    rows = []
    for _, row in aifs_index_df.iterrows():
        init_dt = row["init_dt"]
        step_hours = row["step_hours"]
        valid_dt = row["valid_dt"]
        aifs_path = Path(row["path"])

        if not aifs_path.exists():
            rows.append(
                {
                    "init_dt": init_dt,
                    "step": step_hours,
                    "valid_dt": valid_dt,
                    "aifs_path": str(aifs_path),
                    "era5_path": "",
                    "status": "missing_aifs",
                }
            )
            continue

        era5_path = era5_map.get(valid_dt.date())
        if not era5_path:
            rows.append(
                {
                    "init_dt": init_dt,
                    "step": step_hours,
                    "valid_dt": valid_dt,
                    "aifs_path": str(aifs_path),
                    "era5_path": "",
                    "status": "missing_era5",
                }
            )
            continue

        status = "ok"
        if verify_era5_times:
            if not _era5_has_time(Path(era5_path), valid_dt.hour):
                status = "time_not_found"

        rows.append(
            {
                "init_dt": init_dt,
                "step": step_hours,
                "valid_dt": valid_dt,
                "aifs_path": str(aifs_path),
                "era5_path": str(era5_path),
                "status": status,
            }
        )

    return pd.DataFrame(rows)


def _get_lat_lon_names(ds: "xr.Dataset") -> tuple[str, str]:
    for lat_name, lon_name in [("latitude", "longitude"), ("lat", "lon")]:
        if lat_name in ds.coords and lon_name in ds.coords:
            return lat_name, lon_name
    raise RuntimeError("Could not find latitude/longitude coordinates in dataset")

# normalize_lon is a general safety helper as we already know how lon of ERA5 and AIFS look like
def _normalize_lon(lon: np.ndarray, mode: str = "to_360") -> np.ndarray:
    if mode == "none":
        return lon
    if mode == "to_360":
        return np.mod(lon, 360.0)
    if mode == "to_180":
        return (np.mod(lon + 180.0, 360.0) - 180.0)
    raise ValueError(f"Unknown longitude normalization mode: {mode}")

#It looks for a single large negative jump in a 1-D longitude array 
# and returns the index where longitude wraps back to the start.
def _find_wrap_index(lon: np.ndarray) -> int | None:
    if lon.ndim != 1 or lon.size < 2:
        return None
    diffs = np.diff(lon)
    jump_idx = np.where(diffs < -100)[0]
    if jump_idx.size == 1:
        return int(jump_idx[0] + 1)
    return None


def align_aifs_lon_to_era5(aifs_ds: "xr.Dataset", era5_ds: "xr.Dataset") -> "xr.Dataset":
    """
    Align AIFS longitude ordering to ERA5 without interpolation.
    This handles the common wrap case where AIFS starts at 180 and wraps to 0.
    """
    lat_a, lon_a = _get_lat_lon_names(aifs_ds)
    lat_e, lon_e = _get_lat_lon_names(era5_ds)

    lon_a_vals = _normalize_lon(aifs_ds[lon_a].values, mode="to_360")
    lon_e_vals = _normalize_lon(era5_ds[lon_e].values, mode="to_360")

    # If already aligned, return unchanged
    if lon_a_vals.shape == lon_e_vals.shape and np.allclose(lon_a_vals, lon_e_vals, atol=1e-6, rtol=0.0):
        return aifs_ds

    # Detect wrap and roll to make AIFS longitude monotonic
    wrap_idx = _find_wrap_index(lon_a_vals)
    if wrap_idx is None:
        return aifs_ds

    aligned = aifs_ds.roll({lon_a: -wrap_idx}, roll_coords=True)
    return aligned
