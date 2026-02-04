# AIFS vs ERA5 RMSE Comparison Pipeline

**Author:** Yeganeh Khabbazian  
**Course:** Earth System Data Processing, University of Cologne, Winter Semester 2025/26  
**Instructor:** Martin Schultz, Jülich Supercomputing Centre & University of Cologne  
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

## RMSE Metric (Why It Fits, and What It Misses)

**RMSE definition:** square the errors, average them, then take the square root.  
**Why it fits here:** it penalizes large errors, so it highlights bad forecasts and spatial hotspots.  
**Limitations:**
- Outliers can dominate the score.
- RMSE does not show bias direction (warm vs cold).
- Aggregation can hide localized problems.

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
- **`data_access/README_era5.md`**: ERA5 pipeline documentation (separate project)
- **`data_access/README_ecmwf_aifs.md`**: AIFS Open Data notes
- **`data_access/analyze_rmse_outputs.ipynb`**: Interactive Jupyter notebook for full pipeline orchestration and plotting (recommended for exploration)
- **`data_access/aifs_config.yaml`**: AIFS download configuration
- **`data_access/era5_config.yaml`**: ERA5 download configuration
- **`data_access/aifs_input_output_fields.png`**: AIFS fields reference figure
- **`data_access/scripts/download_aifs_forecasts.py`**: Download AIFS forecast GRIB files
- **`data_access/scripts/download_era5_reanalysis.py`**: Download ERA5 NetCDF files
- **`data_access/scripts/compute_aifs_era5_rmse.py`**: Indexing, pairing, RMSE computation
- **`data_access/scripts/aggregate_rmse_outputs.py`**: Aggregation by step/day/hour
- **`data_access/scripts/verify/check_aifs_era5_grid.py`**: Grid alignment checks
- **`data_access/scripts/checkncfiles.py`**: Quick NetCDF checks
- **`data_access/scripts/temp_era5_aifs_metadata.py`**: Metadata inspection helper
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
Run cells sequentially. Cells are documented with markdown explanations and inline comments. Great for exploration and understanding the pipeline.

**Command-Line (Headless):**
```bash
python data_access/scripts/analyze_rmse_outputs.py
```
All-in-one execution. Downloads, computes RMSE, generates plots, and saves results to `data_access/results/`.

Both do the same thing: download AIFS + ERA5 (if missing), pair forecast-valid times, compute RMSE and aggregations, and generate plots.

### Run Downloads Only

```bash
python data_access/scripts/download_aifs_forecasts.py --config data_access/aifs_config.yaml
python data_access/scripts/download_era5_reanalysis.py
```

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
- **Script:** `compute_aifs_era5_rmse.py` (functions only, no CLI)
- **What happens:** Scans downloaded files, creates manifest of available pairs, validates time alignment
- **Called by:** `compute_rmse_outputs.py` during orchestration
- **Output:** Pair manifests with status (`ok`, `missing_aifs`, `missing_era5`) saved to CSV

### Stage 3: RMSE Computation
- **Script:** `compute_rmse_outputs.py` (functions only, no CLI)
- **What happens:** Loops over valid pairs, opens each AIFS+ERA5 file pair, computes squared error grids
- **Called by:** `analyze_rmse_outputs.py` during orchestration
- **Bottleneck:** ~70% of total time (1–2 sec per pair due to file I/O)
- **Output:** Squared-error grids (intermediate, stored in memory)

### Stage 4: Aggregation
- **Script:** `aggregate_rmse_outputs.py` (functions only, no CLI)
- **What happens:** Groups squared-error grids by lead time, date, and hour; computes RMSE; saves NetCDF + CSV summaries
- **Called by:** `analyze_rmse_outputs.py` during orchestration
- **Output:** `data/rmse_outputs/rmse_by_step_*.nc`, `rmse_by_day_*.nc`, `rmse_by_hour_*.nc` (and CSV equivalents)

### Stage 5: Plotting & Analysis
- **Jupyter Notebook:** `analyze_rmse_outputs.ipynb` (full orchestration + plotting, interactive)
- **Alternative Script:** `analyze_rmse_outputs.py` (headless version of the notebook)
- **What happens:** Generates scatter maps, time series, and land/sea comparisons; saves to `data_access/results/`
- **Calls:** Stages 1–4 in sequence
- **Output:** PNG/PDF plots in `results/` directory


---

## Configuration

**Configuration files** (`aifs_config.yaml`, `era5_config.yaml`) are heavily commented with detailed field-by-field explanations. Edit them directly to customize downloads and behavior.


