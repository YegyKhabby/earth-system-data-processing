from pathlib import Path
import sys
import pandas as pd
import numpy as np
import xarray as xr
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import rasterio
from rasterio.transform import rowcol
from matplotlib.colors import ListedColormap

# Paths (anchor to this script, not CWD)
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent.parent
AIFS_ROOT = REPO_ROOT / 'data' / 'aifs' / 'raw'
ERA5_ARCHIVE = REPO_ROOT / 'data' / 'era5' / 'archive' / 'real'
RMSE_OUT = REPO_ROOT / 'data' / 'rmse_outputs'
RESULTS_DIR = REPO_ROOT / 'results'
KOPPEN_RASTER = REPO_ROOT / 'data' / 'static' / 'koppen_geiger_0p1.tif'
# Fallback to available Köppen raster in repo
_KOPPEN_ALT = REPO_ROOT / 'data' / 'static' / 'koppen_geiger_climatezones_1991_2020_1km.tif'
if not KOPPEN_RASTER.exists() and _KOPPEN_ALT.exists():
    KOPPEN_RASTER = _KOPPEN_ALT
OROG_RASTER = REPO_ROOT / 'data' / 'static' / 'era5_orography.nc'
LSM_RASTER = REPO_ROOT / 'data' / 'static' / 'era5_land_sea_mask.nc'

# Create output directories
RMSE_OUT.mkdir(parents=True, exist_ok=True)
INDEX_DIR = RMSE_OUT / 'cfgrib_index'
INDEX_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Clean stale RMSE outputs from previous runs
def _remove_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
            print(f"  Removed old file: {path.name}")
    except Exception as e:
        print(f"  Warning: could not remove {path.name}: {e}")

print("Cleaning old RMSE outputs...\n")
for var in ['2t', 't500']:
    for suffix in ['by_step', 'by_day', 'by_hour']:
        _remove_if_exists(RMSE_OUT / f'rmse_{suffix}_{var}.nc')
        _remove_if_exists(RMSE_OUT / f'rmse_{suffix}_{var}.csv')

# Constants
VARIABLES = ['2t', 't500']
EUROPE_EXTENT = (-5, 25, 43, 58)  # (lon_min, lon_max, lat_min, lat_max)
VAR_LABELS = {
    "2t": "Temperature at 2m",
    "t500": "Temperature at 500 hPa",
}

# Plot configuration (user-tunable)
PLOT_CFG = {
    # RMSE dots
    "rmse_cmap": "YlOrRd",       # e.g., "cividis", "viridis", "YlOrRd"
    "rmse_size": 45,
    "rmse_edgecolor": "black",
    "rmse_alpha": 0.85,
    # Value range: set either absolute (vmin/vmax) or percentiles
    "rmse_vmin": None,            # absolute vmin (float) or None
    "rmse_vmax": None,            # absolute vmax (float) or None
    "rmse_pct": (5, 95),          # percentile range if vmin/vmax are None
    # Normalization to improve low-value contrast: "linear" or "power"
    "rmse_norm": "power",
    "rmse_gamma": 0.6,
    # Coarsening factor for plotting (1 = original grid, 2 = 0.5°, 4 = 1° for 0.25° data)
    "rmse_coarsen_factor": 4,
    # Backgrounds
    "koppen_alpha": 0.6,
    "orog_alpha": 0.2,
    "orog_cmap": "terrain",
    # Layout
    "legend_cols": 3,
    # Figure 2 config (Mean RMSE vs Lead Time)
    "skill_cmap": "viridis",
    "skill_vmin": None,           # absolute vmin or None
    "skill_vmax": None,           # absolute vmax or None
    "skill_pct": (5, 95),         # percentile range if vmin/vmax are None
    # Figure 6 (land-sea mask vs RMSE)
    "lsm_var": "2t",
    "lsm_step_hours": 6,
    "lsm_land_color": "#f0e6c8",
    "lsm_sea_color": "#9ecae1",
    
}

print(f"✓ Paths configured:")
print(f"  REPO_ROOT: {REPO_ROOT}")
print(f"  AIFS_ROOT: {AIFS_ROOT}")
print(f"  ERA5_ARCHIVE: {ERA5_ARCHIVE}")
print(f"  RMSE_OUT: {RMSE_OUT}")
# Import RMSE pipeline functions

mods_to_remove = [m for m in sys.modules.keys() if 'compute_aifs_era5_rmse' in m or 'aggregate_rmse_outputs' in m]
for m in mods_to_remove:
    del sys.modules[m]

