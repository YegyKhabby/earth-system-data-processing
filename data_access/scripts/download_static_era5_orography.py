#!/usr/bin/env python3
"""
Download static ERA5 orography (geopotential, z) once and cache locally.

Target: data/static/era5_orography.nc
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


def _get_output_path() -> Path:
    base_dir = Path(__file__).resolve().parent.parent
    out_dir = base_dir / "data" / "static"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "era5_orography.nc"


def main() -> int:
    parser = argparse.ArgumentParser(description="Download ERA5 geopotential (static orography).")
    parser.add_argument("--date", default=DEFAULT_DATE, help="Date (YYYY-MM-DD)")
    parser.add_argument("--time", default=DEFAULT_TIME, help="Time (HH:MM)")
    parser.add_argument("--area", default=DEFAULT_AREA, help="Area N,W,S,E (default: Europe)")
    args = parser.parse_args()

    out_path = _get_output_path()
    if out_path.exists():
        print(f"Orography already present, skipping download: {out_path}")
        return 0

    try:
        import cdsapi  # type: ignore
    except Exception:
        print("cdsapi is not installed. Install with: pip install cdsapi")
        return 2

    client = cdsapi.Client()
    request = {
        "product_type": "reanalysis",
        "format": "netcdf",
        "variable": "geopotential",
        "date": args.date,
        "time": args.time,
        "area": _parse_area(args.area),
    }

    print(f"Downloading ERA5 geopotential to: {out_path}")
    client.retrieve("reanalysis-era5-single-levels", request, str(out_path))
    print("Download complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