**Plotting** — Edit `PLOT_CFG` dictionary in `analyze_rmse_outputs.py` (all 17 parameters are documented inline with usage examples).

## Advanced Usage

### Change Spatial Region for Analysis

Default: Central Europe. To change:

1. **Edit `analyze_rmse_outputs.py`:**
   ```python
   EUROPE_EXTENT = (lon_min, lon_max, lat_min, lat_max)  # For map plots
   # ... later in script:
   EUROPE_BBOX = (N, W, S, E)  # For RMSE computation (N,W,S,E format)
   ```
   Example for global: `EUROPE_EXTENT = (-180, 180, -90, 90)`, `EUROPE_BBOX = (90, -180, -90, 180)`

2. **Or download region-specific data via CLI:**
   ```bash
   python data_access/scripts/download_aifs_forecasts.py --area "50,10,40,20"  # Italy
   ```

### Run Analysis for Specific Date Range

```bash
python data_access/scripts/download_aifs_forecasts.py \
  --start-date 2026-01-01 \
  --end-date 2026-01-31
```

Then run `analyze_rmse_outputs.py` as usual (it will find the downloaded files).

### Analyze Specific Variables

Edit `VARIABLES` in `analyze_rmse_outputs.py`:
```python
VARIABLES = ['2t']  # Only 2m temperature
# or
VARIABLES = ['2t', 't500', 't850']  # Add 850 hPa if downloaded
```

### Skip Downloads (Use Existing Data)

Edit `analyze_rmse_outputs.py`, comment out the download calls:
```python
# result = download_data(...)  # Comment this out
result = True  # Assume data already exists
```

### Dry Run (Preview Without Downloading)

```bash
python data_access/scripts/download_aifs_forecasts.py --dry-run
```

Prints all file requests without downloading. Useful for checking what will be fetched.

---

## Utilities & Troubleshooting

### Grid Alignment Check

```bash
python data_access/scripts/verify/check_aifs_era5_grid.py
```

**What it does:** Validates that AIFS and ERA5 grids match after longitude roll. Run this if you suspect grid misalignment.

**Output example:**
```
AIFS shape: (721, 1440)
ERA5 shape: (721, 1440)
Latitude match: ✓
Longitude match (after roll): ✓
```

### Quick NetCDF Inspection

```bash
python data_access/scripts/checkncfiles.py
```

Inspects all ERA5 NetCDF files in `data/era5/archive/real/` and reports dimensions, variables, and missing days.

### Metadata Inspection

```bash
python data_access/scripts/temp_era5_aifs_metadata.py
```

Prints metadata (coordinates, attributes, valid times) from downloaded AIFS and ERA5 files. Useful for debugging pairing issues.

### Common Issues

| Issue | Solution |
|-------|----------|
| **Downloads fail with HTTP 429** | ECMWF rate limit triggered. Script retries automatically with linear backoff (10s, 20s, 30s by default). For persistent issues, increase `--sleep` parameter (e.g., `--sleep 30`) or run at off-peak hours. |
| **"No pairs found"** | Check manifest CSVs in `data/aifs/raw/manifest.csv` and `data/era5/downloads/real/manifest.csv`. Ensure AIFS and ERA5 cover same dates. |
| **Plots not generated** | Check `results/` directory exists. If grid mismatch, run `verify/check_aifs_era5_grid.py`. |
| **Out of memory (OOM)** | Reduce `days` in config or process variables separately. Stream aggregation not yet implemented. |
| **Old results mixed with new** | `analyze_rmse_outputs.py` auto-cleans old RMSE NetCDFs before rerun; manual cleanup: `rm data/rmse_outputs/rmse_*.nc`. |

---

## Automation

To automate daily downloads and analysis (macOS or Windows), see:

**[`data_access/scripts/schedule/README_automation.md`](scripts/schedule/README_automation.md)**

Quick start:
- **macOS:** `bash scripts/schedule/schedule_aifs_daily_macos.sh`
- **Windows:** `PowerShell scripts\schedule\schedule_aifs_daily.ps1` (as Administrator)

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

**Observed results (from the check):**
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
3. **Repeated file I/O** — each pair independently opens AIFS GRIB and ERA5 NetCDF files (no caching between pairs).
4. **Memory-intensive aggregation** — all squared-error grids are loaded into RAM before aggregating; this limits multi-month runs on constrained systems.
5. **Storage growth** — full-resolution RMSE maps (721×1440 grids) add up quickly; CSV summaries are much more compact.


