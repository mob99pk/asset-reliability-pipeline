"""Generate deliberately messy source data for the Asset Reliability Pipeline.

Writes data/assets.json (nested) and data/work_orders.csv. Seeded, so output is
reproducible. Defect codes (A1-A4, W1-W7) match the staging/test design.

Usage: python scripts/generate_data.py
"""
import csv
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

SEED = 42
N_ASSETS = 200
N_WORK_ORDERS = 2000
START, AS_OF = date(2024, 10, 1), date(2026, 9, 30)

ASSET_CLASSES = ["Pump", "Valve", "Pipeline", "Reservoir", "Meter"]
SITES = ["Kwinana", "Perth CBD", "Fremantle", "Joondalup", "Mandurah", "Rockingham"]
CRITICALITY = ["High", "Medium", "Low"]

# canonical value -> messy variants emitted by the source system
WO_TYPES = {
    "Preventive": ["PM", "preventive", "PREVENTIVE"],
    "Corrective": ["CM", "corrective"],
    "Inspection": ["INSP", "inspection"],
    "Emergency": ["EM", "EMERGENCY"],
}
TYPE_WEIGHTS = [50, 35, 10, 5]
STATUSES = {
    "Open": ["OPEN", "open"],
    "In Progress": ["IN_PROGRESS", "in progress"],
    "Completed": ["COMPLETE", "completed ", "Closed"],
    "Cancelled": ["CANCELLED", "Canceled"],
}
SLA_DAYS = {"P1": (1, 3), "P2": (5, 10), "P3": (14, 30), "P4": (30, 60)}
BAD_DATES = ["2024-13-45", "31/02/2025", "N/A", "0000-00-00", "2025-02-30"]
CSV_FIELDS = ["wo_id", "asset_id", "type", "priority", "raised_date",
              "due_date", "completed_date", "status"]

ROOT = Path(__file__).resolve().parents[1]
rng = random.Random(SEED)


def messy(canonical, variants, p):
    return rng.choice(variants) if rng.random() < p else canonical


def rand_date(lo, hi):
    return lo + timedelta(days=rng.randint(0, (hi - lo).days))


def fmt(d, dmy=False):
    if d is None:
        return ""
    return d.strftime("%d/%m/%Y") if dmy else d.isoformat()


def make_assets():
    assets = []
    for i in range(1, N_ASSETS + 1):
        cls, site = rng.choice(ASSET_CLASSES), rng.choice(SITES)
        crit = rng.choices(CRITICALITY, weights=[25, 50, 25])[0]
        installed = rand_date(date(1995, 1, 1), date(2022, 12, 31))

        r = rng.random()  # A4: mixed install_date formats
        if r < 0.70:
            install = installed.isoformat()
        elif r < 0.95:
            install = fmt(installed, dmy=True)
        else:
            install = rng.choice(["unknown", None])

        location = {"site": site, "region": "WA"}
        r = rng.random()  # A3: null site vs missing key
        if r < 0.05:
            location["site"] = None
        elif r < 0.08:
            del location["site"]

        updated = datetime(2025, 1, 1) + timedelta(minutes=rng.randint(0, 450 * 24 * 60))
        assets.append({
            "asset_id": f"AST-{i:04d}",
            "name": f"{site} {cls} {i:03d}",
            "classification": {  # A2: casing / whitespace noise
                "asset_class": messy(cls, [cls.lower(), cls.upper(), f" {cls} "], 0.15),
                "criticality": messy(crit, [crit.upper(), crit.lower(), f"{crit} "], 0.15),
            },
            "location": location,
            "install_date": install,
            "updated_at": updated.isoformat(timespec="seconds"),
        })

    # A1: duplicates; half exact copies, half re-rated with a newer updated_at
    dupes = []
    for n, a in enumerate(rng.sample(assets, 10)):
        d = json.loads(json.dumps(a))
        if n % 2:
            old = a["classification"]["criticality"].strip().capitalize()
            d["classification"]["criticality"] = rng.choice([c for c in CRITICALITY if c != old])
            newer = datetime.fromisoformat(a["updated_at"]) + timedelta(days=rng.randint(10, 150))
            d["updated_at"] = newer.isoformat(timespec="seconds")
        dupes.append(d)

    records = assets + dupes
    rng.shuffle(records)
    return records, [a["asset_id"] for a in assets]


