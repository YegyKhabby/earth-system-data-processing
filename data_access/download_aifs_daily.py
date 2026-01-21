"""
Automated ECMWF AIFS Data Download Script
Downloads the last 3 complete days of AIFS Single surface forecasts
Designed to run daily via scheduled task

Author: Yeganeh Khabbazian
Course: Earth System Data Processing, University of Cologne, Winter Semester 2025/26
"""

import argparse
import earthkit.data
from pathlib import Path
from datetime import datetime, timedelta
import time
import os
import sys
import logging
from typing import Any, Dict
import pandas as pd

# Set up logging
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"aifs_download_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Disable ECMWF index usage for better compatibility
os.environ["ECMWF_OD_USE_INDEX"] = "0"


def get_last_n_days(n_days: int, include_today: bool = False):
    """Generate list of last N complete days (optionally include today)."""
    today = datetime.now()
    dates_list = []

    start_offset = 0 if include_today else 1
    for i in range(start_offset, start_offset + n_days):
        date = today - timedelta(days=i)
        dates_list.append(date.strftime("%Y-%m-%d"))

    # Reverse to get chronological order (oldest to newest)
    dates_list.reverse()
    return dates_list


def create_filename(model, date, time_hour, levtype, step, params, level=None):
    """Generate standardized GRIB2 filename."""
    clean_date = date.replace("-", "")
    params_str = "-".join(params) if params else "params"
    # Include pressure level in filename for pressure-level products
    filename = (
        f"{model}_"
        f"{clean_date}_"
        f"{time_hour:02d}_"
        f"{levtype}_"
        f"{params_str}_"
        + (f"{level}hPa_" if level is not None else "")
        + f"step{step:03d}_0p25.grib2"
    )
    return filename


def parse_area(area_str: str):
    """Parse area string 'N,W,S,E' into list of floats."""
    parts = [p.strip() for p in area_str.split(",")]
    if len(parts) != 4:
        raise ValueError("Area must have 4 comma-separated values: N,W,S,E")
    return [float(p) for p in parts]

def load_yaml_config(path: Path) -> Dict[str, Any]:
    """Load YAML config from disk."""
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError("PyYAML is required for --config. Install with: pip install pyyaml") from e

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("Config must be a YAML mapping at the top level.")
    return data


def build_dates_from_episode(episode: Dict[str, Any]):
    """Build date list from episode config."""
    if not episode:
        return get_last_n_days(3, include_today=False)

    start_date = episode.get("start_date")
    end_date = episode.get("end_date")
    if start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        if end < start:
            raise ValueError("end_date must be >= start_date")
        dates = []
        cur = start
        while cur <= end:
            dates.append(cur.strftime("%Y-%m-%d"))
            cur += timedelta(days=1)
        return dates

    days = int(episode.get("days", 3))
    include_today = bool(episode.get("include_today", False))
    return get_last_n_days(days, include_today=include_today)


def request_with_retries(request_fn, retries: int, sleep_s: float):
    """Call request_fn with retries and simple backoff."""
    attempt = 0
    while True:
        try:
            return request_fn()
        except Exception as e:
            attempt += 1
            if attempt > retries:
                raise
            logger.warning(f"Request failed (attempt {attempt}/{retries}): {e}")
            time.sleep(sleep_s * attempt)