**Where the time goes:**
1. **RMSE computation** (~70%): `compute_pair_rmse()` in `compute_aifs_era5_rmse.py` is called once per pair during the pre-computation phase. Each call opens a GRIB file and an ERA5 NetCDF, aligns coordinates, crops, and subtracts per pair. This is done once offline and results are cached to NetCDF.
2. **Aggregation & plotting** (~25%): stacking grids and rendering scatter maps.
3. **Downloads & indexing** (~5%): fast unless network is slow.

**Notebook execution** is now fast because it loads pre-computed RMSE from NetCDF files instead of recomputing per pair. See "Completed Optimizations" below. 

### Main Bottleneck: Per-Pair File I/O

Each pair is processed independently in a loop (in compute_rmse_outputs.py):

for idx, row in pairs.iterrows():
    result = compute_rmse_func(aifs_path=..., era5_path=..., ...)
    # Opens 2 files, processes, closes, repeats

**Impact:** 
- 100 pairs → 200 file opens (100 AIFS + 100 ERA5)
- 1000 pairs → 2000 file opens
**Why not cache?**
- Multiple AIFS files per day (different init times & lead steps)
- Multiple pairs can use the same ERA5 daily file, but a simple cache would require grouping pairs by date first
- For 1–2 week runs (current use case), the complexity isn't justified

### Secondary Bottleneck: Memory During Aggregation

In compute_rmse_outputs.py all squared-error grids are concatenated at once:

**Workaround:** The code processes variables separately (`2t`, `t500`), reducing peak memory by half.

### Tertiary Bottleneck: Plotting Dense Maps

Scatter maps with 1+ million points are slow to render. I mitigated it in 
rmse_coarsen_factor: 4,  # Coarsen 0.25° grid to 1°, reducing points to ~65k


This is effective and keeps plotting time under a few minutes even for large runs.

### Network Rate Limiting (Real but Manageable)

ECMWF Open Data has a soft cap of ~500 simultaneous connections. During busy hours, requests may fail with **HTTP 429** (too many requests).

**Current behavior:** Failed requests are retried with linear backoff (default: 10s, 20s, 30s, etc. for up to 5 retries). For HTTP 429, you may need to manually wait or increase the `--sleep` parameter to a larger base value (e.g., 30–60 seconds).

---

## Completed Optimizations

### Figure 5: RMSE Distribution by Lead Time (✓ Implemented, ~72× speedup)

**Problem:** Cell 29 (Figure 5) called `compute_pair_rmse()` on-demand for every pair, requiring ~10 seconds to complete (100+ file I/O operations).

**Solution:** Refactored to load pre-computed RMSE grids from `rmse_by_step_*.nc` NetCDF files generated during the `compute_aifs_era5_rmse.py` phase.

**How it works:**
- Pre-computed files contain full RMSE maps (3D: step × latitude × longitude)
- Plotting function extracts RMSE values for each lead time, flattens them, and passes to matplotlib's boxplot
- Shows spatial variability across all grid cells per lead time (more informative than single aggregates)

**Performance:**
- **Before:** ~10 seconds (on-demand computation per pair)
- **After:** ~140 milliseconds (cache load + plot)
- **Speedup:** ~72×

**Trade-off:** Requires `compute_aifs_era5_rmse.py` run first (one-time, part of standard pipeline). Subsequent notebook reruns are instant.

---

## Possible Improvements

These optimizations would help for multi-month runs or parallel deployments. Not implemented because the current 1–2 week analysis window doesn't justify the added complexity.

### High-Impact Optimizations

1. **Cache file opens per day** (Est. **30–50% speedup**, offline computation)
   - Currently: open same ERA5 file multiple times per day during RMSE computation
   - Proposed: group pairs by date, open each file once, process all pairs, close
   - Code change: group pairs by `valid_dt.date()` before the loop in `compute_rmse_outputs.py`
   - Why not done: offline pre-computation already cached via NetCDF; barely helps for 1–2 week runs; adds code complexity

2. **Parallelize pair processing** (Est. **3–6× speedup**)
   - Currently: sequential loop over pairs
   - Proposed: `concurrent.futures.ThreadPoolExecutor` with 4–8 workers
   - Code change: replace `for idx, row in pairs.iterrows():` with thread pool
   - Caveat: Python's GIL limits gains; I/O parallelization helps more than CPU
   - Why not done: triggering ECMWF rate limits (HTTP 429) becomes a problem

