"""Publish a small, shareable statistical export of the selected-start diagnostics."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import random
from statistics import mean, median


HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_rows(path, rows, fields):
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def interval(values, salt):
    if not values:
        return None
    rng = random.Random(salt)
    resamples = sorted(mean(rng.choices(values, k=len(values))) for _ in range(10000))
    return [percentile(resamples, q) for q in (0.025, 0.975)]


def percentile(ordered, p):
    location = (len(ordered) - 1) * p
    i = int(location)
    return ordered[i] + (location - i) * (ordered[min(i + 1, len(ordered) - 1)] - ordered[i])


def summary(values, seed):
    return {
        "pairs": len(values),
        "short_tied_long": [sum(v > 0 for v in values), sum(v == 0 for v in values), sum(v < 0 for v in values)],
        "mean_ppm": mean(values) if values else None, "median_ppm": median(values) if values else None,
        "range_ppm": [min(values), max(values)] if values else None,
        "seed_bootstrap_95_percentile_interval": interval(values, seed),
    }


def accepted_record(row, reg):
    name, seed, role = row["map"], row["pool_seed"], row["start"]
    terminal = HERE / "runs" / f"{int(row['slot']):04d}" / "terminal.json"
    dispatch = terminal.with_name("dispatch.json")
    binding = reg["binding"][f"{name}/{seed}"][role]
    out = {
        "slot": row["slot"], "run_id": row["run_id"], "map": name, "pool_seed": seed, "start": role,
        "continuation_seed": row["continuation_seed"], "within_pair": row["within_pair"],
        "start_length": binding["start_length"], "start_sha256": binding["start_sha256"],
        "status": "not_started", "end_length": None, "end_sha256": None, "charged_seconds": None,
    }
    if not dispatch.is_file():
        if terminal.is_file():
            raise ValueError(f"terminal exists without a dispatch: {terminal}")
        return out
    adm = HERE / "diagnostic_admission.json"
    start = load(dispatch)
    if start["row"] != row or start["version"] != reg["version"] or start["gate_sha256"] != sha(adm):
        raise ValueError(f"dispatch does not match registered evidence: {dispatch}")
    if not terminal.is_file():
        return dict(out, status="dispatched_unfinished")
    end = load(terminal)
    if (end["row"] != row or end["version"] != reg["version"] or
            end["dispatch_sha256"] != sha(dispatch) or end["status"] != end["result"]["status"]):
        raise ValueError(f"terminal does not match its dispatch: {terminal}")
    result = end["result"]
    out["status"] = result["status"]
    if out["status"] == "valid":
        source = terminal.parent / "result"
        seal_path = source / "completion.json"
        seal, pending = load(seal_path), source / "result.json"
        final = source / "continuation" / "delivered.tour"
        if (
            seal["state"] != "certified" or seal["status"] != "valid" or
            seal["result_sha256"] != result["result_sha256"] or sha(pending) != result["result_sha256"] or
            seal["evidence"]["route_sha256"] != result["route_sha256"] or sha(final) != result["route_sha256"] or
            result["initial"]["selected_sha256"] != binding["start_sha256"] or
            result["initial"]["selected_length"] != binding["start_length"]
        ):
            raise ValueError(f"diagnostic scoring proof changed: {terminal}")
        out.update(end_length=result["length"], end_sha256=result["route_sha256"],
                   charged_seconds=result["full_charge_s"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New output directory")
    args = parser.parse_args()
    reg = load(HERE / "registration.json")
    plan = HERE / "diagnostic_plan_120.csv"
    if sha(plan) != reg["plan_sha256"]:
        raise ValueError("registered diagnostic plan changed")
    raw_plan = csv_rows(plan)
    if len(raw_plan) != 120:
        raise ValueError("unexpected diagnostic slot count")
    outcomes = [accepted_record(row, reg) for row in raw_plan]
    sets = defaultdict(dict)
    counts = defaultdict(Counter)
    for row in outcomes:
        pool = f"{row['map']}/{row['pool_seed']}"
        if row["start"] in sets[pool, row["continuation_seed"]]:
            raise ValueError("duplicate arm within registered diagnostic pair")
        sets[pool, row["continuation_seed"]][row["start"]] = row
        counts[pool, row["start"]][row["status"]] += 1
    pairs = []
    observed = defaultdict(list)
    by_order = defaultdict(list)
    for (pool, seed), arms in sets.items():
        m, k = arms["M_parent"], arms["K_selected"]
        ok = m["status"] == k["status"] == "valid"
        within = "M_first" if m["within_pair"] == "1" else "K_first"
        estimate = float(Fraction(1_000_000 * (m["end_length"] - k["end_length"]), m["end_length"])) if ok else None
        pairs.append({"pool": pool, "continuation_seed": seed, "order": within, "M_status": m["status"],
                      "K_status": k["status"], "M_end": m["end_length"], "K_end": k["end_length"],
                      "K_over_M_ppm": estimate})
        if ok:
            observed[pool].append(estimate)
            by_order[pool, within].append(estimate)
    classified = dict(Counter(row["status"] for row in outcomes))
    complete = not any(classified.get(status) for status in ("not_started", "dispatched_unfinished"))
    receipts = {
        "scope": "30 s conditional continuation; historical starts selected for large negative outcomes; three fixed pools in two maps",
        "analysis_status": "complete_coverage" if complete else "partial_coverage",
        "planned_runs": 120, "statuses": classified, "pool_count": 3, "map_count": 2, "planned_seed_pairs": 60,
        "uncertainty": "descriptive seed-resampling within each prespecified pool, 10000 resamples; no independent-map or pooled confirmation claim",
        "plan_sha256": reg["plan_sha256"], "pool_summaries": {},
    }
    for i, (name, seed) in enumerate(reg["pool_groups"]):
        pool = f"{name}/{seed}"
        receipts["pool_summaries"][pool] = {
            "planned_pairs": 20,
            "arm_statuses": {a: dict(counts[pool, a]) for a in ("M_parent", "K_selected")},
            "paired": summary(observed[pool], 20261121 + i),
            "by_order": {order: summary(by_order[pool, order], 20261125 + 2 * i + j)
                         for j, order in enumerate(("M_first", "K_first"))},
        }
    args.output.mkdir()
    write_rows(args.output / "outcomes_120.csv", outcomes, list(outcomes[0]))
    write_rows(args.output / "pairs_60.csv", pairs, list(pairs[0]))
    (args.output / "diagnostics_summary.json").write_text(
        json.dumps(receipts, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    print(json.dumps(receipts, ensure_ascii=False))


if __name__ == "__main__":
    main()
