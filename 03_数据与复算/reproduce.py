"""Recompute the 600-slot C/M/K study from the accompanying audited CSV."""
import argparse
import csv
import hashlib
import json
import math
import random
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from statistics import median
import sys


BUNDLE = Path(__file__).resolve().parent
METHODS = ("C_ref", "M_new", "K_new")
COMPARISONS = (("K_new", "M_new"), ("K_new", "C_ref"), ("M_new", "C_ref"))
STRATA = {
    "01_VLSI_engineering": "VLSI engineering",
    "02_DIMACS_clustered": "DIMACS clustered",
    "03_DIMACS_uniform": "DIMACS uniform",
    "04_Waterloo_geographic": "Waterloo geographic",
}
SEED = 20261120
DRAWS = 100_000


def exact_p(values):
    """Enumerate every sign assignment by joining signed sums of two halves."""
    denominator = math.lcm(*(value.denominator for value in values))
    units = [int(value * denominator) for value in values if value]
    cutoff = abs(sum(units))
    if cutoff == 0:
        return Fraction(1)

    def signed_sums(seq):
        sums = [0]
        for unit in seq:
            sums = [s + unit for s in sums] + [s - unit for s in sums]
        return sums

    mid = len(units) // 2
    right = sorted(signed_sums(units[mid:]))
    hits = sum(
        bisect_right(right, -cutoff - lhs) + len(right) - bisect_left(right, cutoff - lhs)
        for lhs in signed_sums(units[:mid])
    )
    return Fraction(hits, 1 << len(units))


def interval(values):
    rng = random.Random(SEED)
    observed = [float(value) for value in values]
    n = len(observed)
    draws = sorted(sum(rng.choices(observed, k=n)) / n for _ in range(DRAWS))

    def interpolate(p):
        loc = p * (DRAWS - 1)
        floor = math.floor(loc)
        return draws[floor] + (loc - floor) * (draws[floor + 1] - draws[floor])

    return [interpolate(0.025), interpolate(0.975)]


def holm(p_values):
    maximum = Fraction(0)
    adjusted = {}
    for rank, key in enumerate(sorted(p_values, key=p_values.get)):
        maximum = min(Fraction(1), max(maximum, (len(p_values) - rank) * p_values[key]))
        adjusted[key] = float(maximum)
    return adjusted


