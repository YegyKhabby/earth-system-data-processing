from pathlib import Path
import hashlib
import sys
import traceback

OUT = Path(__file__).parent / "data" / "aifs"
DATES = ["2026-01-12","2026-01-13","2026-01-14"]
STEPS = [6,12,24]

results = []

for date in DATES:
    for step in STEPS:
        fname = f"aifs-single_{date.replace('-','')}_12_sfc_step{step:03d}_0p25.grib2"
        fpath = OUT / fname
        entry = {"file": str(fpath), "exists": False, "size": None, "sha256": None, "open_ok": None, "error": None}
        try:
            if fpath.exists():
                entry["exists"] = True
                entry["size"] = fpath.stat().st_size
                # compute sha256
                h = hashlib.sha256()
                with open(fpath, "rb") as fh:
                    for chunk in iter(lambda: fh.read(8192), b""):
                        h.update(chunk)
                entry["sha256"] = h.hexdigest()
            else:
                entry["error"] = "File not found"
        except Exception as e:
            entry["error"] = f"Stat/hash error: {e}"
        results.append(entry)

# Try opening one sample per date (step=24) using xarray/cfgrib
open_checks = []
try:
    import xarray as xr
    for date in DATES:
        sample = OUT / f"aifs-single_{date.replace('-','')}_12_sfc_step024_0p25.grib2"
        oc = {"sample": str(sample), "opened": False, "vars": None, "error": None}
        try:
            if sample.exists():
                ds = xr.open_dataset(sample, engine="cfgrib", backend_kwargs={"indexpath": ""})
                oc["opened"] = True
                oc["vars"] = list(ds.data_vars)
                ds.close()
            else:
                oc["error"] = "Sample file missing"
        except Exception as e:
            oc["error"] = traceback.format_exc()
        open_checks.append(oc)
except Exception as e:
    open_checks = [{"error": f"xarray/cfgrib import failed: {e}"}]

# Print concise report
print("FILE CHECK RESULTS:\n")
for r in results:
    status = "OK" if (r["exists"] and r["size"] and r["sha256"]) else "MISSING/ERROR"
    print(f"{r['file']}: {status}")
    if r["exists"]:
        print(f"  size: {r['size']:,} bytes")
        print(f"  sha256: {r['sha256']}")
    if r["error"]:
        print(f"  error: {r['error']}")

print("\nOPEN CHECKS (step=24 samples):\n")
for oc in open_checks:
    if oc.get("opened"):
        print(f"{oc['sample']}: opened OK, variables: {oc['vars']}")
    else:
        print(f"{oc.get('sample','?')}: ERROR -> {oc.get('error')}")

# Exit code: 0 if all exists and open checks OK, else 2
all_ok = all(r['exists'] and r['size'] and r['sha256'] for r in results) and all(oc.get('opened', False) for oc in open_checks if 'opened' in oc or 'error' not in oc)
sys.exit(0 if all_ok else 2)
