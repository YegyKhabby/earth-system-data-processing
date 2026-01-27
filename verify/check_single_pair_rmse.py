#!/usr/bin/env python3
"""
Verification script to debug RMSE calculation for a single AIFS-ERA5 pair.
Tests time extraction and RMSE computation step-by-step.
"""

import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

# Add scripts directory to path
REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / 'data_access' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

import xarray as xr

# Import RMSE functions
from aifs_era5_rmse import (
    compute_pair_rmse,
    VARIABLE_CONFIG,
    _open_aifs_dataset,
    _open_era5_dataset,
    _select_aifs_field,
    _select_aifs_time,
    _select_era5_field,
    _select_time,
    align_aifs_lon_to_era5,
)

def check_pair(aifs_path: str, era5_path: str, valid_dt_str: str, variable: str = "2t"):
    """Check a single pair with detailed output."""
    
    print("\n" + "="*70)
    print(f"RMSE Verification for Single Pair: {variable}")
    print("="*70)
    
    aifs_path = Path(aifs_path)
    era5_path = Path(era5_path)
    valid_dt = pd.to_datetime(valid_dt_str)
    
    print(f"\n[INPUT]")
    print(f"  AIFS file: {aifs_path.name}")
    print(f"  AIFS exists: {aifs_path.exists()}")
    print(f"  ERA5 file: {era5_path.name}")
    print(f"  ERA5 exists: {era5_path.exists()}")
    print(f"  Target valid time: {valid_dt}")
    print(f"  Variable: {variable}")
    
    # Get config
    cfg = VARIABLE_CONFIG[variable]
    INDEX_DIR = REPO_ROOT / 'data' / 'rmse_outputs' / 'cfgrib_index'
    
    # Step 1: Open AIFS
    print(f"\n[STEP 1: Open AIFS]")
    try:
        ds_aifs = _open_aifs_dataset(aifs_path, cfg["aifs"], index_dir=INDEX_DIR)
        print(f"  ✓ AIFS opened")
        print(f"    Dimensions: {dict(ds_aifs.dims)}")
        print(f"    Coordinates: {list(ds_aifs.coords)}")
        print(f"    Variables: {list(ds_aifs.data_vars)}")
    except Exception as e:
        print(f"  ✗ Failed to open AIFS: {e}")
        return
    
    # Step 2: Open ERA5
    print(f"\n[STEP 2: Open ERA5]")
    try:
        ds_era5 = _open_era5_dataset(era5_path)
        print(f"  ✓ ERA5 opened")
        print(f"    Dimensions: {dict(ds_era5.dims)}")
        print(f"    Coordinates: {list(ds_era5.coords)}")
        print(f"    Variables: {list(ds_era5.data_vars)}")
        
        # Show ERA5 time info
        if "time" in ds_era5.coords:
            times = pd.to_datetime(ds_era5["time"].values)
            print(f"    Time coordinate: {list(times)}")
            print(f"    Hours in file: {sorted(set(times.hour))}")
        elif "valid_time" in ds_era5.coords:
            times = pd.to_datetime(ds_era5["valid_time"].values)
            print(f"    Valid_time coordinate: {list(times)}")
            print(f"    Hours in file: {sorted(set(times.hour))}")
        else:
            print(f"    WARNING: No time or valid_time coordinate!")
    except Exception as e:
        print(f"  ✗ Failed to open ERA5: {e}")
        return
    
    # Step 3: Align AIFS longitude
    print(f"\n[STEP 3: Align AIFS longitude to ERA5]")
    try:
        ds_aifs_aligned = align_aifs_lon_to_era5(ds_aifs, ds_era5)
        print(f"  ✓ Alignment complete")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        ds_aifs_aligned = ds_aifs
    
    # Step 4: Select AIFS field
    print(f"\n[STEP 4: Select AIFS field ({cfg['aifs']['shortName']})]")
    try:
        da_aifs = _select_aifs_field(ds_aifs_aligned, cfg["aifs"])
        print(f"  ✓ Field selected")
        print(f"    Shape: {da_aifs.shape}")
        print(f"    Coordinates: {list(da_aifs.coords)}")
        print(f"    Dimensions: {da_aifs.dims}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return
    
    # Step 5: Select AIFS time
    print(f"\n[STEP 5: Select AIFS time slice (valid_dt={valid_dt})]")
    try:
        da_aifs_time = _select_aifs_time(da_aifs, valid_dt=valid_dt, step_hours=None)
        print(f"  ✓ Time selected")
        print(f"    Shape: {da_aifs_time.shape}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return
    
    # Step 6: Select ERA5 field
    print(f"\n[STEP 6: Select ERA5 field ({cfg['era5']['var']})]")
    try:
        da_era5 = _select_era5_field(ds_era5, cfg["era5"])
        print(f"  ✓ Field selected")
        print(f"    Shape: {da_era5.shape}")
        print(f"    Coordinates: {list(da_era5.coords)}")
        print(f"    Dimensions: {da_era5.dims}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return
    
    # Step 7: Select ERA5 time - THIS IS CRITICAL
    print(f"\n[STEP 7: Select ERA5 time slice (valid_dt={valid_dt})]")
    try:
        print(f"  Looking for time={valid_dt.hour}:00 in ERA5 file...")
        
        # Show what times are available
        if "valid_time" in da_era5.coords:
            avail_times = pd.to_datetime(da_era5["valid_time"].values)
            print(f"  Available times in ERA5:")
            for t in avail_times:
                print(f"    - {t} (hour={t.hour})")
        elif "time" in da_era5.coords:
            avail_times = pd.to_datetime(da_era5["time"].values)
            print(f"  Available times in ERA5:")
            for t in avail_times:
                print(f"    - {t} (hour={t.hour})")
        
        da_era5_time = _select_time(da_era5, valid_dt)
        print(f"  ✓ Time selected")
        print(f"    Shape: {da_era5_time.shape}")
    except Exception as e:
        print(f"  ✗ Failed to select ERA5 time: {e}")
        print(f"  This is a CRITICAL ERROR - the ERA5 time extraction failed!")
        return
    
    # Step 8: Convert to Celsius
    print(f"\n[STEP 8: Convert to Celsius]")
    try:
        da_aifs_c = da_aifs_time - 273.15
        da_era5_c = da_era5_time - 273.15
        print(f"  ✓ Conversion complete")
        print(f"    AIFS: min={float(da_aifs_c.min()):.2f}°C, max={float(da_aifs_c.max()):.2f}°C, mean={float(da_aifs_c.mean()):.2f}°C")
        print(f"    ERA5: min={float(da_era5_c.min()):.2f}°C, max={float(da_era5_c.max()):.2f}°C, mean={float(da_era5_c.mean()):.2f}°C")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return
    
    # Step 9: Compute error
    print(f"\n[STEP 9: Compute error (AIFS - ERA5)]")
    try:
        err = da_aifs_c - da_era5_c
        print(f"  ✓ Error computed")
        print(f"    Shape: {err.shape}")
        print(f"    Min error: {float(err.min()):.4f}°C")
        print(f"    Max error: {float(err.max()):.4f}°C")
        print(f"    Mean error: {float(err.mean()):.4f}°C")
        print(f"    Std error: {float(err.std()):.4f}°C")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return
    
    # Step 10: Compute RMSE
    print(f"\n[STEP 10: Compute RMSE]")
    try:
        rmse = float(np.sqrt(np.nanmean((err.values) ** 2)))
        n_valid = np.isfinite(err.values).sum()
        n_total = err.size
        print(f"  ✓ RMSE computed")
        print(f"    RMSE: {rmse:.4f}°C")
        print(f"    Valid points: {n_valid} / {n_total}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return
    
    # Step 11: Use built-in function
    print(f"\n[STEP 11: Verify with compute_pair_rmse function]")
    try:
        result = compute_pair_rmse(
            aifs_path=aifs_path,
            era5_path=era5_path,
            valid_dt=valid_dt,
            variable_key=variable,
            index_dir=INDEX_DIR,
            step_hours=None,
        )
        print(f"  Result status: {result['status']}")
        if result['status'] == 'ok':
            print(f"  ✓ RMSE computed: {result['rmse_mean']:.4f}°C")
        else:
            print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
    except Exception as e:
        print(f"  ✗ Failed: {e}")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    # Test pair from pairs_manifest_2t.csv
    # First row: 2026-01-19 06:00:00
    aifs_path = "/Users/yeganehkhabbazian/Projects/Earth_System/earth-system-data-processing/data/aifs/raw/2026/01/19/aifs-single_20260119_00_sfc_2t-msl-10u-10v_step006_0p25.grib2"
    era5_path = "/Users/yeganehkhabbazian/Projects/Earth_System/earth-system-data-processing/data/era5/archive/real/2026/01/era5_2m_temperature_20260119.nc"
    valid_dt = "2026-01-19 06:00:00"
    
    check_pair(aifs_path, era5_path, valid_dt, variable="2t")
    
    print("\n\n")
    print("="*70)
    print("Testing another pair: 2026-01-20 12:00")
    print("="*70)
    
    # Test t500 pair
    aifs_path_t500 = "/Users/yeganehkhabbazian/Projects/Earth_System/earth-system-data-processing/data/aifs/raw/2026/01/19/aifs-single_20260119_00_pl_t_500hPa_step036_0p25.grib2"
    era5_path_t500 = "/Users/yeganehkhabbazian/Projects/Earth_System/earth-system-data-processing/data/era5/archive/real/2026/01/era5_temperature_pl500hPa_20260120.nc"
    valid_dt_t500 = "2026-01-20 12:00:00"
    
    check_pair(aifs_path_t500, era5_path_t500, valid_dt_t500, variable="t500")
