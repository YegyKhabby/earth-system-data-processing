# AIFS vs ERA5 RMSE Comparison Pipeline

**Author:** Yeganeh Khabbazian  
**Tool:** Used GitHub Copilot

---

## Overview

This project evaluates **AIFS Single forecasts** against **ERA5 reanalysis** by computing RMSE over a Central Europe region and producing spatial and temporal analyses.

**What the pipeline does (configurable):**

- **Downloads** AIFS forecasts and ERA5 reanalysis fields (if missing)
- **Pairs** AIFS valid times with matching ERA5 timestamps
- **Computes RMSE** per pair and aggregates by lead time, day, and hour
- **Generates plots** for spatial RMSE, time-series summaries, and land/sea comparisons

**Why RMSE?** RMSE is a standard forecast metric that squares errors before averaging, so it penalizes large errors and is sensitive to outliers. Therefore it highlights bad forecasts and spatial hotspots, which fits this project.

**Scope:**
- **Variables:** 2m air temperature (2t), 500 hPa temperature (t500)
- **Spatial focus:** Central Europe (cropped for maps and summary statistics)
- **Temporal focus:** AIFS valid times that overlap ERA5 coverage
- **Configurable downloads:** Change what gets downloaded in `aifs_config.yaml` and `era5_config.yaml`.

---

## Dataset Information

**AIFS**: AIFS is a machine learning–based global weather forecasting model operational since February 2025, developed by ECMWF to complement the traditional physics-based Integrated Forecasting System (IFS). The current version was trained on ERA5 reanalysis data (1979–2018) and fine-tuned on operational IFS forecasts (2019–2020), using both pressure-level and surface variables along with auxiliary forcing information such as solar radiation.

**Operational specifications**: AIFS produces global forecasts at 0.25° × 0.25° resolution four times daily (00, 06, 12, 18 UTC), in 6-hourly forecast steps. Two operational configurations exist: AIFS Single (deterministic model, operational since 25 February 2025) and AIFS Ensemble (ensemble model, operational since 1 July 2025). 

| Property | Details |
|---|---|
| **Spatial resolution** | ~0.25° regular lat/lon grid |
| **Temporal resolution** | 6-hourly initialization (00/06/12/18 UTC) |
| **Lead times** | Multiple forecast steps |
| **Coverage** | Global |
| **Access** | ECMWF Open Data (free, limited retention) |
| **Format used here** | GRIB2 |


**ERA5** (ECMWF Reanalysis v5) is global climate reanalysis from the European Centre for Medium-Range Weather Forecasts. It blends observations (satellites, weather stations, aircraft) with model data via advanced data assimilation.

| Property | Details |
|---|---|
| **Spatial resolution** | ~0.25° regular lat/lon grid |
| **Temporal resolution** | Hourly (this project uses 6-hourly subset) |
| **Variables** | Many fields; this project uses temperature |
| **Coverage** | Global |
| **Access** | ECMWF ERA5 (downloaded locally for matching) |
| **Format used here** | NetCDF (.nc) |

---

## Köppen Climate Zones (Background Layer)

**What it is:** The Köppen–Geiger climate classification divides the world into climate zones based on long‑term temperature and precipitation. We use it as a background layer to contextualize RMSE patterns (e.g., coastal vs continental climates).

**Where to download:** Use the dataset page below (it provides a 1km GeoTIFF plus a legend file).  
Download the **GeoTIFF** and **legend.txt** from:  
```
https://data-staging.naturalcapitalproject.org/dataset/sts-b04939b0df93eb3f4305a065933c66122a0edc6fa425b157b99aa7b4b4446d20
```

**Where to put it:**  
Place the GeoTIFF in:
```
Earth_System/earth-system-data-processing/data/static/
```
Use this filename (the analysis script checks it):
- `koppen_geiger_climatezones_1991_2020_1km.tif`

**Class list (30 zones):**  
We follow the standard 30-class Köppen legend. A few examples:
- **Af** = Tropical rainforest  
- **Csa** = Hot-summer Mediterranean  
- **Dfb** = Warm-summer humid continental  
- **ET** = Alpine tundra  
- **EF** = Polar ice cap

Full list used in this project:
Af, Am, Aw, BWh, BWk, BSh, BSk, Csa, Csb, Csc, Cwa, Cwb, Cwc, Cfa, Cfb, Cfc, Dsa, Dsb, Dsc, Dsd, Dwa, Dwb, Dwc, Dwd, Dfa, Dfb, Dfc, Dfd, ET, EF.


---

## Scope and Configuration

- **Region for maps:** Central Europe  
  - `EUROPE_EXTENT = (-5, 25, 43, 58)` (lon_min, lon_max, lat_min, lat_max)
- **Region for RMSE crop:**  
  - `EUROPE_BBOX = (56, 0, 44, 20)` (N, W, S, E)
