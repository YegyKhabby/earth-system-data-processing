#!/usr/bin/env python3
"""
Script to compute RMSE for all pairs and save to CSV files.
This should have been called in the notebook but wasn't.
"""

import sys
from pathlib import Path

import pandas as pd

# Add scripts directory to path
REPO_ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = REPO_ROOT / 'data_access' / 'scripts'
sys.path.insert(0, str(SCRIPTS_DIR))

from aifs_era5_rmse import (
    compute_rmse_for_pairs,
    compute_rmse_by_step_by_day,
)

def compute_rmse_for_all_pairs():
    """Compute RMSE for all pairs and save CSVs."""
    
    RMSE_OUT = REPO_ROOT / 'data' / 'rmse_outputs'
    INDEX_DIR = RMSE_OUT / 'cfgrib_index'
    
    VARIABLES = ['2t', 't500']
    
    print("\n" + "="*70)
    print("Computing RMSE for all pairs")
    print("="*70)
    
    for var in VARIABLES:
        print(f"\n[{var}] Processing...")
        
        # Load pairs manifest
        pairs_file = RMSE_OUT / f'pairs_manifest_{var}.csv'
        if not pairs_file.exists():
            print(f"  ⚠️  Pairs manifest not found: {pairs_file}")
            continue
        
        pairs_df = pd.read_csv(pairs_file)
        pairs_df['valid_dt'] = pd.to_datetime(pairs_df['valid_dt'])
        pairs_df['init_dt'] = pd.to_datetime(pairs_df['init_dt'])
        
        print(f"  Total pairs: {len(pairs_df)}")
        print(f"  OK pairs: {len(pairs_df[pairs_df['status'] == 'ok'])}")
        
        # Compute RMSE for all pairs
        print(f"  Computing RMSE...")
        pairs_manifest, rmse_by_step = compute_rmse_for_pairs(
            pairs_df=pairs_df,
            variable_key=var,
            index_dir=INDEX_DIR,
        )
        
        # Save pairs manifest with RMSE
        manifest_out = RMSE_OUT / f'pairs_manifest_with_rmse_{var}.csv'
        pairs_manifest.to_csv(manifest_out, index=False)
        print(f"  ✓ Saved: {manifest_out.name} ({len(pairs_manifest)} rows)")
        
        # Save RMSE by step
        rmse_by_step_out = RMSE_OUT / f'rmse_by_step_{var}.csv'
        rmse_by_step.to_csv(rmse_by_step_out, index=False)
        print(f"  ✓ Saved: {rmse_by_step_out.name}")
        if not rmse_by_step.empty:
            print(f"    Rows: {len(rmse_by_step)}")
            print(rmse_by_step)
        else:
            print(f"    WARNING: Empty output!")
        
        # Compute RMSE by step and by day
        print(f"  Computing RMSE by step and day...")
        rmse_by_step_by_day = compute_rmse_by_step_by_day(pairs_manifest)
        
        rmse_by_step_by_day_out = RMSE_OUT / f'rmse_by_step_by_day_{var}.csv'
        rmse_by_step_by_day.to_csv(rmse_by_step_by_day_out, index=False)
        print(f"  ✓ Saved: {rmse_by_step_by_day_out.name}")
        if not rmse_by_step_by_day.empty:
            print(f"    Rows: {len(rmse_by_step_by_day)}")
            print(rmse_by_step_by_day)
        else:
            print(f"    WARNING: Empty output!")
        
        # Summary
        ok_pairs = pairs_manifest[pairs_manifest['status'] == 'ok']
        if not ok_pairs.empty:
            mean_rmse = ok_pairs['rmse_mean'].mean()
            print(f"\n  Summary: {len(ok_pairs)} OK pairs, Mean RMSE = {mean_rmse:.4f}°C")
        else:
            print(f"\n  WARNING: No OK pairs found!")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    compute_rmse_for_all_pairs()
