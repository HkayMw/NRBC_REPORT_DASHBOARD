"""Generate the fictional data used by the public demo.

Creates:
- examples/demo/master_list.csv  districts, zones and centers
- examples/demo/responses.csv    daily form responses for one phase

Every name and figure is made up. The responses include the data-entry
problems the dashboard is built to catch, so each check has something to
show. Run again to get the same files:

    python scripts/generate_demo_data.py
"""

import csv
import math
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

SEED = 2026
PHASE_START = date(2026, 7, 6)
PHASE_END = date(2026, 7, 15)
OUT_DIR = Path(__file__).resolve().parents[1] / "examples" / "demo"

MASTER = {
    "Hillside District": {
        "HILLTOP": ["OAKRIDGE", "RIVERBEND", "SUNNYSIDE", "MAPLE", "CEDAR", "HILLTOP MARKET"],
        "GREENFIELD": ["WILLOW", "PINECREST", "BROOKSIDE", "FAIRVIEW", "GREENFIELD CLINIC"],
        "STONEBRIDGE": [
            "ELMWOOD", "REDSTONE", "ASHFORD", "FOXHILL", "STONEBRIDGE HALL", "MILLBROOK",
        ],
    },
    "Lakeside District": {
        "LAKEVIEW": ["CLEARWATER", "SILVERLAKE", "MEADOWBANK", "LAKEVIEW MARKET", "BAYSIDE"],
        "HARBOUR": ["NORTHGATE", "EASTWOOD", "WESTFIELD", "HARBOUR CLINIC", "SEAVIEW", "DOCKSIDE"],
        "PALM GROVE": ["PALM GROVE", "CORAL", "SANDHILL", "TIDEWATER", "LAGOON"],
    },
}

# Header drift: the form's wording differs from the app's canonical names.
COLUMNS = [
    "Timestamp", "ZONE NAME", "Centre Name", "Reporting Date",
    "Total Male Births Registered", "Total Female Births Registered",
    "Male NID", "Female NID",
]

NEVER_REPORTS = ("STONEBRIDGE", "MILLBROOK")       # 0% completion
OFTEN_MISSES = {("HARBOUR", "DOCKSIDE"): 0.55}     # patchy reporting
# Mistyped names in the form, and the master names they stand for.
CENTER_TYPOS = {
    ("HILLTOP", "OAKRIDGE"): "Oakrige",
    ("GREENFIELD", "BROOKSIDE"): "Brookside Primary School",
    ("HARBOUR", "EASTWOOD"): "Eastwod P/S",
    ("LAKEVIEW", "SILVERLAKE"): "Silver Lake",
}
ZONE_TYPOS = {("GREENFIELD", "WILLOW"): "Greenfeild", ("PALM GROVE", "CORAL"): "Palmgrove"}


def daily_counts(rng: random.Random, size: float, day_factor: float) -> list:
    def poisson(mean: float) -> int:
        # Knuth's method is fine for these small means.
        limit, k, p = math.exp(-mean), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1

    return [
        poisson(4 * size * day_factor), poisson(4 * size * day_factor),
        poisson(11 * size * day_factor), poisson(13 * size * day_factor),
    ]


def ts(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def build_rows(rng: random.Random) -> list:
    rows = []
    days = [PHASE_START + timedelta(n) for n in range((PHASE_END - PHASE_START).days + 1)]
    for district, zones in MASTER.items():
        for zone, centers in zones.items():
            for center in centers:
                if (zone, center) == NEVER_REPORTS:
                    continue
                size = rng.uniform(0.6, 1.6)
                miss = OFTEN_MISSES.get((zone, center), 0.05)
                for n, day in enumerate(days):
                    if rng.random() < miss:
                        continue
                    ramp = 0.7 + 0.6 * math.sin(math.pi * (n + 1) / (len(days) + 1))
                    submitted = datetime.combine(day, time(15, 0)) + timedelta(
                        minutes=rng.randint(0, 240), seconds=rng.randint(0, 59))
                    if rng.random() < 0.07:  # sent the next morning
                        submitted += timedelta(hours=rng.randint(15, 17))
                    zone_text = ZONE_TYPOS.get((zone, center), zone.title())
                    center_text = CENTER_TYPOS.get((zone, center), center.title())
                    if rng.random() < 0.05:  # stray spaces and casing
                        center_text = f"  {center_text.lower()} "
                    rows.append([ts(submitted), zone_text, center_text, day.isoformat(),
                                 *daily_counts(rng, size, ramp)])
    return rows


def plant_problems(rows: list, rng: random.Random) -> None:
    """Add the data-entry problems each dashboard check looks for."""
    # Day/month swaps only make sense for days 8 to 12 (both read as valid dates).
    swappable = [i for i, r in enumerate(rows) if 8 <= date.fromisoformat(r[3]).day <= 12]
    swaps = rng.sample(swappable, 2)
    picks = rng.sample([i for i in range(len(rows)) if i not in swaps], 14)

    for i in picks[:6]:  # corrected resubmissions: same center and day, later
        fixed = list(rows[i])
        fixed[4 + rng.randrange(4)] += rng.choice([-2, -1, 1, 3])
        fixed[0] = ts(datetime.fromisoformat(rows[i][0]) + timedelta(minutes=rng.randint(10, 90)))
        rows.append(fixed)
    for i in picks[6:8]:  # fractional counts
        rows[i][4 + rng.randrange(4)] = rng.choice([2.5, 12.01])
    for i in picks[8:11]:  # missing counts
        rows[i][4 + rng.randrange(4)] = ""
    rows[picks[11]][6] = -3  # negative count
    for i in swaps:  # day and month swapped (e.g. 9 July typed as 7 September)
        d = date.fromisoformat(rows[i][3])
        rows[i][3] = date(d.year, d.day, d.month).isoformat()
    rows[picks[12]][3] = "2026-09-14"  # outside the activity window
    rows[picks[13]][3] = "2026-07-30"  # outside the activity window


def main() -> None:
    rng = random.Random(SEED)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(OUT_DIR / "master_list.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["District", "Zone", "Center"])
        for district, zones in MASTER.items():
            for zone, centers in zones.items():
                for center in centers:
                    writer.writerow([district, zone, center])

    rows = build_rows(rng)
    plant_problems(rows, rng)
    rows.sort(key=lambda r: r[0])
    with open(OUT_DIR / "responses.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    n_centers = sum(len(c) for z in MASTER.values() for c in z.values())
    print(f"{n_centers} centers, {len(rows)} responses")


if __name__ == "__main__":
    main()
