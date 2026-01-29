#!/usr/bin/env python3
"""
Download static ERA5 fields (orography + land-sea mask) once and cache locally.

Targets:
  - data/static/era5_orography.nc
  - data/static/era5_land_sea_mask.nc
Behavior: skip download if file already exists.
"""

from __future__ import annotations

import argparse
from pathlib import Path


DEFAULT_DATE = "2000-01-01"
DEFAULT_TIME = "00:00"
DEFAULT_AREA = "58,-5,43,25"  # N,W,S,E (Europe extent)


def _parse_area(area_str: str) -> list[float]:
    parts = [p.strip() for p in area_str.split(",")]
    if len(parts) != 4:
        raise ValueError("area must be 'N,W,S,E'")
    return [float(p) for p in parts]


def _get_static_dir() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "data" / "static"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _get_orog_path() -> Path:
    return _get_static_dir() / "era5_orography.nc"


def _get_lsm_path() -> Path:
    return _get_static_dir() / "era5_land_sea_mask.nc"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ERA5 static fields (orography + land-sea mask).")
    parser.add_argument("--date", default=DEFAULT_DATE, help="Date (YYYY-MM-DD)")
    parser.add_argument("--time", default=DEFAULT_TIME, help="Time (HH:MM)")
    parser.add_argument("--area", default=DEFAULT_AREA, help="Area N,W,S,E (default: Europe)")
    parser.add_argument("--skip-orog", action="store_true", help="Skip orography download")
    parser.add_argument("--skip-lsm", action="store_true", help="Skip land-sea mask download")
    args = parser.parse_args()

    try:
        import cdsapi  # type: ignore
    except Exception:
        print("cdsapi is not installed. Install with: pip install cdsapi")
        return 2

    client = cdsapi.Client()
    area = _parse_area(args.area)
    date = args.date
    time = args.time

    if not args.skip_orog:
        orog_path = _get_orog_path()
        if orog_path.exists():
            print(f"Orography already present, skipping download: {orog_path}")
        else:
            request_orog = {
                "product_type": "reanalysis",
                "format": "netcdf",
                "variable": "geopotential",
                "date": date,
                "time": time,
                "area": area,
            }
            print(f"Downloading ERA5 geopotential to: {orog_path}")
            client.retrieve("reanalysis-era5-single-levels", request_orog, str(orog_path))
            print("Orography download complete.")

    if not args.skip_lsm:
        lsm_path = _get_lsm_path()
        if lsm_path.exists():
            print(f"Land-sea mask already present, skipping download: {lsm_path}")
        else:
            request_lsm = {
                "product_type": "reanalysis",
                "format": "netcdf",
                "variable": "land_sea_mask",
                "date": date,
                "time": time,
                "area": area,
            }
            print(f"Downloading ERA5 land-sea mask to: {lsm_path}")
            client.retrieve("reanalysis-era5-single-levels", request_lsm, str(lsm_path))
            print("Land-sea mask download complete.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
