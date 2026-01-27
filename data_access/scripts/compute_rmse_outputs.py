"""
Compute and save RMSE outputs in multiple aggregations.

This script generates spatially-aware NetCDF files suitable for plotting maps and
time series. Outputs include:
- rmse_by_step_<var>.nc: RMSE aggregated by lead step (6h, 12h, 18h, etc.)
- rmse_by_day_<var>.nc: RMSE aggregated by date
- rmse_by_hour_<var>.nc: RMSE aggregated by valid hour (0, 6, 12, 18 UTC)

Each file contains:
- Gridded RMSE values (lat, lon)
- Mean RMSE (scalar)
- Count of samples per grid cell
"""

import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_rmse_outputs(
    pairs_2t,
    pairs_t500,
    compute_rmse_for_pairs_func,
    index_dir,
    output_dir,
    bbox=None,
    variables=None,
):
    """
    Orchestrate RMSE output generation for multiple aggregations.
    
    Parameters
    ----------
    pairs_2t : pd.DataFrame
        Pairs manifest for 2t variable (with status='ok' rows)
    pairs_t500 : pd.DataFrame
        Pairs manifest for t500 variable (with status='ok' rows)
    compute_rmse_for_pairs_func : callable
        Function with signature: compute_pair_rmse(aifs_path, era5_path, valid_dt, 
        variable_key, index_dir, step_hours, bbox) -> dict with keys 'status', 'err'
        where 'err' is an xarray.DataArray with lat/lon coordinates.
    index_dir : Path
        Directory for cfgrib index cache
    output_dir : Path
        Output directory for NetCDF files
    bbox : tuple, optional
        (lon_min, lon_max, lat_min, lat_max) for cropping
    variables : list, optional
        Variables to process. Default: ['2t', 't500']
    """
    if variables is None:
        variables = ['2t', 't500']
    
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    pairs_dict = {'2t': pairs_2t, 't500': pairs_t500}
    
    for var in variables:
        pairs = pairs_dict.get(var)
        if pairs is None or len(pairs) == 0:
            logger.warning(f"No pairs for {var}, skipping")
            continue
        
        ok_pairs = pairs[pairs['status'] == 'ok']
        if len(ok_pairs) == 0:
            logger.warning(f"No OK pairs for {var}, skipping")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {var}: {len(ok_pairs)} OK pairs")
        logger.info(f"{'='*60}")
        
        # Compute per-pair squared-error grids
        logger.info(f"Computing per-pair squared-error grids...")
        se_grids = _compute_per_pair_grids(
            ok_pairs, var, compute_rmse_for_pairs_func, index_dir, bbox
        )
        
        if se_grids is None or len(se_grids) == 0:
            logger.warning(f"Failed to compute SE grids for {var}")
            continue
        
        # Aggregate by step
        logger.info(f"Aggregating by lead step...")
        _save_rmse_by_step(se_grids, ok_pairs, var, output_dir)
        
        # Aggregate by day
        logger.info(f"Aggregating by date...")
        _save_rmse_by_day(se_grids, ok_pairs, var, output_dir)
        
        # Aggregate by hour
        logger.info(f"Aggregating by valid hour...")
        _save_rmse_by_hour(se_grids, ok_pairs, var, output_dir)
        
        logger.info(f"✓ Completed {var}")