- **Variables:** 2t and t500
- **Matching:** AIFS valid time must exist in ERA5
- **Global size cap:** `max_total_gb` in `aifs_config.yaml` or `era5_config.yaml` (applies to AIFS+ERA5 combined)

EUROPE_EXTENT is used for plotting, while EUROPE_BBOX is used for RMSE computation
to reduce I/O and processing cost.

---

## Repository Content

- **`data_access/README_aifs_era5_rmse.md`**: This README
- **`data_access/analyze_rmse_outputs.ipynb`**: Interactive Jupyter notebook for full pipeline orchestration and plotting 
- **`data_access/aifs_config.yaml`**: AIFS download configuration
- **`data_access/era5_config.yaml`**: ERA5 download configuration
- **`data_access/scripts/download_aifs_forecasts.py`**: Download AIFS forecast GRIB files
- **`data_access/scripts/download_era5_reanalysis.py`**: Download ERA5 NetCDF files
- **`data_access/scripts/compute_aifs_era5_rmse.py`**: Indexing, pairing, RMSE computation
- **`data_access/scripts/aggregate_rmse_outputs.py`**: Aggregation by step/day/hour
- **`data_access/scripts/verify/check_aifs_era5_grid.py`**: Grid alignment checks
- **`data_access/scripts/schedule/`**: Scheduling helpers and automation README
- **`data_access/logs/`**: Download logs for AIFS and ERA5

---

## Getting Started

### Prerequisites

```bash
conda env create -f environment.yml
conda activate aifs
```


### Run the Full Analysis

**Interactive Notebook (Recommended):**
```bash
jupyter notebook data_access/analyze_rmse_outputs.ipynb
```
Run cells sequentially. Cells are documented with markdown explanations and inline comments. 

---

## Pipeline Architecture

The analysis runs through five stages, each independent but typically orchestrated together:

```
Download Layer
    ↓
Indexing & Pairing Layer
    ↓
RMSE Computation Layer
    ↓
Aggregation Layer
    ↓
Plotting & Analysis Layer
```

### Stage 1: Download
- **Scripts:** `download_aifs_forecasts.py`, `download_era5_reanalysis.py`
- **What happens:** Fetches AIFS GRIB2 files and ERA5 NetCDF files, stores in dated directories
- **Orchestrated by:** `analyze_rmse_outputs.py` (automatic) or manual invocation
- **Output:** Raw files in `data/aifs/raw/` and `data/era5/downloads/real/`

### Stage 2: Indexing & Pairing
- **Script:** `compute_aifs_era5_rmse.py` 
- **What happens:** Scans downloaded files, creates manifest of available pairs, validates time alignment
- **Called by:** `compute_rmse_outputs.py` during orchestration
- **Output:** Pair manifests with status (`ok`, `missing_aifs`, `missing_era5`) saved to CSV

### Stage 3: RMSE Computation
- **Script:** `compute_rmse_outputs.py` 
- **What happens:** Loops over valid pairs, opens each AIFS+ERA5 file pair, computes squared error grids
- **Called by:** `analyze_rmse_outputs.py` during orchestration
- **Bottleneck:** ~70% of total time (1–2 sec per pair due to file I/O)
- **Output:** Squared-error grids (intermediate, stored in memory)

### Stage 4: Aggregation
- **Script:** `aggregate_rmse_outputs.py`
- **What happens:** Groups squared-error grids by lead time, date, and hour; computes RMSE; saves NetCDF + CSV summaries
- **Called by:** `analyze_rmse_outputs.py` during orchestration
- **Output:** `data/rmse_outputs/rmse_by_step_*.nc`, `rmse_by_day_*.nc`, `rmse_by_hour_*.nc` (and CSV )

### Stage 5: Plotting & Analysis
- **Jupyter Notebook:** `analyze_rmse_outputs.ipynb` (full orchestration + plotting, interactive)
- **What happens:** Generates scatter maps, time series, and land/sea comparisons; saves to `data_access/results/`
- **Calls:** Stages 1–4 in sequence
- **Output:** PNG plots in `results/` directory


---

## Configuration

**Configuration files** (`aifs_config.yaml`, `era5_config.yaml`) are heavily commented with detailed field-by-field explanations. Edit them directly to customize downloads and behavior.


**Plotting** — Edit `PLOT_CFG` dictionary in `analyze_rmse_outputs.ipynb`



---

## Automation

To automate daily downloads and analysis (macOS or Windows), see:

**[`data_access/scripts/schedule/README_automation.md`](scripts/schedule/README_automation.md)**

Quick start:
- **macOS:** `bash scripts/schedule/schedule_aifs_daily_macos.sh`
- **Windows:** `PowerShell scripts\schedule\schedule_aifs_daily.ps1` 