def read_runs(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        runs = list(csv.DictReader(stream))
    grid, labels, observed = {}, {}, set()
    for row in runs:
        name, seed, method = row["map"], row["seed"], row["method"]
        identity = name, seed, method
        if identity in observed or method not in METHODS or row["stratum"] not in STRATA:
            raise ValueError(f"Duplicate or unknown study slot: {identity}")
        observed.add(identity)
        if labels.setdefault(name, row["stratum"]) != row["stratum"]:
            raise ValueError(f"Inconsistent stratum: {name}")
        outcomes = grid.setdefault((name, seed), {})
        length = row["checked_length"]
        if row["status"] == "valid":
            if int(length) <= 0 or not row["route_sha256"]:
                raise ValueError(f"Missing valid result or route hash: {identity}")
            outcomes[method] = int(length)
        elif length or row["route_sha256"]:
            raise ValueError(f"Unexpected score on failed slot: {identity}")
    if (
        len(runs) != 600
        or len({row["run_id"] for row in runs}) != 600
        or len(grid) != 200
        or Counter(name for name, _ in grid) != Counter({name: 10 for name in labels})
        or Counter(labels.values()) != Counter({key: 5 for key in STRATA})
        or any((name, seed, method) not in observed for name, seed in grid for method in METHODS)
    ):
        raise ValueError("Expected 20 maps, 10 seeds per map and three attempted methods per seed")
    return runs, grid, labels


def signs(values):
    return [sum(v > 0 for v in values), sum(v == 0 for v in values), sum(v < 0 for v in values)]


def compare(grid, labels, trial, reference, *, formal):
    label = f"{trial}/{reference}"
    per_map = defaultdict(list)
    pair_rows = []
    for (name, seed), scores in grid.items():
        if trial not in scores or reference not in scores:
            continue
        t = scores[trial]
        r = scores[reference]
        value = Fraction((r - t) * 1_000_000, r)
        per_map[name].append(value)
        pair_rows.append(
            dict(comparison=label, map=name, stratum=labels[name], seed=seed, trial_length=t,
                 reference_length=r, exact_reduction_ppm=str(value), reduction_ppm=float(value))
        )
    means = {name: sum(values) / len(values) for name, values in per_map.items()}
    by_map = [
        dict(comparison=label, map=name, stratum=stratum, valid_pairs=len(per_map[name]),
             mean_reduction_ppm=float(means[name]) if name in means else None)
        for name, stratum in labels.items()
    ]
    effects = list(means.values())
    total = sum(effects)
    stratum_rows = []
    for stratum, stratum_name in STRATA.items():
        named = [name for name in means if labels[name] == stratum]
        entries = [value for name in named for value in per_map[name]]
        short, tied, long = signs(entries)
        stratum_rows.append(
            dict(comparison=label, stratum=stratum, stratum_name=stratum_name, maps=len(named),
                 valid_pairs=len(entries), short=short, tied=tied, long=long,
                 map_equal_mean_ppm=float(sum(means[name] for name in named) / len(named)))
        )
    stat = dict(
        pairs=len(pair_rows), maps=len(means), missing_pair_slots=len(grid)-len(pair_rows),
        short_tied_long=signs([value for values in per_map.values() for value in values]),
        per_stratum={r["stratum"]: {"maps": r["maps"], "average_ppm": r["map_equal_mean_ppm"]}
                     for r in stratum_rows},
        mean_ppm=float(total / len(effects)), median_map_ppm=float(median(effects)),
        ci95_pct_map_bootstrap_ppm=interval(effects),
        most_negative_pair_ppm=min(row["reduction_ppm"] for row in pair_rows),
        leave_one_map={name: float((total-value) / (len(means)-1)) for name, value in means.items()},
    )
    p = exact_p(effects) if formal else None
    if p is not None:
        stat["sign_flip_p"] = float(p)
    return stat, by_map, pair_rows, stratum_rows, p


def analyses(grid, labels, *, formal):
    stats, by_map, pairs, strata, raw_secondary = {}, [], [], [], {}
    for trial, reference in COMPARISONS:
        key = f"{trial}/{reference}"
        result, maps, paired, strata_rows, p = compare(grid, labels, trial, reference, formal=formal)
        stats[key] = result
        by_map.extend(maps)
        pairs.extend(paired)
        strata.extend(strata_rows)
        if formal and reference == "C_ref":
            raw_secondary[key] = p
    if formal:
        raw_secondary.update({"K_new/EAX_ref": Fraction(1), "M_new/EAX_ref": Fraction(1)})
        adjusted = holm(raw_secondary)
        for key in stats.keys() & adjusted.keys():
            stats[key]["holm_p"] = adjusted[key]
    return stats, by_map, pairs, strata


def verify_reference(actual, frozen, name="reference"):
    if isinstance(frozen, dict):
        if actual.keys() != frozen.keys():
            raise ValueError(f"Field discrepancy: {name}")
        for key, value in frozen.items():
            verify_reference(actual[key], value, f"{name}.{key}")
    elif isinstance(frozen, list):
        if len(actual) != len(frozen):
            raise ValueError(f"Length discrepancy: {name}")
        for i, (lhs, rhs) in enumerate(zip(actual, frozen)):
            verify_reference(lhs, rhs, f"{name}[{i}]")
    elif isinstance(frozen, float):
        if not math.isclose(actual, frozen, rel_tol=1.0e-13, abs_tol=1.0e-13):
            raise ValueError(f"Numeric discrepancy: {name}: {actual} vs {frozen}")
    elif actual != frozen:
        raise ValueError(f"Value discrepancy: {name}: {actual} vs {frozen}")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plot(out, statistics, maps, pairs):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 11, "font.family": "DejaVu Sans", "pdf.fonttype": 42})
    display = {"K_new/M_new": "K vs M", "K_new/C_ref": "K vs C", "M_new/C_ref": "M vs C"}

    def save(fig, stem):
        fig.savefig(out / (stem + ".png"), dpi=350, bbox_inches="tight")
        fig.savefig(out / (stem + ".pdf"), bbox_inches="tight", metadata={"CreationDate": None})
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.8, 2.9), layout="constrained")
    for y, (name, effect) in enumerate(statistics.items()):
        mean = effect["mean_ppm"]
        low, high = effect["ci95_pct_map_bootstrap_ppm"]
        ax.errorbar(mean, y, xerr=[[mean-low], [high-mean]], fmt="o" if y == 0 else "s",
                    color="#006194" if y == 0 else "#333333", linewidth=1.5, capsize=4)
    ax.set(yticks=list(range(3)), yticklabels=[display[name] for name in statistics],
           xlabel="Map-equal route-length reduction (ppm)")
    ax.invert_yaxis()
    ax.set_ylim(2.45, -0.45)
    ax.axvline(0, color="#666666", linestyle="--", linewidth=1)
    ax.grid(axis="x", linewidth=0.5, alpha=0.35)
    ax.spines[["top", "right"]].set_visible(False)
    save(fig, "overall_effects_95ci")

    fig, axes = plt.subplots(1, 3, figsize=(10, 5.5), sharey=True, sharex=True, layout="constrained")
    ordered = sorted({(row["stratum"], row["map"]) for row in maps})
    for ax, name in zip(axes, statistics):
        observed = {row["map"]: row["mean_reduction_ppm"] for row in maps if row["comparison"] == name}
        ax.scatter([observed[map_name] for _, map_name in ordered], range(len(ordered)),
                   s=18, color="#006194", zorder=3)
        ax.axvline(0, color="#666666", linestyle="--", linewidth=0.9)
        ax.set(title=display[name], xlabel="Reduction (ppm)")
        ax.grid(axis="x", linewidth=0.5, alpha=0.25)
    axes[0].set_yticks(list(range(len(ordered))), [name for _, name in ordered], fontsize=8.5)
    axes[0].invert_yaxis()
    save(fig, "map_effects")

    fig, axes = plt.subplots(1, 3, figsize=(10, 3.2), sharey=True, sharex=True, layout="constrained")
    for ax, name in zip(axes, statistics):
        values = sorted(row["reduction_ppm"] for row in pairs if row["comparison"] == name)
        n = len(values)
        x = [values[0], *values, values[-1]]
        y = [0, *(i / n for i in range(1, n+1)), 1]
        ax.step(x, y, where="post", color="#006194", linewidth=1.5)
        ax.axvline(0, color="#666666", linestyle="--", linewidth=0.9)
        ax.set(title=f"{display[name]} (n={n})", xlabel="Reduction (ppm)")
    axes[0].set_ylabel("Empirical cumulative proportion")
    save(fig, "pair_ecdf")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BUNDLE / "recomputed")
    args = parser.parse_args()
    source = BUNDLE / "data" / "core_600_runs.csv"
    reference = json.loads((BUNDLE / "data" / "frozen_reference.json").read_text(encoding="utf-8"))
    if hashlib.sha256(source.read_bytes()).hexdigest() != reference["portable_csv_sha256"]:
        raise ValueError("The numeric source CSV does not match its bundled SHA256")
    runs, grid, labels = read_runs(source)
    status = {method: dict(Counter(r["status"] for r in runs if r["method"] == method)) for method in METHODS}
    verify_reference(status, reference["by_method"], "statuses")
    statistics, maps, pairs, strata = analyses(grid, labels, formal=True)
    verify_reference(statistics, reference["effects"], "frozen_effects")
    joint = {identity: scores for identity, scores in grid.items() if all(m in scores for m in METHODS)}
    if len(joint) != 196:
        raise ValueError("Expected the complete-data sensitivity to use 196 groups")
    sensitivity, joint_maps, _, _ = analyses(joint, labels, formal=False)
    excluded = [
        dict(map=name, seed=seed, excluded_reason="at_least_one_invalid_delivery",
             unavailable_methods=";".join(method for method in METHODS if method not in outcomes))
        for (name, seed), outcomes in grid.items()
        if (name, seed) not in joint
    ]
    loo = [
        dict(comparison=comparison, omitted_map=name, map_equal_mean_ppm=estimate)
        for comparison, effect in statistics.items()
        for name, estimate in effect["leave_one_map"].items()
    ]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "map_effects.csv", maps)
    write_csv(out / "paired_effects.csv", pairs)
    write_csv(out / "four_strata.csv", strata)
    write_csv(out / "leave_one_map.csv", loo)
    write_csv(out / "complete_triplet_map.csv", joint_maps)
    write_csv(out / "excluded_triplets.csv", excluded)
    write_csv(out / "delivery_by_method.csv", [
        dict(method=m, attempted=200, valid=status[m].get("valid", 0),
             budget_no_delivery=status[m].get("budget_no_delivery", 0),
             monitor_invalid=status[m].get("monitor_invalid", 0),
             execution_error=status[m].get("execution_error", 0))
        for m in METHODS
    ])
    write_csv(out / "complete_triplet_summary.csv", [
        dict(comparison=name, complete_groups=effect["pairs"], maps=effect["maps"],
             short=effect["short_tied_long"][0], tied=effect["short_tied_long"][1],
             long=effect["short_tied_long"][2], mean_ppm=effect["mean_ppm"],
             ci95_low_ppm=effect["ci95_pct_map_bootstrap_ppm"][0],
             ci95_high_ppm=effect["ci95_pct_map_bootstrap_ppm"][1])
        for name, effect in sensitivity.items()
    ])
    plot(out, statistics, maps, pairs)
    result = dict(
        frozen_reference_check="passed", attempted_slots=len(runs), valid_outputs=sum(s["valid"] for s in status.values()),
        by_method=status, effects=statistics, complete_triplet_groups=len(joint),
        complete_triplet_effects_descriptive=sensitivity,
        bootstrap=dict(unit="map", draws=DRAWS, seed=SEED, interval="linear percentile 2.5/97.5"),
        holm_family=["K_new/C_ref", "M_new/C_ref", "K_new/EAX_ref", "M_new/EAX_ref"],
        eax="unestimated; p=1 adjustment placeholders only",
        environment=dict(python=".".join(map(str, sys.version_info[:3])), matplotlib=version("matplotlib")),
    )
    (out / "statistical_reproduction.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("Reproduced frozen primary and secondary results from 600 rows.")
    print("Wrote complete-triplet sensitivity, four-stratum data, leave-one-map analysis and three figures.")


if __name__ == "__main__":
    main()