def lifecycle(raised, due):
    """Simulate status/completion as at AS_OF; older WOs are more likely done."""
    age = (AS_OF - raised).days
    p_done = 0.88 if age > 60 else 0.6 if age > 14 else 0.25
    r = rng.random()
    if r < 0.04:
        return "Cancelled", None
    if r >= 0.04 + p_done:
        return rng.choice(["Open", "In Progress"]), None
    if rng.random() < 0.8:  # ~80% on time
        completed = raised + timedelta(days=rng.randint(0, (due - raised).days))
    else:
        completed = due + timedelta(days=rng.randint(1, 30))
    if completed > AS_OF:
        return "In Progress", None
    return "Completed", completed


def make_work_orders(asset_ids):
    wos = []
    for _ in range(N_WORK_ORDERS):
        wo_type = rng.choices(list(WO_TYPES), weights=TYPE_WEIGHTS)[0]
        priority = "P1" if wo_type == "Emergency" else rng.choices(
            ["P1", "P2", "P3", "P4"], weights=[5, 20, 50, 25])[0]
        raised = rand_date(START, AS_OF)
        due = raised + timedelta(days=rng.randint(*SLA_DAYS[priority]))
        status, completed = lifecycle(raised, due)

        if status == "Completed":  # W6: impossible completion data
            r = rng.random()
            if r < 0.02:
                completed = None
            elif r < 0.03:
                completed = raised - timedelta(days=rng.randint(1, 10))

        asset_id = (rng.choice(asset_ids) if rng.random() > 0.03
                    else f"AST-{rng.randint(9001, 9020)}")  # W7: orphans
        wos.append(dict(asset_id=asset_id, type=wo_type, priority=priority,
                        raised=raised, due=due, completed=completed, status=status))

    wos.sort(key=lambda w: w["raised"])
    for n, w in enumerate(wos):
        w["wo_id"] = f"WO-{100001 + n}"

    rows = []
    for w in wos:
        dmy = rng.random() < 0.08  # W5: some rows exported as DD/MM/YYYY
        r = rng.random()  # W3: null / numeric priority
        priority = "" if r < 0.05 else w["priority"][1:] if r < 0.15 else w["priority"]
        rows.append({
            "wo_id": w["wo_id"],
            "asset_id": w["asset_id"],
            "type": messy(w["type"], WO_TYPES[w["type"]], 0.25),  # W2
            "priority": priority,
            "raised_date": fmt(w["raised"], dmy),
            "due_date": "" if rng.random() < 0.03 else fmt(w["due"], dmy),
            "completed_date": fmt(w["completed"], dmy),
            "status": messy(w["status"], STATUSES[w["status"]], 0.2),  # W4
        })

    # W5: unparseable dates
    for col, k in [("raised_date", 12), ("due_date", 10), ("completed_date", 8)]:
        candidates = [r for r in rows if r[col]]
        for r in rng.sample(candidates, k):
            r[col] = rng.choice(BAD_DATES)

    # W1: duplicates appended as a late "delta" export; last row wins
    late = [dict(r) for r in rng.sample(rows, 25)]  # exact copies
    open_idx = [i for i, w in enumerate(wos)
                if w["status"] in ("Open", "In Progress") and w["raised"] < AS_OF - timedelta(days=7)]
    for i in rng.sample(open_idx, 15):  # status progressed since first export
        updated = dict(rows[i])
        updated["status"] = "Completed"
        updated["completed_date"] = rand_date(wos[i]["raised"], AS_OF).isoformat()
        late.append(updated)
    rng.shuffle(late)
    return rows + late


def main():
    out = ROOT / "data"
    out.mkdir(exist_ok=True)

    assets, asset_ids = make_assets()
    with open(out / "assets.json", "w", encoding="utf-8") as f:
        json.dump(assets, f, indent=2)

    rows = make_work_orders(asset_ids)
    with open(out / "work_orders.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    valid = set(asset_ids)
    print(f"assets.json:     {len(assets)} records, "
          f"{len(assets) - len({a['asset_id'] for a in assets})} duplicate ids")
    print(f"work_orders.csv: {len(rows)} rows, "
          f"{len(rows) - len({r['wo_id'] for r in rows})} duplicate wo_ids, "
          f"{sum(r['asset_id'] not in valid for r in rows)} orphan rows, "
          f"{sum(r['priority'] == '' for r in rows)} null priorities")


if __name__ == "__main__":
    main()