def _compute_per_pair_grids(pairs, var, compute_rmse_func, index_dir, bbox):
    """
    Compute squared-error grids for each pair.
    
    Returns
    -------
    list of dict
        Each dict has keys: 'se' (squared error DataArray), 'valid_dt', 'step', 'date', 'hour'
    """
    se_grids = []
    
    for idx, row in pairs.iterrows():
        try:
            result = compute_rmse_func(
                aifs_path=Path(row['aifs_path']),
                era5_path=Path(row['era5_path']),
                valid_dt=row['valid_dt'],
                variable_key=var,
                index_dir=Path(index_dir),
                step_hours=int(row['step']) if 'step' in row else None,
                bbox=bbox,
            )
            
            if result['status'] != 'ok':
                logger.debug(f"  Pair {idx} failed: {result.get('error')}")
                continue
            
            # Extract error grid (xarray DataArray with coords already attached)
            err = result.get('err')
            if err is None:
                logger.debug(f"  Pair {idx} has no error grid")
                continue
            
            # err is already an xarray DataArray with coordinates
            # Squeeze extra singleton dims (time, step) but keep spatial dims
            err = err.squeeze(drop=True)
            
            # Identify spatial dimensions (could be 'lat'/'lon' or 'latitude'/'longitude')
            spatial_dims = [d for d in err.dims if d in ('latitude', 'lat', 'longitude', 'lon')]
            
            # Must have exactly 2 spatial dimensions
            if len(spatial_dims) != 2:
                logger.debug(f"  Pair {idx}: expected 2 spatial dims, got {spatial_dims}")
                continue
            
            # Reduce over non-spatial dimensions (should be none after squeeze, but be safe)
            non_spatial_dims = [d for d in err.dims if d not in spatial_dims]
            if len(non_spatial_dims) > 0:
                # Average over non-spatial dims before squaring
                err = err.mean(dim=non_spatial_dims)
            
            # Compute squared error: se = err^2 (for per-grid-cell aggregation later)
            se_da = err**2
            
            # Standardize coordinate names: rename lat/lon -> latitude/longitude
            dim_mapping = {}
            for old_dim in se_da.dims:
                if old_dim == 'lat':
                    dim_mapping['lat'] = 'latitude'
                elif old_dim == 'lon':
                    dim_mapping['lon'] = 'longitude'
            if dim_mapping:
                se_da = se_da.rename(dim_mapping)
            
            se_grids.append({
                'se': se_da,
                'valid_dt': pd.Timestamp(row['valid_dt']),
                'step': int(row['step']) if 'step' in row else None,
                'date': pd.Timestamp(row['valid_dt']).date(),
                'hour': pd.Timestamp(row['valid_dt']).hour,
            })
            
            logger.info(f"  ✓ Pair {idx+1}/{len(pairs)}: valid_dt={row['valid_dt']}, step={row.get('step', 'N/A')}h, se_shape={se_da.shape}")
        
        except Exception as e:
            logger.error(f"  Pair {idx} error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    logger.info(f"  Successfully computed {len(se_grids)}/{len(pairs)} pairs")
    return se_grids


def _save_rmse_by_step(se_grids, pairs, var, output_dir):
    """
    Aggregate RMSE by lead step (6h, 12h, 18h, 24h, etc.).
    
    Aggregates squared errors per step, then computes: rmse = sqrt(sum_sq / count)
    """
    # Group by step
    by_step = {}
    for grid_dict in se_grids:
        step = grid_dict['step']
        if step not in by_step:
            by_step[step] = []
        by_step[step].append(grid_dict['se'])
    
    # Compute RMSE and count for each step
    steps_data = []
    for step in sorted(by_step.keys()):
        se_list = by_step[step]
        
        # Aggregate squared errors
        stacked = xr.concat(se_list, dim='sample')
        sum_sq = stacked.sum(dim='sample', skipna=True)
        count = stacked.notnull().sum(dim='sample')
        
        # RMSE = sqrt(sum_sq / count) where count > 0
        rmse = np.sqrt(sum_sq / count.where(count > 0, other=np.nan))
        
        steps_data.append({
            'step': step,
            'rmse': rmse,
            'count': count,
        })
    
    # Create output dataset
    if len(steps_data) > 0:
        # Use first grid as template for coordinates
        template = steps_data[0]['rmse']
        
        rmse_cat = xr.concat([d['rmse'] for d in steps_data], dim='step').assign_coords(
            step=[d['step'] for d in steps_data]
        )
        count_cat = xr.concat([d['count'] for d in steps_data], dim='step').assign_coords(
            step=[d['step'] for d in steps_data]
        )

        ds = xr.Dataset(
            {
                'rmse': rmse_cat,
                'sample_count': count_cat,
            }
        )
        
        # Add attributes
        ds.attrs['title'] = f'RMSE by lead step ({var})'
        ds.attrs['variable'] = var
        ds.attrs['created'] = datetime.now().isoformat()
        ds.attrs['n_pairs'] = len(se_grids)
        
        ds['rmse'].attrs['units'] = '°C'
        ds['rmse'].attrs['long_name'] = 'Root mean square error by lead step'
        ds['sample_count'].attrs['long_name'] = 'Number of valid samples per grid cell'
        
        # Quick sanity checks
        try:
            nan_frac = float(np.isnan(ds['rmse']).sum()) / ds['rmse'].size
            count_min = float(ds['sample_count'].min())
            count_max = float(ds['sample_count'].max())
            if nan_frac == 1.0 or np.isnan(count_min) or np.isnan(count_max):
                logger.warning(f"RMSE by step appears invalid: nan_frac={nan_frac:.2%}, count_min={count_min}, count_max={count_max}")
        except Exception:
            pass

        # Save
        output_file = output_dir / f'rmse_by_step_{var}.nc'
        ds.to_netcdf(output_file)
        logger.info(f"  ✓ Saved: {output_file.name}")
        
        # Also create summary CSV
        summary = []
        for step in sorted(by_step.keys()):
            se_list = by_step[step]
            stacked = xr.concat(se_list, dim='sample')
            count = stacked.notnull().sum(dim='sample')
            sum_sq = stacked.sum(dim='sample', skipna=True)
            global_rmse = float(np.sqrt(sum_sq / count.where(count > 0)).mean().values)
            n_samples = len(se_list)
            summary.append({'step': step, 'rmse_mean': global_rmse, 'n_pairs': n_samples})
        
        summary_df = pd.DataFrame(summary)
        summary_csv = output_dir / f'rmse_by_step_{var}.csv'
        summary_df.to_csv(summary_csv, index=False)
        logger.info(f"  ✓ Saved summary: {summary_csv.name}")


def _save_rmse_by_day(se_grids, pairs, var, output_dir):
    """
    Aggregate RMSE by date.
    
    Aggregates squared errors per date, then computes: rmse = sqrt(sum_sq / count)
    """
    # Group by date
    by_date = {}
    for grid_dict in se_grids:
        date = grid_dict['date']
        if date not in by_date:
            by_date[date] = []
        by_date[date].append(grid_dict['se'])
    
    # Compute RMSE and count for each date
    dates_data = []
    for date in sorted(by_date.keys()):
        se_list = by_date[date]
        
        # Aggregate squared errors
        stacked = xr.concat(se_list, dim='sample')
        sum_sq = stacked.sum(dim='sample', skipna=True)
        count = stacked.notnull().sum(dim='sample')
        
        # RMSE = sqrt(sum_sq / count) where count > 0
        rmse = np.sqrt(sum_sq / count.where(count > 0, other=np.nan))
        
        dates_data.append({
            'date': date,
            'rmse': rmse,
            'count': count,
        })
    
    # Create output dataset
    if len(dates_data) > 0:
        template = dates_data[0]['rmse']
        
        rmse_cat = xr.concat([d['rmse'] for d in dates_data], dim='date').assign_coords(
            date=pd.DatetimeIndex([pd.Timestamp(d['date']) for d in dates_data])
        )
        count_cat = xr.concat([d['count'] for d in dates_data], dim='date').assign_coords(
            date=pd.DatetimeIndex([pd.Timestamp(d['date']) for d in dates_data])
        )

        ds = xr.Dataset(
            {
                'rmse': rmse_cat,
                'sample_count': count_cat,
            }
        )
        
        ds.attrs['title'] = f'RMSE by date ({var})'
        ds.attrs['variable'] = var
        ds.attrs['created'] = datetime.now().isoformat()
        ds.attrs['n_pairs'] = len(se_grids)
        
        ds['rmse'].attrs['units'] = '°C'
        ds['rmse'].attrs['long_name'] = 'Root mean square error by date'
        ds['sample_count'].attrs['long_name'] = 'Number of valid samples per grid cell'
        
        # Quick sanity checks
        try:
            nan_frac = float(np.isnan(ds['rmse']).sum()) / ds['rmse'].size
            count_min = float(ds['sample_count'].min())
            count_max = float(ds['sample_count'].max())
            if nan_frac == 1.0 or np.isnan(count_min) or np.isnan(count_max):
                logger.warning(f"RMSE by date appears invalid: nan_frac={nan_frac:.2%}, count_min={count_min}, count_max={count_max}")
        except Exception:
            pass

        # Save
        output_file = output_dir / f'rmse_by_day_{var}.nc'
        ds.to_netcdf(output_file)
        logger.info(f"  ✓ Saved: {output_file.name}")
        
        # Summary CSV
        summary = []
        for date in sorted(by_date.keys()):
            se_list = by_date[date]
            stacked = xr.concat(se_list, dim='sample')
            count = stacked.notnull().sum(dim='sample')
            sum_sq = stacked.sum(dim='sample', skipna=True)
            global_rmse = float(np.sqrt(sum_sq / count.where(count > 0)).mean().values)
            n_samples = len(se_list)
            summary.append({'date': date, 'rmse_mean': global_rmse, 'n_pairs': n_samples})
        
        summary_df = pd.DataFrame(summary)
        summary_csv = output_dir / f'rmse_by_day_{var}.csv'
        summary_df.to_csv(summary_csv, index=False)
        logger.info(f"  ✓ Saved summary: {summary_csv.name}")


def _save_rmse_by_hour(se_grids, pairs, var, output_dir):
    """
    Aggregate RMSE by valid hour (0, 6, 12, 18 UTC).
    
    Aggregates squared errors per hour, then computes: rmse = sqrt(sum_sq / count)
    """
    # Group by hour
    by_hour = {}
    for grid_dict in se_grids:
        hour = grid_dict['hour']
        if hour not in by_hour:
            by_hour[hour] = []
        by_hour[hour].append(grid_dict['se'])
    
    # Compute RMSE and count for each hour
    hours_data = []
    for hour in sorted(by_hour.keys()):
        se_list = by_hour[hour]
        
        # Aggregate squared errors
        stacked = xr.concat(se_list, dim='sample')
        sum_sq = stacked.sum(dim='sample', skipna=True)
        count = stacked.notnull().sum(dim='sample')
        
        # RMSE = sqrt(sum_sq / count) where count > 0
        rmse = np.sqrt(sum_sq / count.where(count > 0, other=np.nan))
        
        hours_data.append({
            'hour': hour,
            'rmse': rmse,
            'count': count,
        })
    
    # Create output dataset
    if len(hours_data) > 0:
        template = hours_data[0]['rmse']
        
        rmse_cat = xr.concat([d['rmse'] for d in hours_data], dim='hour').assign_coords(
            hour=[d['hour'] for d in hours_data]
        )
        count_cat = xr.concat([d['count'] for d in hours_data], dim='hour').assign_coords(
            hour=[d['hour'] for d in hours_data]
        )

        ds = xr.Dataset(
            {
                'rmse': rmse_cat,
                'sample_count': count_cat,
            }
        )
        
        ds.attrs['title'] = f'RMSE by valid hour ({var})'
        ds.attrs['variable'] = var
        ds.attrs['created'] = datetime.now().isoformat()
        ds.attrs['n_pairs'] = len(se_grids)
        ds.attrs['description'] = 'RMSE aggregated by valid hour (UTC). Use for comparing 6am vs 12pm vs 6pm, etc.'
        
        ds['rmse'].attrs['units'] = '°C'
        ds['rmse'].attrs['long_name'] = 'Root mean square error by valid hour'
        ds['sample_count'].attrs['long_name'] = 'Number of valid samples per grid cell'
        
        # Quick sanity checks
        try:
            nan_frac = float(np.isnan(ds['rmse']).sum()) / ds['rmse'].size
            count_min = float(ds['sample_count'].min())
            count_max = float(ds['sample_count'].max())
            if nan_frac == 1.0 or np.isnan(count_min) or np.isnan(count_max):
                logger.warning(f"RMSE by hour appears invalid: nan_frac={nan_frac:.2%}, count_min={count_min}, count_max={count_max}")
        except Exception:
            pass

        # Save
        output_file = output_dir / f'rmse_by_hour_{var}.nc'
        ds.to_netcdf(output_file)
        logger.info(f"  ✓ Saved: {output_file.name}")
        
        # Summary CSV
        summary = []
        for hour in sorted(by_hour.keys()):
            se_list = by_hour[hour]
            stacked = xr.concat(se_list, dim='sample')
            count = stacked.notnull().sum(dim='sample')
            sum_sq = stacked.sum(dim='sample', skipna=True)
            global_rmse = float(np.sqrt(sum_sq / count.where(count > 0)).mean().values)
            n_samples = len(se_list)
            summary.append({'hour': hour, 'rmse_mean': global_rmse, 'n_pairs': n_samples})
        
        summary_df = pd.DataFrame(summary)
        summary_csv = output_dir / f'rmse_by_hour_{var}.csv'
        summary_df.to_csv(summary_csv, index=False)
        logger.info(f"  ✓ Saved summary: {summary_csv.name}")


if __name__ == '__main__':
    # This script is normally called from the notebook with function imports
    # But can also run standalone for testing
    logger.info("compute_rmse_outputs.py loaded as module")