def download_aifs_data(cfg, dry_run: bool = False, overwrite: bool = False, retries: int = 2, sleep_s: float = 5.0):
    """Main download function."""
    logger.info("=" * 60)
    logger.info("Starting AIFS data download")
    logger.info("=" * 60)

    # Create output directory
    OUT = Path(cfg["out_dir"]).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {OUT}")
    logger.info(f"Dates to download: {cfg['dates']}")
    if cfg.get("area") is not None:
        logger.info(f"Spatial subset (N,W,S,E): {cfg['area']}")
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    total_size = 0
    manifest = []
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # Download loop
    # Use configured source name as-is (e.g., ecmwf-open-data)
    source_name = cfg.get("source")

    for date in cfg["dates"]:
        date_obj = datetime.strptime(date, "%Y-%m-%d")
        date_dir = OUT / date_obj.strftime("%Y/%m/%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        for time_hour in cfg["times"]:
            for step in cfg["steps"]:
                if "sfc" in cfg.get("levtypes", ["sfc"]):
                    target_file = date_dir / create_filename(
                        cfg["model"], date, time_hour, "sfc", step, params=cfg["params"]
                    )

                    if target_file.exists() and not overwrite:
                        logger.info(f"Skipping existing file: {target_file.name}")
                        manifest.append({
                            "date": date,
                            "time": time_hour,
                            "step": step,
                            "levtype": "sfc",
                            "status": "skipped",
                            "file": target_file.name,
                        })
                        continue

                    if date == today_str and step in [36, 48]:
                        logger.info(f"Skipping step {step}h for today ({date})")
                        manifest.append({
                            "date": date,
                            "time": time_hour,
                            "step": step,
                            "levtype": "sfc",
                            "status": "skipped",
                            "file": target_file.name,
                        })
                        continue
                    else:
                        try:
                            logger.info(f"Requesting SFC {date} {time_hour:02d}Z step {step:3d}h -> {target_file.name}")

                            def _request():
                                return earthkit.data.from_source(
                                    source_name,
                                    model=cfg["model"],
                                    stream="oper",
                                    type="fc",
                                    date=date,
                                    time=time_hour,
                                    step=step,
                                    levtype="sfc",
                                    param=cfg["params"],
                                    target=str(target_file),
                                    **({"area": cfg["area"]} if cfg.get("area") else {}),
                                )

                            if dry_run:
                                logger.info("Dry run: skipping SFC request")
                            else:
                                ds = request_with_retries(_request, retries=retries, sleep_s=sleep_s)
                                n = len(ds)
                                if n == 0:
                                    logger.warning(f"No SFC data returned for {date} step {step}h")
                                    error_count += 1
                                    manifest.append({
                                        "date": date,
                                        "time": time_hour,
                                        "step": step,
                                        "levtype": "sfc",
                                        "status": "failed",
                                        "file": target_file.name,
                                    })
                                else:
                                    ds.save(str(target_file))
                                    file_size = target_file.stat().st_size
                                    if file_size == 0:
                                        raise RuntimeError("Downloaded file is empty")
                                    total_size += file_size
                                    logger.info(f"Saved: {target_file.name} ({file_size / (1024*1024):.2f} MB)")
                                    success_count += 1
                                    manifest.append({
                                        "date": date,
                                        "time": time_hour,
                                        "step": step,
                                        "levtype": "sfc",
                                        "status": "ok",
                                        "file": target_file.name,
                                    })
                        except Exception as e:
                            logger.error(f"Failed to download SFC {date} step {step}h: {str(e)}")
                            error_count += 1
                            manifest.append({
                                "date": date,
                                "time": time_hour,
                                "step": step,
                                "levtype": "sfc",
                                "status": "failed",
                                "file": target_file.name,
                            })

                if "pl" in cfg.get("levtypes", []) and cfg.get("pl_levels"):
                    for level in cfg.get("pl_levels", []):
                        target_file_pl = date_dir / create_filename(
                            cfg["model"], date, time_hour, "pl", step, params=cfg["pl_params"], level=level
                        )
                        if target_file_pl.exists() and not overwrite:
                            logger.info(f"Skipping existing file: {target_file_pl.name}")
                            manifest.append({
                                "date": date,
                                "time": time_hour,
                                "step": step,
                                "levtype": "pl",
                                "status": "skipped",
                                "file": target_file_pl.name,
                            })
                            continue
                        if date == today_str and step in [36, 48]:
                            logger.info(f"Skipping step {step}h for today ({date})")
                            manifest.append({
                                "date": date,
                                "time": time_hour,
                                "step": step,
                                "levtype": "pl",
                                "status": "skipped",
                                "file": target_file_pl.name,
                            })
                            continue
                        try:
                            logger.info(f"Requesting PL {level}hPa {date} {time_hour:02d}Z step {step:3d}h -> {target_file_pl.name}")

                            pl_kwargs = dict(
                                model=cfg["model"],
                                stream="oper",
                                type="fc",
                                date=date,
                                time=time_hour,
                                step=step,
                                levtype="pl",
                                param=cfg["pl_params"],
                                target=str(target_file_pl),
                            )
                            pl_kwargs["levelist"] = level
                            if cfg.get("area"):
                                pl_kwargs["area"] = cfg["area"]

                            if dry_run:
                                logger.info("Dry run: skipping PL request")
                                continue

                            ds_pl = request_with_retries(
                                lambda: earthkit.data.from_source(source_name, **pl_kwargs),
                                retries=retries,
                                sleep_s=sleep_s
                            )
                            npl = len(ds_pl)
                            if npl == 0:
                                logger.warning(f"No PL data returned for {level}hPa {date} step {step}h")
                                error_count += 1
                                manifest.append({
                                    "date": date,
                                    "time": time_hour,
                                    "step": step,
                                    "levtype": "pl",
                                    "status": "failed",
                                    "file": target_file_pl.name,
                                })
                            else:
                                ds_pl.save(str(target_file_pl))
                                file_size = target_file_pl.stat().st_size
                                if file_size == 0:
                                    raise RuntimeError("Downloaded file is empty")
                                total_size += file_size
                                logger.info(f"Saved: {target_file_pl.name} ({file_size / (1024*1024):.2f} MB)")
                                success_count += 1
                                manifest.append({
                                    "date": date,
                                    "time": time_hour,
                                    "step": step,
                                    "levtype": "pl",
                                    "status": "ok",
                                    "file": target_file_pl.name,
                                })
                        except Exception as e:
                            logger.error(f"Failed to download PL {level}hPa {date} step {step}h: {str(e)}")
                            error_count += 1
                            manifest.append({
                                "date": date,
                                "time": time_hour,
                                "step": step,
                                "levtype": "pl",
                                "status": "failed",
                                "file": target_file_pl.name,
                            })
    
    # Summary
    elapsed_time = time.time() - start_time
    logger.info("=" * 60)
    logger.info("Download Summary")
    logger.info("=" * 60)
    logger.info(f"Successful downloads: {success_count}")
    logger.info(f"Failed downloads: {error_count}")
    logger.info(f"Total size: {total_size / (1024*1024):.2f} MB")
    logger.info(f"Total time: {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)")
    logger.info("=" * 60)

    pd.DataFrame(manifest).to_csv(OUT / "manifest.csv", index=False)
    
    return success_count, error_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download ECMWF AIFS data (surface and optional pressure levels).")
    parser.add_argument("--config", type=str, default=str(Path(__file__).parent / "aifs_config.yaml"), help="Path to YAML config.")
    parser.add_argument("--start-date", type=str, help="Start date (YYYY-MM-DD).")
    parser.add_argument("--end-date", type=str, help="End date (YYYY-MM-DD).")
    parser.add_argument("--days", type=int, default=None, help="Number of recent days to download (default from config).")
    parser.add_argument("--include-today", action="store_true", help="Include today (may be incomplete).")
    parser.add_argument("--time", type=int, default=None, help="Run time (UTC hour).")
    parser.add_argument("--steps", type=str, default=None, help="Comma-separated steps in hours.")
    parser.add_argument("--params", type=str, default=None, help="Comma-separated surface params.")
    parser.add_argument("--pl-params", type=str, default=None, help="Comma-separated pressure-level params.")
    parser.add_argument("--pl-levels", type=str, default=None, help="Comma-separated pressure levels (hPa). Use empty to disable.")
    parser.add_argument("--area", type=str, help="Spatial subset as N,W,S,E (e.g., 55,5,47,15).")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing files.")
    parser.add_argument("--dry-run", action="store_true", help="Print requests without downloading.")
    parser.add_argument("--retries", type=int, default=2, help="Retry count on failure.")
    parser.add_argument("--sleep", type=float, default=5.0, help="Sleep seconds between retries (base).")
    args = parser.parse_args()

    cfg_file = Path(args.config)
    cfg_yaml = load_yaml_config(cfg_file) if cfg_file.exists() else {}
    cfg_aifs = cfg_yaml.get("aifs", {}) if isinstance(cfg_yaml, dict) else {}

    # Episode: prefer CLI if explicitly set, else use config episode
    episode_cfg = cfg_aifs.get("episode", {}) if isinstance(cfg_aifs, dict) else {}
    if args.start_date and args.end_date:
        episode_cfg = {"start_date": args.start_date, "end_date": args.end_date}
    elif args.days is not None or args.include_today:
        episode_cfg = {
            "days": args.days if args.days is not None else episode_cfg.get("days", 3),
            "include_today": args.include_today,
        }

    dates = build_dates_from_episode(episode_cfg)

    steps = [int(s.strip()) for s in args.steps.split(",") if s.strip()] if args.steps else list(cfg_aifs.get("steps_hours", [0, 6, 12, 18]))
    params = [p.strip() for p in args.params.split(",") if p.strip()] if args.params else list(cfg_aifs.get("sfc_params", ["2t", "10u", "10v", "msl"]))
    pl_params = [p.strip() for p in args.pl_params.split(",") if p.strip()] if args.pl_params else list(cfg_aifs.get("pl_params", ["t"]))
    if args.pl_levels is not None:
        pl_levels = [int(p.strip()) for p in args.pl_levels.split(",") if p.strip()]
    else:
        pl_levels = list(cfg_aifs.get("pl_levels", [500]))

    if args.time is not None:
        times = [args.time]
    else:
        times = list(cfg_aifs.get("init_hours_utc", [12]))

    levtypes = cfg_aifs.get("levtypes", ["sfc", "pl"])

    cfg = {
        "source": cfg_aifs.get("source", "ecmwf-open-data"),
        "model": cfg_aifs.get("model", "aifs-single"),
        "dates": dates,
        "times": times,
        "steps": steps,
        "levtype": "sfc",
        "params": params,
        "pl_params": pl_params,
        "pl_levels": pl_levels,
        "levtypes": levtypes,
        "out_dir": Path(args.out_dir) if args.out_dir else Path(cfg_aifs.get("out_dir", Path(__file__).parent / "data" / "aifs")),
    }
    region = cfg_aifs.get("region")
    if region and region != "global" and not args.area:
        cfg["area"] = parse_area(region)
    if args.area:
        cfg["area"] = parse_area(args.area)

    try:
        success, errors = download_aifs_data(
            cfg,
            dry_run=args.dry_run,
            overwrite=bool(cfg_aifs.get("overwrite", args.overwrite)),
            retries=int(cfg_aifs.get("max_retries", args.retries)),
            sleep_s=float(cfg_aifs.get("backoff_seconds", args.sleep)),
        )
        sys.exit(0 if errors == 0 else 1)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
