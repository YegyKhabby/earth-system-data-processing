from pathlib import Path
import re
import statistics

OUT = Path(__file__).parent / "data" / "aifs"
files = sorted(OUT.glob("*.grib2"))
if not files:
    print("No .grib2 files found in", OUT)
    raise SystemExit(2)

pattern = re.compile(r"aifs-single_(\d{8})_\d{2}_sfc_step(\d{3})_0p25.grib2")
by_date = {}
for f in files:
    m = pattern.search(f.name)
    if not m:
        continue
    date = m.group(1)
    step = m.group(2)
    by_date.setdefault(date, []).append((f.name, f.stat().st_size))

threshold_pct = 15.0  # flag files differing more than this percent from median
any_flag = False

print(f"Found {len(files)} files across {len(by_date)} dates.\n")
for date, entries in sorted(by_date.items()):
    sizes = [s for _, s in entries]
    mean = statistics.mean(sizes)
    med = statistics.median(sizes)
    mn = min(sizes)
    mx = max(sizes)
    stdev = statistics.pstdev(sizes) if len(sizes) > 1 else 0
    print(f"Date {date}: files={len(entries)}, mean={mean:,} B, median={med:,} B, min={mn:,} B, max={mx:,} B, stdev={stdev:.0f} B")
    # flag individual files
    for name, size in entries:
        pct_diff = abs(size - med) / med * 100 if med else 0
        flag = pct_diff > threshold_pct
        if flag:
            any_flag = True
            print(f"  ⚠️ {name}: {size:,} B ({pct_diff:.1f}% from median)")
        else:
            print(f"  OK   {name}: {size:,} B ({pct_diff:.1f}% from median)")
    print("")

if any_flag:
    print(f"One or more files exceed {threshold_pct}% difference from median — inspect flagged files.")
    raise SystemExit(3)
else:
    print("All files sizes are consistent within threshold.")
    raise SystemExit(0)
