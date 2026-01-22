"""
Quick grid comparison between AIFS (GRIB2) and ERA5 (NetCDF).

Checks:
1) Shape comparison
2) Coordinate comparison (lat/lon arrays)
3) Regular vs irregular grid
4) Optional longitude normalization (0..360 or -180..180)
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import numpy as np
import tempfile
import sys

try:
    import xarray as xr  # type: ignore

    _HAS_XARRAY = True
except Exception:
    _HAS_XARRAY = False


def _open_aifs_grib(path: Path, param: str | None = None) -> "xr.Dataset":
    if not _HAS_XARRAY:
        raise RuntimeError("xarray is required")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = str(Path(tmpdir) / f"{path.name}.idx")
            backend_kwargs = {"indexpath": index_path}
            if param:
                backend_kwargs["filter_by_keys"] = {"shortName": param}
            return xr.open_dataset(path, engine="cfgrib", backend_kwargs=backend_kwargs)
    except Exception as e:
        raise RuntimeError(f"Failed to open AIFS GRIB2 with cfgrib: {e}") from e


def _open_era5_netcdf(path: Path) -> "xr.Dataset":
    if not _HAS_XARRAY:
        raise RuntimeError("xarray is required")
    return xr.open_dataset(path)


def _extract_lat_lon(ds: "xr.Dataset") -> Tuple[np.ndarray, np.ndarray]:
    for lat_name, lon_name in [("latitude", "longitude"), ("lat", "lon")]:
        if lat_name in ds.coords and lon_name in ds.coords:
            return ds[lat_name].values, ds[lon_name].values
    raise RuntimeError("Could not find latitude/longitude coordinates in dataset")


def _normalize_lon(lon: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return lon
    if mode == "to_360":
        return np.mod(lon, 360.0)
    if mode == "to_180":
        lon = np.mod(lon + 180.0, 360.0) - 180.0
        return lon
    raise ValueError(f"Unknown longitude normalization mode: {mode}")


def _diff_stats(arr: np.ndarray) -> dict:
    if arr.size < 2:
        return {"min": np.nan, "max": np.nan, "mean": np.nan}
    diffs = np.diff(arr)
    return {"min": float(np.min(diffs)), "max": float(np.max(diffs)), "mean": float(np.mean(diffs))}


def _find_wrap_index(lon: np.ndarray) -> int | None:
    if lon.ndim != 1 or lon.size < 2:
        return None
    diffs = np.diff(lon)
    # Identify a single large negative jump as wrap
    jump_idx = np.where(diffs < -100)[0]
    if jump_idx.size == 0:
        return None
    # If multiple jumps, treat as irregular
    if jump_idx.size > 1:
        return None
    return int(jump_idx[0] + 1)


def _is_regular_grid(lat: np.ndarray, lon: np.ndarray, atol: float = 1e-6) -> bool:
    # Regular lat/lon grid if lat/lon are 1D and spacing is constant (with optional wrap)
    if lat.ndim != 1 or lon.ndim != 1:
        return False

    lat_diff = np.diff(lat)
    if lat_diff.size == 0:
        return False
    if not (np.all(lat_diff > 0) or np.all(lat_diff < 0)):
        return False
    if not np.allclose(lat_diff, lat_diff[0], atol=atol, rtol=0.0):
        return False

    wrap_idx = _find_wrap_index(lon)
    if wrap_idx is not None:
        lon = np.concatenate([lon[wrap_idx:], lon[:wrap_idx]])

    lon_diff = np.diff(lon)
    if lon_diff.size == 0:
        return False
    if not (np.all(lon_diff > 0) or np.all(lon_diff < 0)):
        return False
    if not np.allclose(lon_diff, lon_diff[0], atol=atol, rtol=0.0):
        return False

    return True


def compare_grids(
    aifs_path: Path,
    era5_path: Path,
    param: str | None = None,
    lon_normalize: str = "none",
    rtol: float = 1e-6,
    atol: float = 1e-6,
    align_after_roll: bool = False,
) -> dict:
    ds_aifs = _open_aifs_grib(aifs_path, param=param)
    ds_era5 = _open_era5_netcdf(era5_path)

    if align_after_roll:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from aifs_era5_rmse import align_aifs_lon_to_era5  # type: ignore

        ds_aifs = align_aifs_lon_to_era5(ds_aifs, ds_era5)

    lat_aifs, lon_aifs = _extract_lat_lon(ds_aifs)
    lat_era5, lon_era5 = _extract_lat_lon(ds_era5)

    lon_aifs = _normalize_lon(lon_aifs, lon_normalize)
    lon_era5 = _normalize_lon(lon_era5, lon_normalize)

    shape_match = (lat_aifs.shape == lat_era5.shape) and (lon_aifs.shape == lon_era5.shape)
    lat_match = np.allclose(lat_aifs, lat_era5, rtol=rtol, atol=atol)
    lon_match = np.allclose(lon_aifs, lon_era5, rtol=rtol, atol=atol)

    aifs_wrap = _find_wrap_index(lon_aifs)
    era5_wrap = _find_wrap_index(lon_era5)

    return {
        "shape_match": shape_match,
        "lat_match": lat_match,
        "lon_match": lon_match,
        "regular_aifs": _is_regular_grid(lat_aifs, lon_aifs, atol=atol),
        "regular_era5": _is_regular_grid(lat_era5, lon_era5, atol=atol),
        "lat_shape_aifs": lat_aifs.shape,
        "lon_shape_aifs": lon_aifs.shape,
        "lat_shape_era5": lat_era5.shape,
        "lon_shape_era5": lon_era5.shape,
        "lat_stats_aifs": _diff_stats(lat_aifs),
        "lon_stats_aifs": _diff_stats(lon_aifs),
        "lat_stats_era5": _diff_stats(lat_era5),
        "lon_stats_era5": _diff_stats(lon_era5),
        "aifs_wrap_index": aifs_wrap,
        "era5_wrap_index": era5_wrap,
        "lat_head_aifs": lat_aifs[:5].tolist(),
        "lat_tail_aifs": lat_aifs[-5:].tolist(),
        "lon_head_aifs": lon_aifs[:5].tolist(),
        "lon_tail_aifs": lon_aifs[-5:].tolist(),
        "lat_head_era5": lat_era5[:5].tolist(),
        "lat_tail_era5": lat_era5[-5:].tolist(),
        "lon_head_era5": lon_era5[:5].tolist(),
        "lon_tail_era5": lon_era5[-5:].tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether AIFS and ERA5 grids match")
    parser.add_argument("--aifs", required=True, type=Path, help="Path to AIFS GRIB2 file")
    parser.add_argument("--era5", required=True, type=Path, help="Path to ERA5 NetCDF file")
    parser.add_argument("--param", help="AIFS shortName to select (e.g., 2t, t)")
    parser.add_argument(
        "--lon-normalize",
        default="none",
        choices=["none", "to_360", "to_180"],
        help="Normalize longitude ranges before comparison",
    )
    parser.add_argument("--rtol", type=float, default=1e-6, help="Relative tolerance for coord comparison")
    parser.add_argument("--atol", type=float, default=1e-6, help="Absolute tolerance for coord comparison")
    parser.add_argument("--print-coords", action="store_true", help="Print coordinate details")
    parser.add_argument("--after-roll", action="store_true", help="Align AIFS longitude ordering before comparison")

    args = parser.parse_args()

    result = compare_grids(
        aifs_path=args.aifs,
        era5_path=args.era5,
        param=args.param,
        lon_normalize=args.lon_normalize,
        rtol=args.rtol,
        atol=args.atol,
        align_after_roll=args.after_roll,
    )

    print("Grid comparison:")
    print(f"- Shapes match: {result['shape_match']}")
    print(f"- Latitude match: {result['lat_match']}")
    print(f"- Longitude match: {result['lon_match']}")
    print(f"- AIFS regular grid: {result['regular_aifs']}")
    print(f"- ERA5 regular grid: {result['regular_era5']}")
    print(f"- AIFS lat shape: {result['lat_shape_aifs']}, lon shape: {result['lon_shape_aifs']}")
    print(f"- ERA5 lat shape: {result['lat_shape_era5']}, lon shape: {result['lon_shape_era5']}")
    if args.print_coords:
        print("")
        print("Coordinate details:")
        print(f"- AIFS lat head: {result['lat_head_aifs']}")
        print(f"- AIFS lat tail: {result['lat_tail_aifs']}")
        print(f"- AIFS lon head: {result['lon_head_aifs']}")
        print(f"- AIFS lon tail: {result['lon_tail_aifs']}")
        print(f"- ERA5 lat head: {result['lat_head_era5']}")
        print(f"- ERA5 lat tail: {result['lat_tail_era5']}")
        print(f"- ERA5 lon head: {result['lon_head_era5']}")
        print(f"- ERA5 lon tail: {result['lon_tail_era5']}")
        print(f"- AIFS lat diff stats: {result['lat_stats_aifs']}")
        print(f"- AIFS lon diff stats: {result['lon_stats_aifs']}")
        print(f"- ERA5 lat diff stats: {result['lat_stats_era5']}")
        print(f"- ERA5 lon diff stats: {result['lon_stats_era5']}")
        print(f"- AIFS wrap index: {result['aifs_wrap_index']}")
        print(f"- ERA5 wrap index: {result['era5_wrap_index']}")

    if result["shape_match"] and result["lat_match"] and result["lon_match"]:
        print("Result: grids match (no regrid needed)")
        return 0

    print("Result: grids differ (regrid needed)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