# Add SCRIPTS_DIR to path
if str(SCRIPTS_DIR) in sys.path:
    sys.path.remove(str(SCRIPTS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from compute_aifs_era5_rmse import (
    index_aifs_files,
    index_era5_archive,
    filter_era5_index_by_product,
    filter_aifs_index_by_levtype,
    pair_aifs_with_era5_for_variable,
    compute_pair_rmse,
    EUROPE_BBOX,
    VARIABLE_CONFIG,
)

from aggregate_rmse_outputs import compute_rmse_outputs
# Run download scripts (idempotent)
import runpy

print("Running data access scripts...\n")
for script in [
    SCRIPTS_DIR / 'download_aifs_forecasts.py',
    SCRIPTS_DIR / 'download_era5_reanalysis.py',
]:
    try:
        print(f"  Running {script.name}...")
        runpy.run_path(str(script), run_name='__main__')
    except SystemExit as e:
        print(f"    (exited with code {e.code})")
    except Exception as e:
        print(f"    Error: {e}")

print("\n✓ Download scripts completed")
print("Indexing AIFS and ERA5 files...\n")

# Index AIFS
aifs_index = index_aifs_files(AIFS_ROOT)
print(f"AIFS Index:")
print(f"  Total files: {len(aifs_index)}")
print(f"  Date range: {aifs_index['valid_dt'].min()} to {aifs_index['valid_dt'].max()}")

# Extract lead times from filenames (e.g., step006, step012)
if 'path' in aifs_index.columns:
    steps = set()
    for fpath in aifs_index['path']:
        if 'step' in fpath:
            import re
            match = re.search(r'step(\d+)', fpath)
            if match:
                steps.add(int(match.group(1)))
    if steps:
        print(f"  Lead times (hours): {sorted(steps)}")

# Index ERA5
era5_all = index_era5_archive(ERA5_ARCHIVE, variable=None)
print(f"\nERA5 Index:")
print(f"  Total files: {len(era5_all)}")
if len(era5_all) > 0:
    print(f"  Date range: {era5_all['date'].min()} to {era5_all['date'].max()}")
    print(f"  Product tags: {list(era5_all['product_tag'].unique())}")
    for tag in sorted(era5_all['product_tag'].unique()):
        subset = era5_all[era5_all['product_tag'] == tag]
        print(f"    {tag}: {len(subset)} files")
        print("Pairing AIFS with ERA5...\n")

pairs_dict = {}

for var in VARIABLES:
    print(f"{var}:")
    
    # Get config
    config = VARIABLE_CONFIG[var]
    aifs_levtype = "sfc" if config["aifs"]["filter_by_keys"]["typeOfLevel"] == "heightAboveGround" else "pl"
    
    # Determine ERA5 product tag
    if var == "2t":
        era5_tag = "t2m"
    elif var == "t500":
        era5_tag = "t_pl500"
    else:
        era5_tag = config["era5"]["var"]
    
    # Filter indices
    aifs_filt = filter_aifs_index_by_levtype(aifs_index, aifs_levtype)
    era5_filt = filter_era5_index_by_product(era5_all, era5_tag)
    
    print(f"  AIFS {aifs_levtype}: {len(aifs_filt)} files")
    print(f"  ERA5 {era5_tag}: {len(era5_filt)} files")
    
    if len(era5_filt) == 0:
        print(f"  ⚠️  No ERA5 files for {var}, skipping")
        continue
    
    # Pair
    pairs = pair_aifs_with_era5_for_variable(aifs_filt, era5_filt, var)
    pairs_dict[var] = pairs
    
    # Status breakdown
    status_counts = pairs['status'].value_counts().to_dict()
    ok_pairs = len(pairs[pairs['status'] == 'ok'])
    print(f"  Total pairs: {len(pairs)}")
    print(f"  OK pairs: {ok_pairs}")
    print(f"  Status breakdown: {status_counts}")
    
    # Save manifest
    pairs.to_csv(RMSE_OUT / f'pairs_manifest_{var}.csv', index=False)
    print(f"  ✓ Saved pairs_manifest_{var}.csv\n")
    # Compute spatial and temporal aggregations
print("Computing RMSE outputs (spatial maps + aggregations)...\n")

pairs_2t = pairs_dict.get('2t')
pairs_t500 = pairs_dict.get('t500')

compute_rmse_outputs(
    pairs_2t=pairs_2t,
    pairs_t500=pairs_t500,
    compute_rmse_for_pairs_func=compute_pair_rmse,
    index_dir=INDEX_DIR,
    output_dir=RMSE_OUT,
    bbox=EUROPE_BBOX,
    variables=VARIABLES,
)

print("\n✓ RMSE outputs computation completed")
print("Loading and validating RMSE outputs...\n")

# Data loaders (eager-load then close to avoid netCDF handle issues)
def _open_rmse(path: Path) -> xr.Dataset:
    ds = xr.open_dataset(path)
    ds.load()
    ds.close()
    return ds

def load_rmse_by_step(var):
    path = RMSE_OUT / f'rmse_by_step_{var}.nc'
    return _open_rmse(path)

def load_rmse_by_day(var):
    path = RMSE_OUT / f'rmse_by_day_{var}.nc'
    return _open_rmse(path)

def load_rmse_by_hour(var):
    path = RMSE_OUT / f'rmse_by_hour_{var}.nc'
    return _open_rmse(path)

# Validate outputs for each variable
outputs_summary = {}

for var in VARIABLES:
    print(f"{var}:")
    results = {}
    
    for agg_type, loader in [
        ('by_step', load_rmse_by_step),
        ('by_day', load_rmse_by_day),
        ('by_hour', load_rmse_by_hour),
    ]:
        try:
            ds = loader(var)
            results[agg_type] = ds
            
            rmse = ds['rmse']
            dims_str = f"{list(rmse.dims)}"
            shape_str = f"{rmse.shape}"
            n_pairs = ds.attrs.get('n_pairs', 'N/A')
            
            print(f"  {agg_type}: dims={dims_str}, shape={shape_str}, n_pairs={n_pairs}")
        except FileNotFoundError:
            print(f"  {agg_type}: ⚠️  File not found")
        except Exception as e:
            print(f"  {agg_type}: ✗ Error - {e}")
    
    outputs_summary[var] = results
    print()
    # Detailed sanity check
print("Detailed output validation:\n")

for var in VARIABLES:
    print(f"\n{var}:")
    
    try:
        ds_step = load_rmse_by_step(var)
        rmse = ds_step['rmse']
        
        print(f"  RMSE by step:")
        print(f"    Min: {float(rmse.min()):.4f} K")
        print(f"    Max: {float(rmse.max()):.4f} K")
        print(f"    Mean: {float(rmse.mean()):.4f} K")
        print(f"    NaN fraction: {float(np.isnan(rmse).sum()) / rmse.size:.1%}")
        print(f"    Steps available: {list(ds_step.coords['step'].values)}")
    except Exception as e:
        print(f"  Error: {e}")

def _maybe_coarsen(da, lat_name, lon_name, factor):
    if factor is None or int(factor) <= 1:
        return da
    return da.coarsen(**{lat_name: int(factor), lon_name: int(factor)}, boundary='trim').mean()

# --- Sanity helpers for plotting time ranges ---
def _pairs_date_range(pairs_df):
    if pairs_df is None or len(pairs_df) == 0:
        return "N/A", "N/A", 0
    if "status" in pairs_df.columns:
        ok = pairs_df[pairs_df["status"] == "ok"]
    else:
        ok = pairs_df
    if ok.empty:
        return "N/A", "N/A", 0
    return str(ok["valid_dt"].min()), str(ok["valid_dt"].max()), len(ok)

def _overall_ok_date_range(pairs_dict, variables):
    mins = []
    maxs = []
    total_ok = 0
    for v in variables:
        dmin, dmax, n_ok = _pairs_date_range(pairs_dict.get(v))
        if dmin != "N/A":
            mins.append(pd.to_datetime(dmin))
            maxs.append(pd.to_datetime(dmax))
            total_ok += n_ok
    if not mins or not maxs:
        return "N/A", "N/A", total_ok
    return str(min(mins)), str(max(maxs)), total_ok
# Helper plotting functions

def setup_map_ax(title="", extent=EUROPE_EXTENT):
    """Create cartographic axes over Europe."""
    fig = plt.figure(figsize=(12, 8))
    ax = plt.axes(projection=ccrs.PlateCarree())
    ax.set_extent(extent, crs=ccrs.PlateCarree())
    ax.coastlines(linewidth=0.5)
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    
    gl = ax.gridlines(draw_labels=True, linestyle='--', linewidth=0.3, alpha=0.5)
    gl.top_labels = False
    gl.right_labels = False
    
    if title:
        ax.set_title(title, fontsize=14, fontweight='bold')
    
    return fig, ax


def load_lsm_crop(lsm_path, extent):
    """Return (lsm_da, lat_name, lon_name) or (None, None, None) on error."""
    if not lsm_path.exists():
        return None, None, None
    try:
        ds = xr.open_dataset(lsm_path)
        var = 'lsm' if 'lsm' in ds else list(ds.data_vars)[0]
        lsm = ds[var]
        if lsm.ndim > 2:
            lsm = lsm.squeeze()
        lsm.load()
        ds.close()
        lat_name = None
        lon_name = None
        for dim in lsm.dims:
            if dim in ('latitude', 'lat'):
                lat_name = dim
            elif dim in ('longitude', 'lon'):
                lon_name = dim
        if lat_name is None or lon_name is None:
            return None, None, None
        lon_min, lon_max, lat_min, lat_max = extent
        lsm_crop = lsm.sel(
            **{lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)}
        )
        if lsm_crop.ndim != 2:
            return None, None, None
        return lsm_crop, lat_name, lon_name
    except Exception as e:
        print("LSM load error:", e)
        return None, None, None


# Preload LSM once (Köppen/orography are loaded once inside the Figure 1 block)
try:
    lsm_da, lsm_lat_name, lsm_lon_name = load_lsm_crop(LSM_RASTER, EUROPE_EXTENT)
except Exception:
    lsm_da, lsm_lat_name, lsm_lon_name = (None, None, None)

print(
    "lsm: "
    f"{None if lsm_da is None else lsm_da.shape}"
)
# Figure 1: RMSE Maps over Europe (IMPROVED VISUALIZATION)
# - Prominent Köppen background with distinct colors
# - Visible RMSE grid dots with color mapping
# - Proper coordinate handling and error checking

import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import matplotlib.colors as mcolors
import warnings
import time
from rasterio.windows import from_bounds
warnings.filterwarnings('ignore')

try:
    t_start = time.time()
    
    # ========== PRELOAD BACKGROUNDS ONCE ==========
    lon_min, lon_max, lat_min, lat_max = EUROPE_EXTENT  # (-5, 25, 43, 58)
    
    # Load and crop Köppen once (RGBA so colors are fixed)
    koppen_image = None
    koppen_extent = None
    koppen_legend = None
    koppen_present_codes = []
    try:
        koppen_path = KOPPEN_RASTER
        if not koppen_path.exists():
            fallback = Path.home() / "Downloads" / "koppen_geiger_0p1.tif"
            if fallback.exists():
                koppen_path = fallback
        if koppen_path.exists():
            src = rasterio.open(str(koppen_path))
            koppen_full = src.read(1)
            koppen_transform = src.transform

            window = from_bounds(lon_min, lat_min, lon_max, lat_max, koppen_transform)
            row_min, col_min = int(window.row_off), int(window.col_off)
            row_max = row_min + int(window.height)
            col_max = col_min + int(window.width)
            koppen_crop = koppen_full[row_min:row_max, col_min:col_max]

            koppen_code_to_abbrev = {
                1: "Af", 2: "Am", 3: "Aw", 4: "BWh", 5: "BWk", 6: "BSh", 7: "BSk",
                8: "Csa", 9: "Csb", 10: "Csc", 11: "Cwa", 12: "Cwb", 13: "Cwc",
                14: "Cfa", 15: "Cfb", 16: "Cfc", 17: "Dsa", 18: "Dsb", 19: "Dsc", 20: "Dsd",
                21: "Dwa", 22: "Dwb", 23: "Dwc", 24: "Dwd", 25: "Dfa", 26: "Dfb",
                27: "Dfc", 28: "Dfd", 29: "ET", 30: "EF"
            }
            koppen_abbrev_to_full = {
                "Af": "Tropical rainforest",      "Am": "Tropical monsoon",
                "Aw": "Tropical savanna",         "BWh": "Hot desert",
                "BWk": "Cold desert",             "BSh": "Hot semi-arid",
                "BSk": "Cold semi-arid",          "Csa": "Hot-summer Mediterranean",
                "Csb": "Warm-summer Mediterranean", "Csc": "Cold-summer Mediterranean",
                "Cwa": "Subtropical monsoon",     "Cwb": "Subtropical highland",
                "Cwc": "Cold subtropical highland","Cfa": "Humid subtropical",
                "Cfb": "Temperate oceanic",       "Cfc": "Subpolar oceanic",
                "Dsa": "Hot-summer humid continental", "Dsb": "Warm-summer humid continental",
                "Dsc": "Cold-summer humid continental", "Dsd": "Extremely cold-summer continental",
                "Dwa": "Monsoon-influenced humid continental", "Dwb": "Dry-winter warm-summer continental",
                "Dwc": "Dry-winter cold-summer continental", "Dwd": "Dry-winter extremely cold-summer continental",
                "Dfa": "Hot humid continental",   "Dfb": "Warm-summer humid continental",
                "Dfc": "Subarctic",               "Dfd": "Extremely cold subarctic",
                "ET": "Alpine tundra",            "EF": "Polar ice cap"
            }

            color_map = plt.cm.tab20.colors
            koppen_color_map = {code: color_map[i % 20] for i, code in enumerate(koppen_code_to_abbrev.keys())}

            colored_koppen = np.zeros((*koppen_crop.shape, 4), dtype=float)
            present_codes = sorted({int(c) for c in np.unique(koppen_crop) if int(c) in koppen_code_to_abbrev})
            koppen_present_codes = present_codes
            for code in present_codes:
                rgba = plt.matplotlib.colors.to_rgba(koppen_color_map.get(code, "#f0f0f0"))
                colored_koppen[koppen_crop == code] = rgba
            colored_koppen[(koppen_crop < 1) | (koppen_crop > 30)] = plt.matplotlib.colors.to_rgba("#f0f0f0")

            koppen_image = colored_koppen
            koppen_extent = [lon_min, lon_max, lat_min, lat_max]

            legend_patches = []
            for code in present_codes:
                abbrev = koppen_code_to_abbrev[code]
                full_name = koppen_abbrev_to_full.get(abbrev, "Unknown")
                patch = mpatches.Patch(color=koppen_color_map[code], label=f"{abbrev} – {full_name}")
                legend_patches.append(patch)
            koppen_legend = legend_patches

            print(f"✓ Köppen loaded: {koppen_crop.shape}, {len(present_codes)} classes")
            src.close()
    except Exception as e:
        print(f"⚠ Köppen background unavailable: {e}")
    
    # Load and crop orography once
    orog_image = None
    try:
        if OROG_RASTER.exists():
            ds_orog = xr.open_dataset(OROG_RASTER)
            if 'z' in ds_orog:
                z = ds_orog['z'] / 9.80665  # geopotential to meters
                if z.ndim > 2:
                    z = z.squeeze()
                
                # Crop to EUROPE_EXTENT
                z_crop = z.sel(
                    longitude=slice(lon_min, lon_max),
                    latitude=slice(lat_max, lat_min)
                )
                z_values = np.squeeze(z_crop.values)
                
                if z_values.ndim == 2:
                    orog_image = z_values
                    orog_vmin, orog_vmax = np.nanmin(z_values), np.nanmax(z_values)
                    print(f"✓ Orography loaded: {z_values.shape}")
    except Exception as e:
        print(f"⚠ Orography unavailable: {e}")
    
    print()

    # ========== GLOBAL RMSE COLOR SCALE (shared across panels) ==========
    global_vmin, global_vmax = None, None
    rmse_norm = None
    try:
        vals = []
        for var in VARIABLES:
            ds_step = load_rmse_by_step(var)
            rmse = ds_step['rmse'].isel(step=0).squeeze()
            # Find lat/lon names
            lat_name = None
            lon_name = None
            for dim in rmse.dims:
                if dim in ('latitude', 'lat'):
                    lat_name = dim
                elif dim in ('longitude', 'lon'):
                    lon_name = dim
            if lat_name is None or lon_name is None:
                continue
            rmse_map = rmse.sel(
                **{lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)}
            ).sortby(lat_name)
            rmse_coarse = _maybe_coarsen(rmse_map, lat_name, lon_name, PLOT_CFG["rmse_coarsen_factor"])
            arr = rmse_coarse.values
            arr = arr[np.isfinite(arr)]
            if arr.size:
                vals.append(arr)
        if vals:
            all_vals = np.concatenate(vals)
            if PLOT_CFG["rmse_vmin"] is not None and PLOT_CFG["rmse_vmax"] is not None:
                global_vmin = float(PLOT_CFG["rmse_vmin"])
                global_vmax = float(PLOT_CFG["rmse_vmax"])
            else:
                # True min/max across both variables for Figure 1
                global_vmin = float(np.nanmin(all_vals))
                global_vmax = float(np.nanmax(all_vals))
            if PLOT_CFG["rmse_norm"] == "power":
                rmse_norm = mcolors.PowerNorm(
                    gamma=float(PLOT_CFG["rmse_gamma"]),
                    vmin=global_vmin,
                    vmax=global_vmax,
                )
            else:
                rmse_norm = mcolors.Normalize(vmin=global_vmin, vmax=global_vmax)
    except Exception:
        global_vmin, global_vmax = None, None
        rmse_norm = None
    
    print("SANITY FIG1 (RMSE maps):")
    for var in VARIABLES:
        dmin, dmax, n_ok = _pairs_date_range(pairs_dict.get(var))
        print(f"  {var}: ok_pairs={n_ok}, valid_dt range={dmin} to {dmax}")
    fig1_date_min, fig1_date_max, _ = _overall_ok_date_range(pairs_dict, VARIABLES)

    # ========== PLOT LOOP ==========
    fig = plt.figure(figsize=(18, 8))
    gs = gridspec.GridSpec(1, 2, figure=fig, hspace=0.3, wspace=0.35)
    rmse_mappable = None
    
    orog_mappable = None
    for plot_idx, var in enumerate(VARIABLES):
        print(f"  Plotting {var}...")
        t_var_start = time.time()
        
        try:
            ax = fig.add_subplot(gs[0, plot_idx], projection=ccrs.PlateCarree())
            ax.set_extent(EUROPE_EXTENT, crs=ccrs.PlateCarree())
            
            # --- Load and crop RMSE to EUROPE_EXTENT ---
            t_load = time.time()
            ds_step = load_rmse_by_step(var)
            rmse = ds_step['rmse']
            rmse_full = rmse.isel(step=0).squeeze()
            step_val = int(rmse_full.step.values)
            print(f"    Sanity: using step={step_val}h from rmse_by_step_{var}.nc")
            
            # Determine coordinate names (try both naming conventions)
            lat_name = None
            lon_name = None
            for dim in rmse_full.dims:
                if dim in ('latitude', 'lat'):
                    lat_name = dim
                elif dim in ('longitude', 'lon'):
                    lon_name = dim
            
            if lat_name is None or lon_name is None:
                print(f"    ✗ Cannot find lat/lon coords. Dims: {rmse_full.dims}")
                ax.text(0.5, 0.5, f'Coordinate error:\nExpected lat/lon, got {rmse_full.dims}',
                       ha='center', va='center', fontsize=10, color='red')
                ax.axis('off')
                continue
            
            # Crop to EUROPE_EXTENT
            rmse_map = rmse_full.sel(
                **{lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)}
            )
            print(f"    Load: {time.time()-t_load:.2f}s")
            
            # --- Sort latitude ascending and coarsen ---
            t_coarse = time.time()
            rmse_map = rmse_map.sortby(lat_name)
            rmse_coarse = _maybe_coarsen(rmse_map, lat_name, lon_name, PLOT_CFG["rmse_coarsen_factor"])
            print(f"    Coarsen: {time.time()-t_coarse:.2f}s")
            
            # --- Extract coordinates ---
            lats = rmse_coarse[lat_name].values
            lons = rmse_coarse[lon_name].values
            rmse_plot = rmse_coarse.values
            extent_data = [lons.min(), lons.max(), lats.min(), lats.max()]
            
            print(f"    Data shape: {rmse_plot.shape}, extent: {extent_data}")
            
            # --- LAYER 0: Köppen background (PROMINENT) ---
            if koppen_image is not None and koppen_extent is not None:
                ax.imshow(
                    koppen_image,
                    origin='upper',
                    extent=koppen_extent,
                    transform=ccrs.PlateCarree(),
                    alpha=PLOT_CFG["koppen_alpha"],
                    zorder=0
                )
            
            # --- LAYER 1: Orography overlay (pixelated grid) ---
            if orog_image is not None:
                orog_mappable = ax.imshow(
                    orog_image,
                    origin='upper',
                    extent=[lon_min, lon_max, lat_min, lat_max],
                    cmap=PLOT_CFG["orog_cmap"],
                    transform=ccrs.PlateCarree(),
                    vmin=orog_vmin,
                    vmax=orog_vmax,
                    interpolation='nearest',
                    alpha=PLOT_CFG["orog_alpha"],
                    zorder=1
                )
            
            # --- RMSE dots only (no background heatmap) ---
            valid_mask = ~np.isnan(rmse_plot)
            if global_vmin is not None and global_vmax is not None:
                vmin, vmax = global_vmin, global_vmax
            elif valid_mask.any():
                vmin = np.nanpercentile(rmse_plot, 5)
                vmax = np.nanpercentile(rmse_plot, 95)
            else:
                vmin, vmax = 0, 1
            
            # --- LAYER 5: Grid dots with COLOR MAPPING (VISIBLE) ---
            t_dots = time.time()
            stride = 2  # More frequent dots for visibility
            lon_grid, lat_grid = np.meshgrid(lons, lats)
            
            # Flatten and create scatter with color values
            lon_scatter = lon_grid[::stride, ::stride].ravel()
            lat_scatter = lat_grid[::stride, ::stride].ravel()
            rmse_scatter = rmse_plot[::stride, ::stride].ravel()
            
            # Only plot where data exists
            valid_idx = ~np.isnan(rmse_scatter)
            scatter_kwargs = dict(
                c=rmse_scatter[valid_idx],
                cmap=PLOT_CFG["rmse_cmap"],
                s=PLOT_CFG["rmse_size"],
                alpha=PLOT_CFG["rmse_alpha"],
                edgecolors=PLOT_CFG["rmse_edgecolor"],
                linewidths=0.5,
                transform=ccrs.PlateCarree(),
                zorder=5,
                marker='o',
            )
            if rmse_norm is not None:
                scatter_kwargs["norm"] = rmse_norm
            else:
                scatter_kwargs["vmin"] = vmin
                scatter_kwargs["vmax"] = vmax

            scatter = ax.scatter(
                lon_scatter[valid_idx],
                lat_scatter[valid_idx],
                **scatter_kwargs
            )
            if rmse_mappable is None:
                rmse_mappable = scatter
            print(f"    Dots: {time.time()-t_dots:.2f}s")
            
            # --- Map features (coastlines, borders) ---
            ax.coastlines(linewidth=1.0, color='black', zorder=10)
            ax.add_feature(cfeature.BORDERS, linewidth=0.7, color='black', linestyle='-', zorder=10)
            
            gl = ax.gridlines(draw_labels=True, linestyle='--', linewidth=0.2, alpha=0.4, zorder=2)
            gl.top_labels = False
            gl.right_labels = False
            
            # --- Title and stats ---
            ax.set_title(f'{VAR_LABELS.get(var, var)} – Lead {step_val}h (RMSE, °C)',
                        fontsize=12, fontweight='bold', pad=10)
            
            if valid_mask.any():
                mean_val = np.nanmean(rmse_plot[valid_mask])
                min_val = np.nanmin(rmse_plot[valid_mask])
                max_val = np.nanmax(rmse_plot[valid_mask])
                stats_text = (
                    f'Mean: {mean_val:.2f}°C\n'
                    f'Min: {min_val:.2f}°C\n'
                    f'Max: {max_val:.2f}°C\n'
                    f'Samples: {valid_mask.sum()}'
                )
                ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                       fontsize=8, verticalalignment='top',
                       bbox=dict(boxstyle='round', facecolor='white', alpha=0.85), zorder=20)
            
            print(f"    {var} total: {time.time()-t_var_start:.2f}s")
            
        except FileNotFoundError as e:
            ax = fig.add_subplot(gs[0, plot_idx])
            ax.text(0.5, 0.5, f'Data not found:\n{var}\n\nRe-run cell 6 after\ndeleting old outputs',
                   ha='center', va='center', fontsize=11, color='red')
            ax.axis('off')
        except Exception as e:
            ax = fig.add_subplot(gs[0, plot_idx])
            error_msg = f'{type(e).__name__}: {str(e)[:60]}'
            ax.text(0.5, 0.5, f'Error:\n{error_msg}',
                   ha='center', va='center', fontsize=9, color='red')
            ax.axis('off')
            import traceback
            traceback.print_exc()

    # Shared RMSE colorbar (single bar for both plots) placed outside plots
    if rmse_mappable is not None:
        cax = fig.add_axes([0.92, 0.20, 0.015, 0.60])
        cbar_rmse = fig.colorbar(rmse_mappable, cax=cax, orientation='vertical')
        cbar_rmse.set_label('RMSE (°C)', fontsize=10, fontweight='bold')
        cbar_rmse.ax.tick_params(labelsize=9)

    # Add a shared orography colorbar if available
    if orog_mappable is not None:
        cbar_orog = fig.colorbar(orog_mappable, ax=fig.axes, orientation='horizontal', shrink=0.7, pad=0.08)
        cbar_orog.set_label('Orography Height (m)', fontsize=9)
        cbar_orog.ax.tick_params(labelsize=8)

    # Add Köppen legend (present classes only) below orography bar
    if koppen_legend:
        fig.legend(
            handles=koppen_legend,
            loc='lower center',
            bbox_to_anchor=(0.5, -0.26),
            ncol=PLOT_CFG["legend_cols"],
            fontsize=8,
            title="Köppen Climate Zones",
            frameon=False
        )

    # Final touches
    date_min, date_max = fig1_date_min, fig1_date_max

    suptitle = (
        "RMSE Comparison – AIFS vs ERA5 over Europe\n"
        "RMSE = root-mean-square error between AIFS forecasts and ERA5 reanalysis\n"
        f"AIFS–ERA5 paired dates: {date_min} to {date_max}"
    )
    fig.suptitle(suptitle, fontsize=13, fontweight='bold', y=0.96)
    fig.subplots_adjust(bottom=0.36, right=0.90, top=0.86)
    
    fig_path = str(RESULTS_DIR / 'fig01_rmse_maps_europe.png')
    t_save = time.time()
    plt.savefig(fig_path, dpi=120, bbox_inches='tight')
    print(f"\n  Save: {time.time()-t_save:.2f}s")
    
    plt.show()
    print(f"\n✓ Figure 1 complete in {time.time()-t_start:.2f}s")
    print(f"✓ Saved to: {fig_path}")

    # Close fig1 before creating figure 2 to avoid overlaps
    plt.close(fig)

    # --- Figure 2: Mean RMSE vs lead time (skill proxy) ---
    try:
        fig2 = plt.figure(figsize=(7.5, 5.0))
        ax2 = fig2.add_subplot(1, 1, 1)
        all_rows = []
        for var in VARIABLES:
            csv_path = RMSE_OUT / f'rmse_by_step_{var}.csv'
            if not csv_path.exists():
                continue
            df = pd.read_csv(csv_path)
            df["variable"] = var
            all_rows.append(df)
        if all_rows:
            df_all = pd.concat(all_rows, ignore_index=True)
        else:
            df_all = pd.DataFrame(columns=["step", "rmse_mean", "variable"])

        print("SANITY FIG2 (Mean RMSE vs Lead Time):")
        for var in VARIABLES:
            dmin, dmax, n_ok = _pairs_date_range(pairs_dict.get(var))
            print(f"  {var}: ok_pairs={n_ok}, valid_dt range={dmin} to {dmax}")
        if not df_all.empty:
            steps = sorted(df_all["step"].unique())
            print(f"  steps used: {steps}")
        else:
            print("  steps used: N/A (no data)")

        # Determine y-range for consistent interpretation
        if not df_all.empty:
            if PLOT_CFG["skill_vmin"] is not None and PLOT_CFG["skill_vmax"] is not None:
                y_min = float(PLOT_CFG["skill_vmin"])
                y_max = float(PLOT_CFG["skill_vmax"])
            else:
                p_lo, p_hi = PLOT_CFG["skill_pct"]
                y_min = float(np.nanpercentile(df_all["rmse_mean"], p_lo))
                y_max = float(np.nanpercentile(df_all["rmse_mean"], p_hi))
        else:
            y_min, y_max = None, None

        # Plot per variable with color mapped to RMSE value
        cmap = plt.get_cmap(PLOT_CFG["skill_cmap"])
        norm = None
        if y_min is not None and y_max is not None:
            norm = mcolors.Normalize(vmin=y_min, vmax=y_max)

        for var in VARIABLES:
            df = df_all[df_all["variable"] == var]
            if df.empty:
                continue
            if norm is not None:
                colors = cmap(norm(df["rmse_mean"].values))
            else:
                colors = None
            ax2.plot(df['step'], df['rmse_mean'], color="#333333", linewidth=1.2, alpha=0.6)
            ax2.scatter(df['step'], df['rmse_mean'], c=colors, cmap=cmap, norm=norm, s=55, label=var, edgecolors="black")
        ax2.set_title("Mean RMSE vs Lead Time (AIFS vs ERA5)", fontsize=12, fontweight='bold')
        ax2.set_xlabel("Lead time (hours)")
        ax2.set_ylabel("RMSE (°C)")
        if y_min is not None and y_max is not None:
            pad = 0.12 * (y_max - y_min) if y_max > y_min else 0.15
            ax2.set_ylim(y_min - pad, y_max + pad)
        ax2.margins(y=0.08)
        ax2.grid(True, linestyle='--', alpha=0.4)
        ax2.legend(frameon=False)
        # Show actual step values on x-axis
        if not df_all.empty:
            steps = sorted(df_all["step"].unique())
            ax2.set_xticks(steps)
        if norm is not None:
            cbar2 = fig2.colorbar(
                plt.cm.ScalarMappable(norm=norm, cmap=cmap),
                ax=ax2, orientation='vertical', pad=0.03
            )
            cbar2.set_label("RMSE (°C)")

        # Add metadata text for interpretability
        date_min, date_max, _ = _overall_ok_date_range(pairs_dict, VARIABLES)
        ax2.text(
            0.02, 0.98,
            f"AIFS–ERA5 paired dates: {date_min} to {date_max}\n"
            f"Variables: {', '.join([VAR_LABELS.get(v, v) for v in VARIABLES if v in df_all['variable'].unique()])}\n"
            "Metric: Mean RMSE by lead step",
            transform=ax2.transAxes, va="top", fontsize=8,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85)
        )
        fig2.tight_layout()
        fig2_path = str(RESULTS_DIR / 'fig02_rmse_mean_vs_lead.png')
        fig2.savefig(fig2_path, dpi=140, bbox_inches='tight')
        print(f"✓ Figure 2 saved to: {fig2_path}")
        plt.show()
    except Exception as e:
        print(f"✗ Figure 2 failed: {type(e).__name__}: {e}")

    # --- Figure 3: Köppen-only + RMSE dots at 06:00 and 18:00 for 2t ---
    try:
        fig3 = plt.figure(figsize=(14, 6))
        gs3 = gridspec.GridSpec(1, 2, figure=fig3, hspace=0.3, wspace=0.25)
        hours = [6, 18]
        hour_means = []
        hour_mins = []
        hour_maxs = []
        rmse_cache = {}

        # Precompute RMSE fields for normalization
        ds_hour = load_rmse_by_hour("2t")
        for hour_val in hours:
            rmse = ds_hour['rmse'].sel(hour=hour_val).squeeze()
            lat_name = 'latitude' if 'latitude' in rmse.dims else 'lat'
            lon_name = 'longitude' if 'longitude' in rmse.dims else 'lon'
            rmse_map = rmse.sel(
                **{lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)}
            ).sortby(lat_name)
            rmse_coarse = _maybe_coarsen(rmse_map, lat_name, lon_name, PLOT_CFG["rmse_coarsen_factor"])
            rmse_cache[hour_val] = {
                "lat_name": lat_name,
                "lon_name": lon_name,
                "lats": rmse_coarse[lat_name].values,
                "lons": rmse_coarse[lon_name].values,
                "rmse_plot": rmse_coarse.values,
            }

        # Figure-specific norm for better contrast at low RMSE
        all_vals = np.concatenate([v["rmse_plot"][np.isfinite(v["rmse_plot"])] for v in rmse_cache.values()])
        if all_vals.size > 0:
            # True min/max across both hours for Figure 3
            vmin3 = float(np.nanmin(all_vals))
            vmax3 = float(np.nanmax(all_vals))
            norm3 = mcolors.PowerNorm(gamma=float(PLOT_CFG["rmse_gamma"]), vmin=vmin3, vmax=vmax3)
        else:
            vmin3, vmax3, norm3 = None, None, None

        for i, hour_val in enumerate(hours):
            axh = fig3.add_subplot(gs3[0, i], projection=ccrs.PlateCarree())
            axh.set_extent(EUROPE_EXTENT, crs=ccrs.PlateCarree())

            # Köppen-only background
            if koppen_image is not None and koppen_extent is not None:
                axh.imshow(
                    koppen_image,
                    origin='upper',
                    extent=koppen_extent,
                    transform=ccrs.PlateCarree(),
                    alpha=1.0,
                    zorder=0
                )

            cached = rmse_cache[hour_val]
            lats = cached["lats"]
            lons = cached["lons"]
            rmse_plot = cached["rmse_plot"]
            hour_means.append(float(np.nanmean(rmse_plot)))
            hour_mins.append(float(np.nanmin(rmse_plot)))
            hour_maxs.append(float(np.nanmax(rmse_plot)))

            lon_grid, lat_grid = np.meshgrid(lons, lats)
            stride = 2
            lon_scatter = lon_grid[::stride, ::stride].ravel()
            lat_scatter = lat_grid[::stride, ::stride].ravel()
            rmse_scatter = rmse_plot[::stride, ::stride].ravel()
            valid_idx = ~np.isnan(rmse_scatter)

            scatter_kwargs = dict(
                c=rmse_scatter[valid_idx],
                cmap=PLOT_CFG["rmse_cmap"],
                s=PLOT_CFG["rmse_size"],
                alpha=PLOT_CFG["rmse_alpha"],
                edgecolors=PLOT_CFG["rmse_edgecolor"],
                linewidths=0.5,
                transform=ccrs.PlateCarree(),
                zorder=5,
                marker='o',
            )
            if norm3 is not None:
                scatter_kwargs["norm"] = norm3
            else:
                scatter_kwargs["vmin"] = vmin3
                scatter_kwargs["vmax"] = vmax3

            sc = axh.scatter(lon_scatter[valid_idx], lat_scatter[valid_idx], **scatter_kwargs)

            axh.coastlines(linewidth=1.0, color='black', zorder=10)
            axh.add_feature(cfeature.BORDERS, linewidth=0.7, color='black', linestyle='-', zorder=10)
            gl = axh.gridlines(draw_labels=True, linestyle='--', linewidth=0.2, alpha=0.4, zorder=2)
            gl.top_labels = False
            gl.right_labels = False

            axh.set_title(
                f"{VAR_LABELS.get('2t', '2t')} RMSE at {hour_val:02d}:00 UTC",
                fontsize=11, fontweight='bold', pad=8
            )

            # Per-panel stats (same style as Figure 1)
            if valid_idx.any():
                mean_val = float(np.nanmean(rmse_plot))
                min_val = float(np.nanmin(rmse_plot))
                max_val = float(np.nanmax(rmse_plot))
                stats_text = f"Mean: {mean_val:.2f}°C\nMin: {min_val:.2f}°C\nMax: {max_val:.2f}°C"
                axh.text(
                    0.02, 0.98, stats_text,
                    transform=axh.transAxes, fontsize=8, va='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.85), zorder=20
                )

        # Shared RMSE colorbar for fig3
        cax3 = fig3.add_axes([0.92, 0.20, 0.015, 0.60])
        fig3.colorbar(sc, cax=cax3, orientation='vertical').set_label("RMSE (°C)")

        date_min, date_max, _ = _overall_ok_date_range(pairs_dict, VARIABLES)
        fig3.suptitle(
            f"RMSE Dots for {VAR_LABELS.get('2t', '2t')}: 06:00 vs 18:00 UTC | "
            f"AIFS–ERA5 paired dates: {date_min} to {date_max}",
            fontsize=12, fontweight='bold', y=0.98
        )
        fig3.subplots_adjust(right=0.90, bottom=0.36, top=0.86)

        # No bottom-left summary box for Figure 3

        # Köppen legend + names (same style as Figure 1)
        if koppen_legend:
            fig3.legend(
                handles=koppen_legend,
                loc='lower center',
                bbox_to_anchor=(0.5, -0.26),
                ncol=PLOT_CFG["legend_cols"],
                fontsize=8,
                title="Köppen Climate Zones",
                frameon=False
            )
        try:
            koppen_items = []
            if koppen_present_codes:
                for code in koppen_present_codes:
                    abbrev = koppen_code_to_abbrev.get(code)
                    if not abbrev:
                        continue
                    full_name = koppen_abbrev_to_full.get(abbrev, "Unknown")
                    koppen_items.append((code, f"■ {abbrev} – {full_name}"))
            if koppen_items:
                cols = 3
                rows = int(np.ceil(len(koppen_items) / cols))
                columns = [koppen_items[i*rows:(i+1)*rows] for i in range(cols)]
                x_positions = [0.10, 0.40, 0.70]
                for x, col in zip(x_positions, columns):
                    y = 0.02
                    for code, line in col:
                        fig3.text(
                            x, y,
                            line,
                            ha='left',
                            va='bottom',
                            fontsize=7,
                            color=koppen_color_map.get(code, "#555555"),
                        )
                        y += 0.018
        except Exception:
            pass

        fig3_path = str(RESULTS_DIR / 'fig03_rmse_2mtemp_06_18.png')
        fig3.savefig(fig3_path, dpi=140, bbox_inches='tight')
        print(f"✓ Figure 3 saved to: {fig3_path}")
        plt.show()
    except Exception as e:
        print(f"✗ Figure 3 failed: {type(e).__name__}: {e}")

    # --- Figure 4: Orography-only + RMSE dots at 00:00 and 12:00 for 2t ---
    try:
        fig4 = plt.figure(figsize=(14, 6))
        gs4 = gridspec.GridSpec(1, 2, figure=fig4, hspace=0.3, wspace=0.25)
        hours4 = [0, 12]
        hour_means4 = []
        hour_mins4 = []
        hour_maxs4 = []
        rmse_cache4 = {}

        # Precompute RMSE fields for normalization
        ds_hour4 = load_rmse_by_hour("2t")
        for hour_val in hours4:
            rmse = ds_hour4['rmse'].sel(hour=hour_val).squeeze()
            lat_name = 'latitude' if 'latitude' in rmse.dims else 'lat'
            lon_name = 'longitude' if 'longitude' in rmse.dims else 'lon'
            rmse_map = rmse.sel(
                **{lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)}
            ).sortby(lat_name)
            rmse_coarse = _maybe_coarsen(rmse_map, lat_name, lon_name, PLOT_CFG["rmse_coarsen_factor"])
            rmse_cache4[hour_val] = {
                "lat_name": lat_name,
                "lon_name": lon_name,
                "lats": rmse_coarse[lat_name].values,
                "lons": rmse_coarse[lon_name].values,
                "rmse_plot": rmse_coarse.values,
            }

        # Figure-specific norm for better contrast at low RMSE
        all_vals4 = np.concatenate([v["rmse_plot"][np.isfinite(v["rmse_plot"])] for v in rmse_cache4.values()])
        if all_vals4.size > 0:
            # True min/max across both hours for Figure 4
            vmin4 = float(np.nanmin(all_vals4))
            vmax4 = float(np.nanmax(all_vals4))
            norm4 = mcolors.PowerNorm(gamma=float(PLOT_CFG["rmse_gamma"]), vmin=vmin4, vmax=vmax4)
        else:
            vmin4, vmax4, norm4 = None, None, None

        # Custom orography colormap: white (sea) -> green -> brown
        orog_cmap4 = mcolors.LinearSegmentedColormap.from_list(
            "orog_white_green_brown",
            ["#ffffff", "#cfeccf", "#7fbf7b", "#b8860b", "#6b3e1e"]
        )
        orog_cmap4.set_under("#ffffff")

        for i, hour_val in enumerate(hours4):
            axh = fig4.add_subplot(gs4[0, i], projection=ccrs.PlateCarree())
            axh.set_extent(EUROPE_EXTENT, crs=ccrs.PlateCarree())

            # Orography-only background (white sea -> green -> brown)
            if orog_image is not None:
                axh.imshow(
                    orog_image,
                    origin='upper',
                    extent=[lon_min, lon_max, lat_min, lat_max],
                    cmap=orog_cmap4,
                    transform=ccrs.PlateCarree(),
                    vmin=0.1,
                    vmax=orog_vmax,
                    interpolation='nearest',
                    alpha=1.0,
                    zorder=0
                )

            cached = rmse_cache4[hour_val]
            lats = cached["lats"]
            lons = cached["lons"]
            rmse_plot = cached["rmse_plot"]
            hour_means4.append(float(np.nanmean(rmse_plot)))
            hour_mins4.append(float(np.nanmin(rmse_plot)))
            hour_maxs4.append(float(np.nanmax(rmse_plot)))

            lon_grid, lat_grid = np.meshgrid(lons, lats)
            stride = 2
            lon_scatter = lon_grid[::stride, ::stride].ravel()
            lat_scatter = lat_grid[::stride, ::stride].ravel()
            rmse_scatter = rmse_plot[::stride, ::stride].ravel()
            valid_idx = ~np.isnan(rmse_scatter)

            scatter_kwargs = dict(
                c=rmse_scatter[valid_idx],
                cmap=PLOT_CFG["rmse_cmap"],
                s=PLOT_CFG["rmse_size"],
                alpha=PLOT_CFG["rmse_alpha"],
                edgecolors=PLOT_CFG["rmse_edgecolor"],
                linewidths=0.5,
                transform=ccrs.PlateCarree(),
                zorder=5,
                marker='o',
            )
            if norm4 is not None:
                scatter_kwargs["norm"] = norm4
            else:
                scatter_kwargs["vmin"] = vmin4
                scatter_kwargs["vmax"] = vmax4

            sc4 = axh.scatter(lon_scatter[valid_idx], lat_scatter[valid_idx], **scatter_kwargs)

            axh.coastlines(linewidth=1.0, color='black', zorder=10)
            axh.add_feature(cfeature.BORDERS, linewidth=0.7, color='black', linestyle='-', zorder=10)
            gl = axh.gridlines(draw_labels=True, linestyle='--', linewidth=0.2, alpha=0.4, zorder=2)
            gl.top_labels = False
            gl.right_labels = False

            axh.set_title(
                f"{VAR_LABELS.get('2t', '2t')} RMSE at {hour_val:02d}:00 UTC",
                fontsize=11, fontweight='bold', pad=8
            )

            # Per-panel stats (same style as Figure 1)
            if valid_idx.any():
                mean_val = float(np.nanmean(rmse_plot))
                min_val = float(np.nanmin(rmse_plot))
                max_val = float(np.nanmax(rmse_plot))
                stats_text = f"Mean: {mean_val:.2f}°C\nMin: {min_val:.2f}°C\nMax: {max_val:.2f}°C"
                axh.text(
                    0.02, 0.98, stats_text,
                    transform=axh.transAxes, fontsize=8, va='top',
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.85), zorder=20
                )

        # Shared RMSE colorbar for fig4
        cax4 = fig4.add_axes([0.92, 0.20, 0.015, 0.60])
        fig4.colorbar(sc4, cax=cax4, orientation='vertical').set_label("RMSE (°C)")

        date_min, date_max, _ = _overall_ok_date_range(pairs_dict, VARIABLES)
        fig4.suptitle(
            f"RMSE Dots for {VAR_LABELS.get('2t', '2t')}: 00:00 vs 12:00 UTC | "
            f"AIFS–ERA5 paired dates: {date_min} to {date_max}",
            fontsize=12, fontweight='bold', y=0.98
        )
        fig4.subplots_adjust(right=0.90, bottom=0.36, top=0.86)

        # No bottom-left summary box for Figure 4

        # Orography colorbar (white sea -> green -> brown)
        if orog_image is not None:
            try:
                cbar_orog4 = fig4.colorbar(
                    plt.cm.ScalarMappable(norm=mcolors.Normalize(vmin=0.1, vmax=orog_vmax), cmap=orog_cmap4),
                    ax=fig4.axes,
                    orientation='horizontal',
                    shrink=0.7,
                    pad=0.08
                )
                cbar_orog4.set_label('Orography Height (m)', fontsize=9)
                cbar_orog4.ax.tick_params(labelsize=8)
            except Exception:
                pass

        fig4_path = str(RESULTS_DIR / 'fig04_rmse_2mtemp_00_12.png')
        fig4.savefig(fig4_path, dpi=140, bbox_inches='tight')
        print(f"✓ Figure 4 saved to: {fig4_path}")
        plt.show()
    except Exception as e:
        print(f"✗ Figure 4 failed: {type(e).__name__}: {e}")

    # --- Figure 5: RMSE distribution by lead time (boxplots) ---
    try:
        fig5 = plt.figure(figsize=(12, 6))
        ax5a = fig5.add_subplot(1, 2, 1)
        ax5b = fig5.add_subplot(1, 2, 2)

        def _rmse_by_step_distribution(var_key):
            csv_path = RMSE_OUT / f'pairs_manifest_{var_key}.csv'
            if not csv_path.exists():
                return {}
            df = pd.read_csv(csv_path)
            ok = df[df['status'] == 'ok']
            if ok.empty:
                return {}
            step_map = {}
            for _, row in ok.iterrows():
                res = compute_pair_rmse(
                    aifs_path=Path(row['aifs_path']),
                    era5_path=Path(row['era5_path']),
                    valid_dt=pd.to_datetime(row['valid_dt']).to_pydatetime(),
                    variable_key=var_key,
                    index_dir=INDEX_DIR,
                    step_hours=int(row['step']) if 'step' in row and pd.notna(row['step']) else None,
                    bbox=EUROPE_BBOX,
                )
                if res['status'] != 'ok':
                    continue
                step = int(row['step']) if pd.notna(row['step']) else None
                if step is None:
                    continue
                step_map.setdefault(step, []).append(float(res['rmse_mean']))
            return step_map

        for ax, var_key in [(ax5a, "2t"), (ax5b, "t500")]:
            step_map = _rmse_by_step_distribution(var_key)
            if not step_map:
                ax.text(0.5, 0.5, f'No data for {var_key}', ha='center', va='center')
                ax.axis('off')
                continue
            steps = sorted(step_map.keys())
            data = [step_map[s] for s in steps]
            ax.boxplot(
                data,
                positions=steps,
                widths=2.5,
                patch_artist=True,
                boxprops=dict(facecolor="#d9d9d9", edgecolor="black"),
                medianprops=dict(color="black"),
                whiskerprops=dict(color="black"),
                capprops=dict(color="black"),
                showfliers=False,
            )
            ax.set_title(f"{VAR_LABELS.get(var_key, var_key)} RMSE Distribution by Lead Time", fontsize=11, fontweight='bold')
            ax.set_xlabel("Lead time (hours)")
            ax.set_ylabel("RMSE (°C)")
            ax.set_xticks(steps)
            ax.grid(True, linestyle='--', alpha=0.3)

        fig5.tight_layout()
        fig5_path = str(RESULTS_DIR / 'fig05_rmse_by_leadtime.png')
        fig5.savefig(fig5_path, dpi=140, bbox_inches='tight')
        print(f"✓ Figure 5 saved to: {fig5_path}")
        plt.show()
    except Exception as e:
        print(f"✗ Figure 5 failed: {type(e).__name__}: {e}")

    # --- Figure 6: RMSE vs land-sea mask (map + distributions) ---
    try:
        if lsm_da is None:
            raise ValueError("Land-sea mask not available. Download era5_land_sea_mask.nc first.")

        var_key = PLOT_CFG["lsm_var"]
        step_target = float(PLOT_CFG["lsm_step_hours"])

        ds_step = load_rmse_by_step(var_key)
        rmse = ds_step["rmse"]

        lat_name = None
        lon_name = None
        for dim in rmse.dims:
            if dim in ("latitude", "lat"):
                lat_name = dim
            elif dim in ("longitude", "lon"):
                lon_name = dim
        if lat_name is None or lon_name is None:
            raise ValueError("RMSE dataset missing latitude/longitude dimensions")

        if "step" not in rmse.dims:
            raise ValueError("RMSE dataset missing step dimension")

        step_vals = rmse["step"].values.astype(float)
        if step_vals.size == 0:
            raise ValueError("RMSE dataset has no steps")
        step_idx = int(np.nanargmin(np.abs(step_vals - step_target)))
        step_used = float(step_vals[step_idx])

        lon_min, lon_max, lat_min, lat_max = EUROPE_EXTENT
        rmse_step = rmse.isel(step=step_idx).sel(
            **{lat_name: slice(lat_max, lat_min), lon_name: slice(lon_min, lon_max)}
        ).sortby(lat_name)

        rmse_vals = np.asarray(rmse_step.values)
        if np.all(np.isnan(rmse_vals)):
            raise ValueError("RMSE step map is all NaN")

        # Regrid LSM onto RMSE grid (nearest)
        lsm_on_rmse = lsm_da.interp(
            **{
                lsm_lat_name: rmse_step[lat_name].values,
                lsm_lon_name: rmse_step[lon_name].values,
            },
            method="nearest",
        )
        lsm_vals = np.asarray(lsm_on_rmse.values)

        land_mask = lsm_vals >= 0.5
        sea_mask = lsm_vals < 0.5
        valid_mask = ~np.isnan(rmse_vals)

        land_rmse = rmse_vals[land_mask & valid_mask]
        sea_rmse = rmse_vals[sea_mask & valid_mask]

        fig6 = plt.figure(figsize=(12, 6.5))
        gs6 = gridspec.GridSpec(1, 2, width_ratios=[1.3, 1.0], wspace=0.25)
        ax6_map = fig6.add_subplot(gs6[0, 0], projection=ccrs.PlateCarree())
        ax6_dist = fig6.add_subplot(gs6[0, 1])

        ax6_map.set_extent(EUROPE_EXTENT, crs=ccrs.PlateCarree())

        # Land-sea background
        lsm_cmap = ListedColormap([PLOT_CFG["lsm_sea_color"], PLOT_CFG["lsm_land_color"]])
        ax6_map.imshow(
            lsm_vals,
            origin="upper",
            extent=[lon_min, lon_max, lat_min, lat_max],
            cmap=lsm_cmap,
            vmin=0.0,
            vmax=1.0,
            transform=ccrs.PlateCarree(),
            interpolation="nearest",
            alpha=1.0,
            zorder=0,
        )

        # RMSE dots over land/sea: keep native grid to match land/sea boxplots
        # (no coarsening here to avoid mismatched classification vs plotted values)
        rmse_vals = np.asarray(rmse_step.values)
        lon_grid, lat_grid = np.meshgrid(
            rmse_step[lon_name].values,
            rmse_step[lat_name].values
        )
        rmse_scatter = rmse_vals.ravel()
        lon_scatter = lon_grid.ravel()
        lat_scatter = lat_grid.ravel()
        ok = ~np.isnan(rmse_scatter)

        vmin6 = float(np.nanmin(rmse_vals)) if PLOT_CFG["rmse_vmin"] is None else float(PLOT_CFG["rmse_vmin"])
        vmax6 = float(np.nanmax(rmse_vals)) if PLOT_CFG["rmse_vmax"] is None else float(PLOT_CFG["rmse_vmax"])
        if PLOT_CFG["rmse_norm"] == "power":
            norm6 = mcolors.PowerNorm(gamma=float(PLOT_CFG["rmse_gamma"]), vmin=vmin6, vmax=vmax6)
        else:
            norm6 = mcolors.Normalize(vmin=vmin6, vmax=vmax6)

        sc6 = ax6_map.scatter(
            lon_scatter[ok],
            lat_scatter[ok],
            c=rmse_scatter[ok],
            cmap=PLOT_CFG["rmse_cmap"],
            s=PLOT_CFG["rmse_size"],
            alpha=PLOT_CFG["rmse_alpha"],
            edgecolors=PLOT_CFG["rmse_edgecolor"],
            linewidths=0.5,
            transform=ccrs.PlateCarree(),
            zorder=5,
            norm=norm6,
        )

        ax6_map.coastlines(linewidth=1.0, color="black", zorder=10)
        ax6_map.add_feature(cfeature.BORDERS, linewidth=0.7, color="black", linestyle="-", zorder=10)
        gl = ax6_map.gridlines(draw_labels=True, linestyle="--", linewidth=0.2, alpha=0.4, zorder=2)
        gl.top_labels = False
        gl.right_labels = False

        # Land/sea legend
        land_patch = mpatches.Patch(color=PLOT_CFG["lsm_land_color"], label="Land")
        sea_patch = mpatches.Patch(color=PLOT_CFG["lsm_sea_color"], label="Sea")
        ax6_map.legend(
            handles=[land_patch, sea_patch],
            loc="lower left",
            frameon=True,
            framealpha=0.85,
            fontsize=8
        )

        # Distribution plot (land vs sea)
        # Note: boxplots use IQR whiskers (and hide outliers), while the colorbar shows true min/max.
        data = [sea_rmse, land_rmse]
        labels = ["Sea", "Land"]
        ax6_dist.boxplot(
            data,
            labels=labels,
            patch_artist=True,
            boxprops=dict(facecolor="#d9d9d9", edgecolor="black"),
            medianprops=dict(color="black"),
            whiskerprops=dict(color="black"),
            capprops=dict(color="black"),
            showfliers=False,
        )
        ax6_dist.set_title("RMSE Distribution by Land/Sea", fontsize=11, fontweight="bold")
        ax6_dist.set_ylabel("RMSE (°C)")
        ax6_dist.grid(True, linestyle="--", alpha=0.3)

        info = (
            f"Variable: {var_key}\n"
            f"Step: {step_used:.0f} h\n"
            f"Sea mean: {np.nanmean(sea_rmse):.2f}°C (n={sea_rmse.size})\n"
            f"Land mean: {np.nanmean(land_rmse):.2f}°C (n={land_rmse.size})"
        )
        ax6_map.text(
            0.02, 0.98, info,
            transform=ax6_map.transAxes, fontsize=8, va="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85), zorder=20
        )

        ax6_map.set_title(
            f"RMSE over Land/Sea Mask at {step_used:.0f}h Lead Time",
            fontsize=12, fontweight="bold", pad=10
        )

        # RMSE colorbar
        cax6 = fig6.add_axes([0.92, 0.20, 0.015, 0.60])
        fig6.colorbar(sc6, cax=cax6, orientation="vertical").set_label("RMSE (°C)")

        fig6_path = str(RESULTS_DIR / 'fig06_rmse_land_sea.png')
        fig6.savefig(fig6_path, dpi=140, bbox_inches="tight")
        print(f"✓ Figure 6 saved to: {fig6_path}")
        plt.show()
    except Exception as e:
        print(f"✗ Figure 6 failed: {type(e).__name__}: {e}")
    
except Exception as e:
    print(f"\n✗ Figure 1 failed: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    plt.close('all')
