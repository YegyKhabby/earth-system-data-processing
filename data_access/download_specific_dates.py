"""
Download specific AIFS dates (one-off helper)
"""
import earthkit.data
from pathlib import Path
import os
from datetime import datetime

os.environ["ECMWF_OD_USE_INDEX"] = "0"

DATES = ["2026-01-13", "2026-01-14"]
STEPS = [6,12,24]
PARAMS = ["2t","10u","10v","msl"]
OUT = Path(__file__).parent / "data" / "aifs"
OUT.mkdir(parents=True, exist_ok=True)

print(f"Output dir: {OUT}")
for date in DATES:
    for step in STEPS:
        fname = f"aifs-single_{date.replace('-','')}_12_sfc_step{step:03d}_0p25.grib2"
        target = OUT / fname
        print(f"Requesting {date} step {step}h -> {fname}")
        try:
            ds = earthkit.data.from_source(
                "ecmwf-open-data",
                model="aifs-single",
                stream="oper",
                type="fc",
                date=date,
                time=12,
                step=step,
                levtype="sfc",
                param=PARAMS,
                target=str(target),
            )
            n = len(ds)
            print(f"Messages returned: {n}")
            if n:
                ds.save(str(target))
                print(f"Saved: {target} size: {target.stat().st_size}")
            else:
                print(f"No data returned for {date} step {step}h")
        except Exception as e:
            print(f"Failed: {date} step {step}h -> {e}")

print("Done")
