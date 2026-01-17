"""
Automated ECMWF AIFS Data Download Script
Downloads the last 3 complete days of AIFS Single surface forecasts
Designed to run daily via scheduled task

Author: Yeganeh Khabbazian
Course: Earth System Data Processing, University of Cologne, Winter Semester 2025/26
"""

import earthkit.data
from pathlib import Path
from datetime import datetime, timedelta
import time
import os
import sys
import logging

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


def get_last_3_days():
    """Generate list of last 3 complete days (excluding today)"""
    today = datetime.now()
    dates_list = []
    
    for i in range(1, 4):
        date = today - timedelta(days=i)
        dates_list.append(date.strftime("%Y-%m-%d"))
    
    # Reverse to get chronological order (oldest to newest)
    dates_list.reverse()
    return dates_list


def create_filename(model, date, time_hour, levtype, step):
    """Generate standardized GRIB2 filename"""
    clean_date = date.replace("-", "")
    filename = (
        f"{model}_"
        f"{clean_date}_"
        f"{time_hour:02d}_"
        f"{levtype}_"
        f"step{step:03d}_"
        f"0p25.grib2"
    )
    return filename


def download_aifs_data():
    """Main download function"""
    logger.info("=" * 60)
    logger.info("Starting AIFS data download")
    logger.info("=" * 60)
    
    # Configuration
    CFG = {
        "source": "ecmwf-open-data",
        "model": "aifs-single",
        "dates": get_last_3_days(),
        "time": 12,
        "steps": [6, 12, 24],
        "levtype": "sfc",
        "params": ["2t", "10u", "10v", "msl"],
        "out_dir": Path(__file__).parent / "data" / "aifs",
    }
    
    # Create output directory
    OUT = Path(CFG["out_dir"]).resolve()
    OUT.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {OUT}")
    logger.info(f"Dates to download: {CFG['dates']}")
    
    start_time = time.time()
    success_count = 0
    error_count = 0
    total_size = 0
    
    # Download loop
    for date in CFG["dates"]:
        for step in CFG["steps"]:
            target_file = OUT / create_filename(
                CFG["model"], date, CFG["time"], CFG["levtype"], step
            )
            
            try:
                logger.info(f"Requesting {date} step {step:3d}h → {target_file.name}")
                
                # Request data from ECMWF Open Data
                ds = earthkit.data.from_source(
                    CFG["source"],
                    model=CFG["model"],
                    stream="oper",
                    type="fc",
                    date=date,
                    time=CFG["time"],
                    step=step,
                    levtype=CFG["levtype"],
                    param=CFG["params"],
                    target=str(target_file),
                )
                
                # Verify data was returned
                n = len(ds)
                if n == 0:
                    logger.warning(f"No data returned for {date} step {step}h")
                    error_count += 1
                    continue
                
                # Save the data
                ds.save(str(target_file))
                file_size = target_file.stat().st_size
                total_size += file_size
                logger.info(f"✓ Saved: {target_file.name} ({file_size / (1024*1024):.2f} MB)")
                success_count += 1
                
            except Exception as e:
                logger.error(f"✗ Failed to download {date} step {step}h: {str(e)}")
                error_count += 1
    
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
    
    return success_count, error_count


if __name__ == "__main__":
    try:
        success, errors = download_aifs_data()
        sys.exit(0 if errors == 0 else 1)
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)