---

## Output Structure

```
Earth_System/earth-system-data-processing/
  data_access/
    logs/
      aifs_log/
      era5_log/
    scripts/
      schedule/
      verify/
    results/                   # Plots saved by analyze_rmse_outputs.py
    README_aifs_era5_rmse.md
    aifs_config.yaml
    STOP_DOWNLOADS_*.GB         # Marker file created when size limit is reached

  data/
    aifs/
      raw/                      # AIFS GRIB2 files (by date)
      raw/manifest.csv          # AIFS download manifest
    era5/
      downloads/real/           # Raw ERA5 downloads
      downloads/real/manifest.csv
      downloads/mock/           # Mock downloads (if used)
      downloads/mock/manifest.csv
      archive/real/             # Processed ERA5 by date
      archive/mock/             # Mock archive
    rmse_outputs/               # NetCDF + CSV RMSE aggregations
      cfgrib_index/             # cfgrib index cache
      rmse_by_step_*.nc          # RMSE maps aggregated by lead time
      rmse_by_step_*.csv         # Global RMSE summary by lead time
      rmse_by_day_*.nc           # RMSE maps aggregated by date
      rmse_by_day_*.csv          # Global RMSE summary by date
      rmse_by_hour_*.nc          # RMSE maps aggregated by valid hour
      rmse_by_hour_*.csv         # Global RMSE summary by valid hour
      pairs_manifest_*.csv       # Pairing manifest for each variable
    static/                     # Land/sea mask, orography, Koppen
```

---

## Grid Alignment (AIFS vs ERA5)

We validate the grids using:  
`data_access/scripts/verify/check_aifs_era5_grid.py`

**Observed results:**
- **Shape:** both are **721 × 1440**
- **Latitude:** 90 → −90 with **0.25°** spacing (descending)
- **Longitude:** matches **after roll/normalization** to 0 → 359.75 (0.25° spacing)
- **Grid type:** regular lat/lon for both

**Interpretation:**  
AIFS uses the same longitude values as ERA5 but starts at −180 (wrapped ordering).  
After we **roll** AIFS longitudes (as implemented in `compute_aifs_era5_rmse.py`), the grids match exactly.  
So the fix is **re-ordering**, not interpolation.

After rolling AIFS longitudes from [-180, 180) to [0, 360), the grids match exactly.




---

## Data Access Constraints

**ECMWF Open Data (AIFS):**
- Free access, no authentication
- Retains only a few recent forecast days

**ECMWF MARS Archive (historical):**
- Full archive, but requires institutional access or license

This project uses Open Data to stay within the retention window.

---

## Scaling Behavior and Performance

### Current Limitations

1. **Open Data retention window** — ECMWF only keeps the last ~4 days. Requires daily automated runs to maintain continuous coverage.
3. **Repeated file I/O** — each pair independently opens AIFS GRIB and ERA5 NetCDF files (no caching between pairs except while plotting).
4. **Memory-intensive aggregation** — all squared-error grids are loaded into RAM before aggregating; this limits multi-month runs on constrained systems.
5. **Storage growth** — full-resolution RMSE maps (721×1440 grids) add up quickly


**Where the time goes:**
1. **RMSE computation** (~70%): `compute_pair_rmse()` in `compute_aifs_era5_rmse.py` is called once per pair during the pre-computation phase. Each call opens a GRIB file and an ERA5 NetCDF, aligns coordinates, crops, and subtracts per pair. This is done once offline and results are cached to NetCDF.
2. **Aggregation & plotting** (~25%): stacking grids and rendering scatter maps.
3. **Downloads & indexing** (~5%): fast unless network is slow.

**Notebook execution** is now fast because it loads pre-computed RMSE from NetCDF files instead of recomputing per pair. See "Completed Optimizations" below. 

### Main Bottleneck: Per-Pair File I/O (During Computation)

Each pair is processed in a loop to compute RMSE:

**Impact:** 
- 100 pairs → 200 file opens (100 AIFS + 100 ERA5)
- 1000 pairs → 2000 file opens

This is unavoidable for the initial computation, but the results are cached so recomputation is never needed.


### Tertiary Bottleneck: Plotting Dense Maps

Scatter maps with 1+ million points are slow to render. I mitigated it in 
rmse_coarsen_factor: 4,  # Coarsen 0.25° grid to 1°, reducing points to ~65k


This is effective and keeps plotting time relatively short.

### Network Rate Limiting 

ECMWF Open Data has a soft cap of ~500 simultaneous connections. During busy hours, requests may fail with **HTTP 429** (too many requests).

**Current behavior:** Failed requests are retried with linear backoff (default: 10s, 20s, 30s, etc. for up to 5 retries). For HTTP 429, you may need to manually wait or increase the `--sleep` parameter to a larger base value (e.g., 30–60 seconds).


