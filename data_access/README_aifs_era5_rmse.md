# AIFS vs ERA5 RMSE Comparison (Notebook + Scripts)

**Author**: Yeganeh Khabbazian  
**Course**: Earth System Data Processing, University of Cologne, Winter Semester 2025/26  
**Instructor**: Martin Schultz, Jülich Supercomputing Centre & University of Cologne  
**Tools**: Developed with GitHub Copilot

## Overview

This project evaluates AIFS forecasts against ERA5 reanalysis by computing RMSE over Europe. It includes **scripted downloads**, **pairing logic**, and **visual analysis** outputs.

**What is RMSE?** Root Mean Square Error (RMSE) is a standard metric for forecast accuracy. It measures the typical size of errors by squaring differences, averaging them, and taking the square root. Lower RMSE indicates better agreement.

**Scope**: AIFS Single forecasts are compared with ERA5 for matching valid times. The analysis focuses on:
- **2m air temperature (2t)**
- **500 hPa air temperature (t500)**

## Repository Content

- **`data_access/scripts/download_aifs_forecasts.py`**: Downloads AIFS forecast GRIB files
- **`data_access/scripts/download_era5_reanalysis.py`**: Downloads ERA5 reanalysis GRIB files
- **`data_access/scripts/compute_aifs_era5_rmse.py`**: Pairs files and computes RMSE per pair
- **`data_access/scripts/aggregate_rmse_outputs.py`**: Aggregates RMSE by step/day/hour
- **`data_access/scripts/analyze_rmse_outputs.py`**: Produces plots and summary tables
- **`data_access/aifs_config.yaml`**: AIFS download configuration
- **`environment.yml`**: Conda environment specification

## Setup and Execution

### Prerequisites

Create the Conda environment with all required dependencies:

```bash
conda env create -f environment.yml
conda activate aifs
```

The environment includes `earthkit-data` (ECMWF Open Data client), `xarray`/`cfgrib` (GRIB2 file handling), `cartopy` (geospatial visualization), and `eccodes` (GRIB decoding backend).

### Running the Analysis Script

```bash
python data_access/scripts/analyze_rmse_outputs.py
```

The script will:
1. Download AIFS and ERA5 files (if not present)
2. Pair forecast-valid times
3. Compute RMSE
4. Create plots and save them in:

```
Earth_System/earth-system-data-processing/data_access/results
```

### Running Downloads Only

```bash
python data_access/scripts/download_aifs_forecasts.py --config data_access/aifs_config.yaml
python data_access/scripts/download_era5_reanalysis.py
```

## Data Access and Download Scope

- **Spatial coverage**: Global input data, analysis cropped to Europe
- **Temporal resolution**: AIFS initialized at 00/06/12/18 UTC with 6-hourly steps
- **Variables**:
  - AIFS: 2m temperature, 500 hPa temperature
  - ERA5: matching reanalysis fields
- **Format**: GRIB2
- **Outputs**: NetCDF RMSE maps and CSV summaries

### Data Availability Constraints

**ECMWF Open Data** (used in this project):
- Free access, no authentication required
- Retains approximately 4 days of recent forecasts
- Limited to near-real-time applications

**ECMWF MARS Archive** (for historical access):
- Complete archive dating to operational start (February 2025 for AIFS)
- Requires ECMWF membership, research agreement, or commercial license

### Registration and User Experience

**ECMWF Open Data**: No registration required. Access is immediate via public HTTP API.  
**MARS Archive**: Historical access requires institutional credentials, so this project stays within the Open Data retention window.

## Development Notes

**Initial approach**: Started with a small number of forecast days and steps to confirm pairing logic and grid alignment. Expanded to multiple lead times once pairing was stable.

**Key findings**:
- Forecast-valid time matching is the main constraint; AIFS future lead times do not always have ERA5 counterparts.
- ERA5 files are hourly, so matching requires aligning AIFS valid times to ERA5 timestamps.
- RMSE values can differ strongly between land and sea, motivating a dedicated land/sea comparison plot.

## Grid Alignment (AIFS vs ERA5)

Both AIFS and ERA5 are on ~0.25° regular lat/lon grids, but longitude ordering can differ. In practice:
- **ERA5** uses longitudes that start at 0° and increase to 359.75°.
- **AIFS (Open Data)** may start at 180° and wrap to 0°.

This means a direct point-wise subtraction can fail unless the longitude ordering is aligned.

**How it is handled in this project:**
- We verify grid shapes and coordinate values using `data_access/scripts/verify/check_aifs_era5_grid.py`.
- If longitudes are the same values but wrapped, we **roll** AIFS longitude ordering to match ERA5 before RMSE (no interpolation).
- If the grids truly differ (different spacing or values), regridding is required.

## Scaling Considerations

### Current Limitations
1. **Data retention**: Open Data’s ~4-day window limits historical analysis
2. **Download efficiency**: Sequential downloads become slow at scale
3. **Storage organization**: Flat directories do not scale well
4. **Data volume**: Full AIFS archive exceeds hundreds of GB

### Script Modifications for Larger Downloads
- **Date generation**: Use `pandas.date_range()` for arbitrary ranges
- **Parallel execution**: Use `ThreadPoolExecutor` with a small worker cap
- **Resumable downloads**: Skip files that already exist
- **Robust error handling**: Add retries with backoff

### Data Organization at Scale
Use hierarchical storage like `data/{year}/{month}/{day}/{run}/` and consider Zarr or NetCDF for scalable analysis.

## Data Attribution

ECMWF Open Data are available under the Creative Commons CC-BY-4.0 license, which requires attribution.

**Attribution for this project**:
> Adapted from "ECMWF AIFS Single 15-day Forecast Data" by ECMWF, licensed under CC BY 4.0, available at https://data.ecmwf.int/forecasts/

## References

- https://www.ecmwf.int/en/forecasts/dataset/aifs-machine-learning-data
- https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model/aifs-single-v1-implementation
- https://events.ecmwf.int/event/493/
- https://github.com/ecmwf/notebook-examples/tree/master/opencharts
- https://earthkit.readthedocs.io/en/latest/

## License

See `LICENSE` file for details.
