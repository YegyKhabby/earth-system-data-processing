#!/usr/bin/env python3
"""
Temp helper to print metadata + header-style info for ERA5 NetCDF and AIFS GRIB2 files.

Usage:
  python temp_era5_aifs_metadata.py /path/to/file1.nc /path/to/file2.grib2
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

try:
    import xarray as xr  # type: ignore

    _HAS_XARRAY = True
except Exception:
    _HAS_XARRAY = False

try:
    import cfgrib  # type: ignore

    _HAS_CFGRIB = True
except Exception:
    _HAS_CFGRIB = False


def _print_ds_header(ds, label: str, max_vars: int) -> None:
    print(f"\n== {label} ==")
    # Use sizes to avoid future deprecation of Dataset.dims
    print("dims:", dict(ds.sizes))
    print("coords:", list(ds.coords))
    print("data_vars:", list(ds.data_vars)[:max_vars])
    if len(ds.data_vars) > max_vars:
        print(f"... (+{len(ds.data_vars) - max_vars} more vars)")
    if ds.attrs:
        print("global attrs:")
        for k in sorted(ds.attrs):
            print(f"  {k}: {ds.attrs.get(k)}")


def _print_netcdf(path: Path, max_vars: int) -> None:
    if not _HAS_XARRAY:
        print("xarray not available; cannot read NetCDF.")
        return
    # Prefer explicit engine to avoid xarray auto-detect failures.
    preferred = ["netcdf4", "h5netcdf", "scipy"]
    try:
        available = set(xr.backends.list_engines())
    except Exception:
        available = set()

    engines = [e for e in preferred if e in available] or preferred
    last_err: Exception | None = None
    for engine in engines:
        try:
            with xr.open_dataset(path, engine=engine) as ds:
                _print_ds_header(ds, f"ERA5 NetCDF: {path.name}", max_vars)
            return
        except Exception as exc:
            last_err = exc
            continue
    print(f"Failed to open NetCDF with engines {engines}: {path}")
    if last_err:
        print(f"Last error: {last_err}")


def _print_grib2(path: Path, max_vars: int) -> None:
    if not _HAS_XARRAY and not _HAS_CFGRIB:
        print("xarray/cfgrib not available; cannot read GRIB2.")
        return

    if _HAS_CFGRIB:
        # Disable on-disk index creation to avoid permission issues.
        datasets = cfgrib.open_datasets(str(path), backend_kwargs={"indexpath": ""})
        for idx, ds in enumerate(datasets, start=1):
            _print_ds_header(ds, f"AIFS GRIB2: {path.name} (message set {idx})", max_vars)
        return

    # Fallback: try xarray with cfgrib engine if available in the env
    with xr.open_dataset(path, engine="cfgrib") as ds:
        _print_ds_header(ds, f"AIFS GRIB2: {path.name}", max_vars)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print metadata/header info for ERA5 and AIFS files.")
    parser.add_argument("paths", nargs="*", help="Paths to ERA5 .nc and/or AIFS .grib2 files")
    parser.add_argument("--max-vars", type=int, default=20, help="Max number of variables to list")
    parser.add_argument("--max-files", type=int, default=10, help="Max number of files to scan per type")
    parser.add_argument("--all", action="store_true", help="Process all discovered files")
    parser.add_argument("--include-mock", action="store_true", help="Include mock ERA5 files")
    args = parser.parse_args()

    paths: list[Path]
    if args.paths:
        paths = [Path(raw).expanduser() for raw in args.paths]
    else:
        # Default locations relative to this script
        script_path = Path(__file__).resolve()
        projects_root = script_path.parents[4]  # /Users/.../Projects
        aifs_root = projects_root / "data" / "aifs"
        era5_root = script_path.parents[2] / "data" / "era5"

        discovered: list[Path] = []
        aifs_all: list[Path] = []
        era5_all: list[Path] = []
        if aifs_root.exists():
            aifs_all.extend(aifs_root.rglob("*.grib2"))
            aifs_all.extend(aifs_root.rglob("*.grb2"))
            aifs_all.extend(aifs_root.rglob("*.grb"))
        if era5_root.exists():
            era5_all = list(era5_root.rglob("*.nc")) + list(era5_root.rglob("*.nc4"))
            if not args.include_mock:
                era5_all = [p for p in era5_all if "mock" not in p.parts]
            # Prefer real data paths if present
            era5_all = sorted(
                era5_all,
                key=lambda p: (0 if "real" in p.parts else 1, str(p)),
            )
        aifs_all = sorted(p for p in aifs_all if p.is_file())
        era5_all = [p for p in era5_all if p.is_file()]

        if args.all:
            discovered = aifs_all + era5_all
        else:
            discovered = aifs_all[: args.max_files] + era5_all[: args.max_files]
        paths = discovered

    if not paths:
        print("No files found. Pass explicit paths or check data directories.")
        return

    for path in paths:
        if not path.exists():
            print(f"Missing: {path}")
            continue

        if path.suffix in {".nc", ".nc4"}:
            _print_netcdf(path, args.max_vars)
        elif path.suffix in {".grib2", ".grb2", ".grb"} or path.name.endswith(".grib2"):
            _print_grib2(path, args.max_vars)
        else:
            print(f"Unknown file type: {path}")


if __name__ == "__main__":
    main()