---

## Possible Improvements

These optimizations would help for multi-month runs or parallel deployments. Not implemented because the current 1–2 week analysis window doesn't justify the added complexity.

### High-Impact Optimizations

1. **Parallelize pair processing** (Est. **3–6× speedup**)
   - Currently: sequential loop over pairs
   - Proposed: 4–8 workers
 


5. **Resume logic** (Est. **huge speedup on re-runs**)
   - Currently: recompute all pairs every run
   - Proposed: save pair results to a manifest, skip already-computed pairs
   - Why not done: the script is modified constantly and need fresh computations for now

6. **Compressed outputs** (Est. **20–30% storage savings, negligible runtime impact**)
   - Currently: NetCDF with default compression
   - Proposed: NetCDF with `zlib` or Zarr format
   



## Robustness Across the Pipeline

The pipeline includes multiple safeguards to prevent data loss, corruption, and runaway resource consumption.

### Download Layer (`download_aifs_forecasts.py` & `download_era5_reanalysis.py`)

**Network Resilience:**
- **Retries with exponential backoff** — transient network failures are retried automatically; permanent errors (404s) are not retried, saving time on missing data
- **HTTP 429 backoff** — respects ECMWF rate limiting; backs off gracefully when the portal is busy

**Disk & Storage Guards:**
- **Free disk space check** — stops downloads if available space drops below `min_free_gb` threshold, preventing "disk full" crashes mid-run
- **Global size cap** — `STOP_DOWNLOADS_<limit>GB` marker file created when combined AIFS+ERA5 exceeds `max_total_gb` config; prevents scheduler from accidentally filling all storage
  - *Why this matters:* scheduler runs daily; if one forgets to monitor, data could grow unbounded. This automatically stops it.
  - *Set in config:* `max_total_gb: 1.0` (default) or adjust.

**Download Integrity:**
- **Idempotent downloads** — skips files that already exist unless `--overwrite` flag is used; safe to re-run without wasting bandwidth
- **File size validation** — flags suspiciously small/large files (e.g., if download was truncated)
- **Completeness checks** (ERA5) — verifies all expected days are present before marking download complete; doesn't proceed with partial days

**Operational Visibility:**
- **Manifest + structured logs** — every download attempt (success/failure) recorded in CSV manifest and dated log files; essential for debugging failed runs
  - AIFS manifest: `data/aifs/raw/manifest.csv`
  - ERA5 manifest: `data/era5/downloads/{real|mock}/manifest.csv`
  - Logs: `data_access/logs/aifs_log/`, `data_access/logs/era5_log/`

**AIFS-Specific:**
- **Partial-day protection** — "today's" longest lead-time forecasts are skipped to avoid downloading data that will become stale before the next run

**ERA5-Specific:**
- **Mock vs. real separation** — test downloads go to `downloads/mock/`, production to `downloads/real/`; prevents test files from contaminating real archive
- **Archiving** — downloaded files organized by date in `archive/real/`; enables fast re-pairing without re-downloading

### Computation Layer

**Key safeguards in indexing, pairing, and aggregation:**
- **Explicit pairing status** — each pair marked with status (`ok`, `missing_aifs`, `missing_era5`, `time_not_found`); audit trail for debugging
- **Time alignment checks** — verifies ERA5 contains valid time before computation
- **Skips failed pairs** — only aggregates pairs with `status='ok'`; prevents NaN propagation
- **Dimension validation** — checks spatial dimensions exist before stacking
- **Dual output format** — saves both NetCDF (detailed) and CSV (quick sanity checks)
- **Stale output cleanup** — removes old RMSE files before rerun to prevent mixing results
- **Per-figure exception handling** — one plot failing doesn't stop others
- **Eager dataset loading** — loads fully into memory to prevent file handle exhaustion

**Validation utilities:**
- **`check_aifs_era5_grid.py`** — validates grid alignment (shape, coords, lon wrapping)
- **`check_nans_aifs_era5.py`** — quick scan for data corruption across large datasets

### Automation Layer (`scripts/schedule/*`)

- **Daily scheduler** — runs downloads on macOS and Windows automatically; prevents data loss to short Open Data retention window (~4 days)
- **Conditional execution** — can disable specific steps (download, RMSE, plots) via config; prevents re-running expensive steps unnecessarily
- **Documented turnoff** — see `data_access/scripts/schedule/README_automation.md` for how to pause scheduler without breaking workflow


---

## References

- https://www.ecmwf.int/en/forecasts/dataset/aifs-machine-learning-data  
- https://www.ecmwf.int/en/forecasts/documentation-and-support/changes-ecmwf-model/aifs-single-v1-implementation  
- https://earthkit.readthedocs.io/en/latest/

---

## License

See `LICENSE` for details.