3. **Streaming aggregation** (Est. **40% memory reduction**)
   - Currently: load all grids in RAM, concatenate, aggregate
   - Proposed: accumulate sums and counts per grid cell as pairs process (no concat)
   - Code change: replace `xr.concat()` with incremental sum/count updates
   - Why not done: incompatible with current architecture; would need refactor

### Medium-Impact Optimizations

4. **Pre-crop once, reuse** (Est. **10–20% speedup**)
   - Currently: crop to `EUROPE_BBOX` inside each pair's `compute_pair_rmse()`
   - Proposed: crop AIFS/ERA5 files once after indexing, cache cropped versions
   - Code change: add pre-crop step before the pair loop
   - Trade-off: uses more disk; speeds up pairs

5. **Resume logic** (Est. **huge speedup on re-runs**)
   - Currently: recompute all pairs every run
   - Proposed: save pair results to a manifest, skip already-computed pairs
   - Code change: check manifest before calling `compute_pair_rmse()`
   - Value: if pipeline crashes mid-run, resume without starting over
   - Why not done: requires careful state management; current runs are fast enough to complete

6. **Compressed outputs** (Est. **20–30% storage savings, negligible runtime impact**)
   - Currently: NetCDF with default compression
   - Proposed: NetCDF with `zlib` (8–9) or Zarr format
   - Code change: add `encoding={'zlib': True, 'complevel': 9}` to `to_netcdf()`
   - Why not done: already using xarray's sensible defaults; gains are modest

### Low-Impact Optimizations

7. **Low-res quicklook plots** (Est. **small time saving, big for QA**)
   - Currently: one resolution for all plots
   - Proposed: generate coarse (1–2°) plots fast, full-res only on demand
   - Code change: parameterize coarsening in `analyze_rmse_outputs.py`
   - Already partially done with `rmse_coarsen_factor`; further gains are minimal

---

## Robustness Across the Pipeline

The pipeline includes multiple safeguards to prevent data loss, corruption, and runaway resource consumption. These are especially important for automated runs.

### Download Layer (`download_aifs_forecasts.py` & `download_era5_reanalysis.py`)

**Network Resilience:**
- **Retries with exponential backoff** — transient network failures are retried automatically; permanent errors (404s) are not retried, saving time on missing data
- **HTTP 429 backoff** — respects ECMWF rate limiting; backs off gracefully when the portal is busy

**Disk & Storage Guards:**
- **Free disk space check** — stops downloads if available space drops below `min_free_gb` threshold, preventing "disk full" crashes mid-run
- **Global size cap** — `STOP_DOWNLOADS_<limit>GB` marker file created when combined AIFS+ERA5 exceeds `max_total_gb` config; prevents scheduler from accidentally filling all storage
  - *Why this matters:* scheduler runs daily; if you forget to monitor, data could grow unbounded. This auto-stops it.
  - *Set in config:* `max_total_gb: 1.0` (default) or adjust based on your storage

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

**`compute_aifs_era5_rmse.py` (Indexing & Pairing):**
- **Explicit pairing status** — each pair marked with status (`ok`, `missing_aifs`, `missing_era5`, `time_not_found`); makes failures auditable
- **Time alignment checks** — verifies ERA5 contains the valid time before attempting pair computation; prevents silent mismatches

**`aggregate_rmse_outputs.py` (Aggregation):**
- **Skips failed pairs** — only aggregates pairs with `status='ok'`; prevents NaN propagation from bad pairs
- **Dimension validation** — checks that spatial dimensions exist before stacking; catches malformed grids early
- **Dual output format** — saves both NetCDF (for detailed analysis) and CSV (for quick checks); CSVs act as quick sanity check

**`analyze_rmse_outputs.py` (Analysis & Plotting):**
- **Stale output cleanup** — removes old `rmse_*` files before rerun; prevents accidentally mixing old and new results
- **Per-figure exception handling** — if one plot fails, others still generate; resilient to bad data in single variable/step
- **Eager dataset loading** — reads datasets fully into memory instead of lazy-loading; prevents file handle exhaustion
- **Range/step sanity prints** — logs suspicious values (e.g., NaN-only grids, step=0) to console; easy to spot invalid outputs

**`verify/check_aifs_era5_grid.py` (QA):**
- **Explicit grid diagnostics** — prints lat/lon shape, spacing, and coordinate order; detects alignment issues before pair computation
- **Pre/post-roll comparison** — tests whether longitude rolling fixes misalignment; confirms grid matching strategy

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
