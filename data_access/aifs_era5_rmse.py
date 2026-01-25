"""
Reproducible RMSE pipeline helpers for AIFS vs ERA5 at valid time.

Core tasks:
1) Index AIFS GRIB files (init_dt, step_hours, valid_dt, path, levtype, params)
2) Index ERA5 daily NetCDF files (date, path, product_tag)
3) Pair AIFS forecasts with ERA5 files at matching valid time, per variable

Recommended flow:
- Build a single ERA5 index with product_tag via index_era5_archive(variable=None)
- Split ERA5 by product_tag (e.g., "t2m", "t_pl500")
- Split AIFS by levtype ("sfc" vs "pl")
- Pair per variable using pair_aifs_with_era5_for_variable

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

try:
    import rasterio  # type: ignore
    from rasterio.transform import rowcol  # type: ignore

    _HAS_RASTERIO = True
except Exception:
    _HAS_RASTERIO = False


_AIFS_RE = re.compile(
    r"^(?P<model>[^_]+)_(?P<date>\d{8})_(?P<hour>\d{2})_(?P<levtype>[^_]+)_(?P<params>.+?)_"
    r"(?:(?P<level>\d+)hPa_)?step(?P<step>\d{3})_0p25\.grib2$"
)

VARIABLE_CONFIG = {
    "2t": {
        "aifs": {
            "shortName": "2t",
            "filter_by_keys": {"shortName": "2t", "typeOfLevel": "heightAboveGround", "level": 2},
        },
        "era5": {"var": "t2m", "level": None},
    },
    "t500": {
        "aifs": {
            "shortName": "t",
            "filter_by_keys": {"shortName": "t", "typeOfLevel": "isobaricInhPa", "level": 500},
        },
        "era5": {"var": "t", "level": 500},
    },
}

# European crop (N, W, S, E) on native ERA5 grid
EUROPE_BBOX = (56.0, 0.0, 44.0, 20.0)


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


def _infer_era5_product_tag(path: Path) -> str:
    """Infer a product tag from filename (e.g., 't2m' or 't_pl500')."""
    name = path.name
    # Common patterns from era5_download_only.py output
    if "2m_temperature" in name:
        return "t2m"
    if "temperature" in name and "pl" in name:
        m = re.search(r"pl(\d+)hPa", name)
        if m:
            return f"t_pl{m.group(1)}"
        return "t_pl"
    return "unknown"


def index_era5_archive(era5_archive_root: Path, variable: str | None = None) -> pd.DataFrame:
    """
    Scan ERA5 archive and map each day to a file path.

    If variable is None, index all files and add a product_tag column.
    If variable is provided, filter by substring match (backward compatible).
    """
    rows = []
    for path in era5_archive_root.rglob("*.nc"):
        if variable is not None and variable not in path.name:
            continue
        date_match = re.search(r"(\d{8})", path.name)
        if not date_match:
            continue
        date = datetime.strptime(date_match.group(1), "%Y%m%d").date()
        rows.append(
            {
                "date": date,
                "path": str(path),
                "product_tag": _infer_era5_product_tag(path),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["date", "path"]).reset_index(drop=True)
    return df


def filter_era5_index_by_product(era5_index_df: pd.DataFrame, product_tag: str) -> pd.DataFrame:
    """Filter an ERA5 index by product_tag."""
    if "product_tag" not in era5_index_df.columns:
        raise RuntimeError("ERA5 index missing product_tag. Rebuild with index_era5_archive(variable=None).")
    return era5_index_df[era5_index_df["product_tag"] == product_tag].reset_index(drop=True)


def filter_aifs_index_by_levtype(aifs_index_df: pd.DataFrame, levtype: str) -> pd.DataFrame:
    """Filter AIFS index by levtype (e.g., 'sfc' or 'pl')."""
    return aifs_index_df[aifs_index_df["levtype"] == levtype].reset_index(drop=True)


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


def pair_aifs_with_era5_for_variable(
    aifs_index_df: pd.DataFrame,
    era5_index_df: pd.DataFrame,
    variable_key: str,
    verify_era5_times: bool = True,
) -> pd.DataFrame:
    """Pair AIFS forecasts with ERA5 and tag rows with variable."""
    if "product_tag" in era5_index_df.columns:
        unique_tags = sorted(set(era5_index_df["product_tag"].dropna().tolist()))
        if len(unique_tags) != 1:
            raise RuntimeError(f"ERA5 index must contain a single product_tag for pairing, got {unique_tags}")
    pairs = pair_aifs_with_era5(aifs_index_df, era5_index_df, verify_era5_times=verify_era5_times)
    pairs["variable"] = variable_key
    return pairs


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


def crop_to_bbox(ds_or_da, bbox: tuple[float, float, float, float]) -> "xr.Dataset | xr.DataArray":
    """Crop to (N, W, S, E) while handling lat order and lon normalization."""
    if not _HAS_XARRAY:
        raise RuntimeError("xarray is required")
    lat_name, lon_name = _get_lat_lon_names(ds_or_da if hasattr(ds_or_da, "coords") else ds_or_da.to_dataset())

    north, west, south, east = bbox
    obj = ds_or_da

    # Normalize longitude to 0..360 for consistent slicing with Europe bbox
    lon_vals = _normalize_lon(obj[lon_name].values, mode="to_360")
    obj = obj.assign_coords({lon_name: lon_vals})
    # Ensure monotonic lon for safe slice selection
    obj = obj.sortby(lon_name)

    lat_vals = obj[lat_name].values
    if lat_vals[0] > lat_vals[-1]:
        lat_slice = slice(north, south)
    else:
        lat_slice = slice(south, north)

    return obj.sel({lat_name: lat_slice, lon_name: slice(west, east)})


def sample_koppen_onehot(lat: float, lon: float, koppen_path: Path) -> np.ndarray:
    """Sample Koppen class for a single lat/lon and return a one-hot vector."""
    if not _HAS_RASTERIO:
        raise RuntimeError("rasterio is required for Koppen sampling")

    koppen_lookup = {
        1: "Af", 2: "Am", 3: "Aw", 4: "BWh", 5: "BWk", 6: "BSh", 7: "BSk",
        8: "Csa", 9: "Csb", 10: "Csc", 11: "Cwa", 12: "Cwb", 13: "Cwc",
        14: "Cfa", 15: "Cfb", 16: "Cfc", 17: "Dsa", 18: "Dsb", 19: "Dsc", 20: "Dsd",
        21: "Dwa", 22: "Dwb", 23: "Dwc", 24: "Dwd", 25: "Dfa", 26: "Dfb",
        27: "Dfc", 28: "Dfd", 29: "ET", 30: "EF",
    }
    all_classes = sorted(set(koppen_lookup.values()) | {"Unknown"})
    class_to_index = {cls: i for i, cls in enumerate(all_classes)}

    with rasterio.open(koppen_path) as src:
        koppen_data = src.read(1)
        transform = src.transform
        try:
            row, col = rowcol(transform, lon, lat)
            code = koppen_data[row, col]
            label = koppen_lookup.get(int(code), "Unknown")
        except Exception:
            label = "Unknown"

    one_hot = np.zeros(len(all_classes), dtype=np.float32)
    if label in class_to_index:
        one_hot[class_to_index[label]] = 1.0
    return one_hot


def load_era5_land_sea_mask(lsm_path: Path) -> "xr.DataArray":
    """Load ERA5 land-sea mask as a DataArray (expects single-level LSM)."""
    if not _HAS_XARRAY:
        raise RuntimeError("xarray is required")
    ds = _open_era5_dataset(lsm_path)
    if "lsm" in ds:
        da = ds["lsm"]
    elif "land_sea_mask" in ds:
        da = ds["land_sea_mask"]
    else:
        raise RuntimeError("LSM variable not found in ERA5 dataset")
    if "time" in da.coords:
        da = da.isel(time=0)
    return da


def apply_land_sea_mask(err: "xr.DataArray", lsm_da: "xr.DataArray", mode: str = "none") -> "xr.DataArray":
    """Apply land/sea mask to an error field."""
    if mode == "none":
        return err
    if mode not in {"land", "sea"}:
        raise ValueError("mask mode must be 'land', 'sea', or 'none'")
    mask = lsm_da >= 0.5
    return err.where(mask if mode == "land" else ~mask)

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


def _open_aifs_dataset(path: Path, aifs_cfg: dict, index_dir: Path) -> "xr.Dataset":
    if not _HAS_XARRAY:
        raise RuntimeError("xarray is required")
    index_dir.mkdir(parents=True, exist_ok=True)
    index_path = index_dir / f"{path.name}.{aifs_cfg['shortName']}.idx"
    return xr.open_dataset(
        path,
        engine="cfgrib",
        backend_kwargs={"indexpath": str(index_path), "filter_by_keys": aifs_cfg.get("filter_by_keys", {})},
    )


def _open_era5_dataset(path: Path) -> "xr.Dataset":
    if not _HAS_XARRAY:
        raise RuntimeError("xarray is required")
    return xr.open_dataset(path)


def _select_aifs_field(ds: "xr.Dataset", aifs_cfg: dict) -> "xr.DataArray":
    short_name = aifs_cfg.get("shortName")
    if short_name in ds.data_vars:
        return ds[short_name]
    if len(ds.data_vars) == 1:
        return next(iter(ds.data_vars.values()))
    raise RuntimeError("AIFS dataset has multiple variables; cannot infer target variable")


def _select_aifs_time(da: "xr.DataArray", valid_dt: datetime, step_hours: int | None = None) -> "xr.DataArray":
    """Select the AIFS time slice if a time-like coordinate exists."""
    if "valid_time" in da.coords:
        return da.sel(valid_time=valid_dt)
    if "time" in da.coords:
        return da.sel(time=valid_dt)
    if "step" in da.coords:
        if step_hours is None:
            return da
        try:
            return da.sel(step=step_hours)
        except Exception:
            return da
    return da


def _select_era5_field(ds: "xr.Dataset", era5_cfg: dict) -> "xr.DataArray":
    var = era5_cfg["var"]
    if var not in ds:
        raise RuntimeError(f"ERA5 variable not found: {var}")
    da = ds[var]
    level = era5_cfg.get("level")
    if level is None:
        return da
    if "level" in da.coords:
        return da.sel(level=level)
    if "pressure_level" in da.coords:
        return da.sel(pressure_level=level)
    raise RuntimeError("ERA5 pressure level coordinate not found")


def _select_time(da: "xr.DataArray", valid_dt: datetime) -> "xr.DataArray":
    if "time" not in da.coords:
        raise RuntimeError("No time coordinate in ERA5 data")
    try:
        return da.sel(time=valid_dt)
    except Exception:
        try:
            return da.sel(time=np.datetime64(valid_dt), method="nearest", tolerance=np.timedelta64(30, "m"))
        except Exception:
            raise RuntimeError("time_not_found")


def compute_pair_rmse(
    aifs_path: Path,
    era5_path: Path,
    valid_dt: datetime,
    variable_key: str,
    index_dir: Path,
    step_hours: int | None = None,
    bbox: Optional[tuple[float, float, float, float]] = None,
    land_sea_mask: "xr.DataArray | None" = None,
    mask_mode: str = "none",
) -> dict:
    cfg = VARIABLE_CONFIG[variable_key]
    try:
        ds_aifs = _open_aifs_dataset(aifs_path, cfg["aifs"], index_dir=index_dir)
        ds_era5 = _open_era5_dataset(era5_path)

        ds_aifs = align_aifs_lon_to_era5(ds_aifs, ds_era5)

        da_aifs = _select_aifs_field(ds_aifs, cfg["aifs"])
        da_aifs = _select_aifs_time(da_aifs, valid_dt=valid_dt, step_hours=step_hours)
        da_era5 = _select_era5_field(ds_era5, cfg["era5"])
        da_era5 = _select_time(da_era5, valid_dt)

        if bbox is not None:
            da_aifs = crop_to_bbox(da_aifs, bbox)
            da_era5 = crop_to_bbox(da_era5, bbox)

        # Convert temperature fields to Celsius for consistent RMSE units
        if variable_key == "2t":
            da_aifs = da_aifs - 273.15
            da_era5 = da_era5 - 273.15
        err = da_aifs - da_era5
        if land_sea_mask is not None:
            lsm = land_sea_mask
            if bbox is not None:
                lsm = crop_to_bbox(lsm, bbox)
            err = apply_land_sea_mask(err, lsm, mode=mask_mode)
        rmse_mean = float(np.sqrt(np.nanmean((err.values) ** 2)))
        return {"status": "ok", "rmse_mean": rmse_mean, "err": err}
    except Exception as e:
        msg = str(e)
        status = "time_not_found" if "time_not_found" in msg else "failed"
        return {"status": status, "rmse_mean": np.nan, "err": None, "error": msg}


def compute_rmse_for_pairs(
    pairs_df: pd.DataFrame,
    variable_key: str,
    index_dir: Path,
    valid_hours: Optional[list[int]] = None,
    bbox: Optional[tuple[float, float, float, float]] = None,
    land_sea_mask: "xr.DataArray | None" = None,
    mask_mode: str = "none",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for _, row in pairs_df.iterrows():
        valid_dt = row["valid_dt"]
        if valid_hours is not None and valid_dt.hour not in valid_hours:
            rows.append(
                {
                    "variable": variable_key,
                    "init_dt": row["init_dt"],
                    "step": row["step"],
                    "valid_dt": valid_dt,
                    "aifs_path": row["aifs_path"],
                    "era5_path": row["era5_path"],
                    "status": "filtered_hour",
                    "rmse_mean": np.nan,
                    "error": "",
                }
            )
            continue

        if row["status"] != "ok":
            rows.append(
                {
                    "variable": variable_key,
                    "init_dt": row["init_dt"],
                    "step": row["step"],
                    "valid_dt": valid_dt,
                    "aifs_path": row["aifs_path"],
                    "era5_path": row["era5_path"],
                    "status": row["status"],
                    "rmse_mean": np.nan,
                    "error": "",
                }
            )
            continue

        result = compute_pair_rmse(
            aifs_path=Path(row["aifs_path"]),
            era5_path=Path(row["era5_path"]),
            valid_dt=valid_dt,
            variable_key=variable_key,
            index_dir=index_dir,
            step_hours=int(row["step"]) if "step" in row and pd.notna(row["step"]) else None,
            bbox=bbox,
            land_sea_mask=land_sea_mask,
            mask_mode=mask_mode,
        )

        rows.append(
            {
                "variable": variable_key,
                "init_dt": row["init_dt"],
                "step": row["step"],
                "valid_dt": valid_dt,
                "aifs_path": row["aifs_path"],
                "era5_path": row["era5_path"],
                "status": result["status"],
                "rmse_mean": result["rmse_mean"],
                "error": result.get("error", ""),
            }
        )

    pairs_manifest = pd.DataFrame(rows)

    ok_df = pairs_manifest[pairs_manifest["status"] == "ok"]
    rmse_by_step = (
        ok_df.groupby(["variable", "step"], as_index=False)
        .agg(rmse_mean=("rmse_mean", "mean"), n_samples=("rmse_mean", "count"))
    )
    return pairs_manifest, rmse_by_step


def aggregate_rmse_map(
    pairs_df: pd.DataFrame,
    variable_key: str,
    index_dir: Path,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    bbox: Optional[tuple[float, float, float, float]] = None,
    land_sea_mask: "xr.DataArray | None" = None,
    mask_mode: str = "none",
) -> Optional["xr.DataArray"]:
    sum_sq = None
    count = None

    for _, row in pairs_df.iterrows():
        valid_dt = row["valid_dt"]
        if start_date and valid_dt < start_date:
            continue
        if end_date and valid_dt > end_date:
            continue
        if row["status"] != "ok":
            continue

        result = compute_pair_rmse(
            aifs_path=Path(row["aifs_path"]),
            era5_path=Path(row["era5_path"]),
            valid_dt=valid_dt,
            variable_key=variable_key,
            index_dir=index_dir,
            step_hours=int(row["step"]) if "step" in row and pd.notna(row["step"]) else None,
            bbox=bbox,
            land_sea_mask=land_sea_mask,
            mask_mode=mask_mode,
        )
        if result["status"] != "ok" or result["err"] is None:
            continue

        err = result["err"]
        err_sq = (err ** 2)
        valid_mask = np.isfinite(err)
        if sum_sq is None:
            sum_sq = err_sq.fillna(0)
            count = xr.where(valid_mask, 1, 0)
        else:
            sum_sq = sum_sq + err_sq.fillna(0)
            count = count + xr.where(valid_mask, 1, 0)

    if sum_sq is None or count is None:
        return None
    rmse_map = np.sqrt(sum_sq / count.where(count > 0))
    rmse_map = rmse_map.where(count > 0)
    return rmse_map
