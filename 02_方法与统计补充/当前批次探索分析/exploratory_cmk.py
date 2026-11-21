"""Reproduce exploratory order and start/finish diagnostics from the frozen 600-task package."""

import argparse
import csv
import hashlib
import itertools
import json
import random
from collections import Counter, defaultdict
from math import isclose
from pathlib import Path
from statistics import mean, median


INPUTS = {
    "pairs": "03_数据与复算/复算产物/paired_effects.csv",
    "runs": "03_数据与复算/data/core_600_runs.csv",
    "pools": "02_方法与统计补充/父池与费用版本核对_200组.csv",
    "times": "02_方法与统计补充/主臂计费事件_600项.csv",
    "design": "04_证据与获取/原始证据/phase_b_design/主实验800_候选账本.csv",
}
STRATA = {
    "01_VLSI_engineering": "VLSI",
    "02_DIMACS_clustered": "Clustered",
    "03_DIMACS_uniform": "Uniform",
    "04_Waterloo_geographic": "Geographic",
}
COLORS = ["#245E82", "#A94732", "#25807D", "#8A6500"]
FILTER_PPM = 1000
PERMUTATION_SEED = 20261121
PERMUTATION_DRAWS = 100_000


def keyed_csv(source):
    with source.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def index(rows, *fields):
    result = {tuple(row[f] for f in fields): row for row in rows}
    assert len(result) == len(rows), fields
    return result


def ppm(trial, reference):
    return 1_000_000 * (reference - trial) / reference


def unique_len(rows, field):
    return len({row[field] for row in rows})


def grouped(rows, key):
    result = defaultdict(list)
    for row in rows:
        result[key(row)].append(row)
    return result


def map_mean(rows, field):
    return mean(mean(r[field] for r in values) for values in grouped(rows, lambda r: r["map"]).values())


def exact_sign_flip(differences):
    sums = [0.0]
    for delta in differences:
        sums = [old - delta for old in sums] + [old + delta for old in sums]
    observed = abs(sum(differences))
    extreme = sum(abs(value) >= observed - 1e-9 for value in sums)
    return {"p_two_sided": extreme / len(sums), "enumerated": len(sums), "extreme": extreme}


def conditional_permutation(rows, observed):
    """Condition on observed valid pairs and per-map observed K-first counts."""
    distributions = []
    for _, per_map in sorted(grouped(rows, lambda r: r["map"]).items()):
        outcomes = [row["final_advantage_ppm"] for row in per_map]
        total = sum(outcomes)
        n_k = sum(row["order"] == "K_first" for row in per_map)
        n_m = len(outcomes) - n_k
        distributions.append([
            sum(cell) / n_k - (total - sum(cell)) / n_m
            for cell in itertools.combinations(outcomes, n_k)
        ])
    generator = random.Random(PERMUTATION_SEED)
    threshold = abs(observed * len(distributions)) - 1e-9
    extreme = sum(
        abs(sum(generator.choice(cell) for cell in distributions)) >= threshold
        for _ in range(PERMUTATION_DRAWS)
    )
    return {"p_two_sided_with_plus_one": (extreme + 1) / (PERMUTATION_DRAWS + 1),
            "extreme": extreme, "draws": PERMUTATION_DRAWS, "seed": PERMUTATION_SEED,
            "condition": "Fix observed valid outcomes and observed per-map counts; label exchangeability assumes no schedule interference or selection by valid status."}


def crosscheck(raw):
    assert len(raw["design"]) == 800 and len(raw["runs"]) == 600 and len(raw["pools"]) == 200
    assert Counter(r["status"] for r in raw["runs"]) == {"valid": 596, "monitor_invalid": 3, "execution_error": 1}
    run = index(raw["runs"], "map", "seed", "method")
    design = index(raw["design"], "map", "pool_seed", "method")
    time = index(raw["times"], "run_id")
    recorded = index(raw["pairs"], "comparison", "map", "seed")
    counts = Counter()
    skipped = []
    dataset = []
    for pool in raw["pools"]:
        m, k = run[pool["map"], pool["base_seed"], "M_new"], run[pool["map"], pool["base_seed"], "K_new"]
        c = run[pool["map"], pool["base_seed"], "C_ref"]
        for r in (m, k, c):
            plan = design[r["map"], r["seed"], r["method"]]
            assert (r["run_id"], r["slot"], r["stratum"], r["instance_sha256"]) == (
                plan["run_id"], plan["slot"], plan["stratum"], plan["input_sha256"])
            assert r["stratum"] == pool["stratum"] and r["instance_sha256"] == pool["input_sha256"]
        for letter, r in (("m", m), ("k", k)):
            assert (r["run_id"], r["slot"], r["status"]) == (
                pool[letter+"_run_id"], pool[letter+"_slot"], pool[letter+"_status"])
        assert isclose(float(pool["m_pool_paid_s"]), float(pool["k_pool_paid_s"]), abs_tol=1e-9)
        order = "K_first" if int(k["slot"]) < int(m["slot"]) else "M_first"
        counts[m["map"], order] += 1
        c_first = int(c["slot"]) < min(int(k["slot"]), int(m["slot"]))
        assert c_first or int(c["slot"]) > max(int(k["slot"]), int(m["slot"]))
        record = {"map": m["map"], "stratum": m["stratum"], "seed": int(m["seed"]), "order": order,
                  "C_before_MK": c_first, "M_slot": int(m["slot"]), "K_slot": int(k["slot"]),
                  "C_slot": int(c["slot"]), "M_status": m["status"], "K_status": k["status"], "C_status": c["status"]}
        if m["status"] != "valid" or k["status"] != "valid":
            skipped.append(record)
            continue
        lengths = {"M_start": int(pool["m_selected_length"]), "K_start": int(pool["k_selected_length"]),
                   "M_final": int(m["checked_length"]), "K_final": int(k["checked_length"])}
        m_start, k_start, m_final, k_final = (lengths[k] for k in ("M_start", "K_start", "M_final", "K_final"))
        same_hash = pool["m_selected_sha256"] == pool["k_selected_sha256"]
        assert k_start <= m_start and (not same_hash or m_start == k_start)
        effect = ppm(k_final, m_final)
        source_pair = recorded["K_new/M_new", m["map"], m["seed"]]
        assert int(source_pair["trial_length"]) == k_final and int(source_pair["reference_length"]) == m_final
        assert isclose(effect, float(source_pair["reduction_ppm"]), abs_tol=1e-9)
        time_m, time_k = time[m["run_id"],], time[k["run_id"],]
        assert time_m["native_process_started"] == time_k["native_process_started"] == "True"
        launch_delay = float(time_k["native_launch_charged_s"]) - float(time_m["native_launch_charged_s"])
        gain_m, gain_k = m_start - m_final, k_start - k_final
        final_den = (m_start - k_start)*1_000_000/m_final
        gain_den = (gain_k - gain_m)*1_000_000/m_final
        assert isclose(effect, final_den + gain_den, abs_tol=1e-9)
        record.update(lengths, start_relation=("shorter" if k_start < m_start else "same_sha256" if same_hash else "equal_length_distinct_sha256"),
                      start_advantage_ppm=ppm(k_start, m_start), final_advantage_ppm=effect,
                      final_relation=("shorter" if k_final < m_final else "longer" if k_final > m_final else "tied"),
                      M_own_start_gain_ppm=ppm(m_final, m_start), K_own_start_gain_ppm=ppm(k_final, k_start),
                      start_advantage_on_M_final_ppm=final_den, K_minus_M_phase_gain_on_M_final_ppm=gain_den,
                      M_native_launch_charged_s=float(time_m["native_launch_charged_s"]),
                      K_native_launch_charged_s=float(time_k["native_launch_charged_s"]),
                      K_minus_M_launch_s=launch_delay,
                      M_launch_to_job_zero_s=float(time_m["launch_to_observed_job_zero_s"]),
                      K_launch_to_job_zero_s=float(time_k["launch_to_observed_job_zero_s"]),
                      M_start_sha256=pool["m_selected_sha256"], K_start_sha256=pool["k_selected_sha256"],
                      continuation_seed=int(pool["continuation_seed"]))
        dataset.append(record)
    assert len(counts) == 40 and set(counts.values()) == {5}
    assert len(dataset) == 198 and len(skipped) == 2
    assert len([r for r in raw["pairs"] if r["comparison"] == "K_new/M_new"]) == len(dataset)
    return dataset, skipped


def quality(rows):
    tally = Counter(r["final_relation"] for r in rows)
    data = {"pairs": len(rows), "maps": unique_len(rows, "map"), "shorter": tally["shorter"],
            "tied": tally["tied"], "longer": tally["longer"]}
    for field in ("start_advantage_ppm", "final_advantage_ppm", "M_own_start_gain_ppm", "K_own_start_gain_ppm",
                  "start_advantage_on_M_final_ppm", "K_minus_M_phase_gain_on_M_final_ppm",
                  "K_minus_M_launch_s", "M_launch_to_job_zero_s", "K_launch_to_job_zero_s"):
        data["pair_mean_"+field] = mean(r[field] for r in rows)
        data["map_equal_mean_"+field] = map_mean(rows, field)
    for field in ("start_advantage_ppm", "final_advantage_ppm"):
        data["pair_median_"+field] = median(r[field] for r in rows)
    return data


def order_stats(rows):
    order_map = grouped(rows, lambda row: row["map"])
    output = []
    for map_id, values in sorted(order_map.items()):
        groups = grouped(values, lambda row: row["order"])
        assert set(groups) == {"K_first", "M_first"}
        row = {"map": map_id, "stratum": values[0]["stratum"]}
        for order in ("K_first", "M_first"):
            selected = groups[order]
            row[order + "_n"] = len(selected)
            row[order + "_ppm"] = mean(v["final_advantage_ppm"] for v in selected)
            row[order + "_C_before_n"] = sum(v["C_before_MK"] for v in selected)
        row["K_first_minus_M_first_ppm"] = row["K_first_ppm"] - row["M_first_ppm"]
        output.append(row)
    contrast = [row["K_first_minus_M_first_ppm"] for row in output]
    summary = {"K_first": quality([r for r in rows if r["order"] == "K_first"]),
               "M_first": quality([r for r in rows if r["order"] == "M_first"]),
               "mean_difference_ppm": mean(contrast), "median_difference_ppm": median(contrast),
               "maps_positive": sum(d > 0 for d in contrast), "maps_negative": sum(d < 0 for d in contrast),
               "map_sign_flip": exact_sign_flip(contrast)}
    for order in ("K_first", "M_first"):
        summary[order]["C_before_MK_n"] = sum(r["C_before_MK"] for r in rows if r["order"] == order)
    return output, summary


def csv_out(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def effects_against_c(raw):
    joined = index(raw["design"], "map", "pool_seed", "method")
    result = {}
    for method in ("M_new", "K_new"):
        pairs = [row.copy() for row in raw["pairs"] if row["comparison"] == method + "/C_ref"]
        for r in pairs:
            r["ppm"] = float(r["reduction_ppm"])
            slots = {m: int(joined[r["map"], r["seed"], m]["slot"]) for m in ("M_new", "K_new", "C_ref")}
            r["position_in_MK"] = "first" if slots[method] < slots["K_new" if method == "M_new" else "M_new"] else "second"
            r["position_relative_C"] = "before_C" if slots[method] < slots["C_ref"] else "after_C"
        result[method] = {
            key: {group: {"pairs": len(values), "maps": unique_len(values, "map"), "map_equal_mean_ppm": map_mean(values, "ppm")}
                  for group, values in grouped(pairs, lambda r: r[key]).items()}
            for key in ("position_in_MK", "position_relative_C")
        }
    return result


def make_figures(output, rows, maps):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    colors = dict(zip(STRATA, COLORS))
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False,
                         'pdf.fonttype': 42, 'svg.fonttype': 'none'})
    shorter = [row for row in rows if row['start_relation'] == 'shorter']
    identical = [row for row in rows if row['start_relation'] == 'same_sha256']
    assert len(shorter) == 181 and len(identical) == 17 and len(rows) == 198
    same_ties = [row for row in identical if row['final_relation'] == 'tied']
    same_losses = [row for row in identical if row['final_relation'] == 'longer']
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4), layout='constrained')
    for axis in axes:
        for strata, values in sorted(grouped(shorter, lambda row: row["stratum"]).items()):
            axis.scatter([row["start_advantage_ppm"] for row in values], [row["final_advantage_ppm"] for row in values],
                         c=colors[strata], s=19, edgecolors='white', linewidths=.25, alpha=.78, label=STRATA[strata])
        axis.scatter([row['start_advantage_ppm'] for row in identical], [row['final_advantage_ppm'] for row in identical],
                     s=33, facecolors='white', edgecolors='0.16', linewidths=.85, label='Byte-identical start', zorder=5)
        axis.axhline(0, color='0.37', lw=.85)
        axis.axvline(0, color='0.75', lw=.65)
        axis.set_xlabel('K start reduction relative to M start (ppm)')
        axis.grid(alpha=.24)
    axes[0].set_ylabel('K final reduction relative to M final (ppm)')
    axes[0].set_title('(a) All 198 valid pairs', loc='left')
    axes[1].set_title('(b) Central view of the same data', loc='left')
    axes[1].set_ylim(-350, 350)
    axes[1].legend(frameon=False, loc='upper right')
    note = {'arrowprops': {'arrowstyle': '-', 'color': '0.32', 'lw': .75}, 'textcoords': 'axes fraction',
            'fontsize': 8, 'bbox': {'fc': 'white', 'ec': 'none', 'pad': .8}, 'zorder': 7}
    axes[1].annotate(f'{len(same_ties)} coincident ties', xy=(0, 0), xytext=(.12, .88), **note)
    axes[1].annotate(f'{len(same_losses)} near-coincident\none-unit losses', xy=(0, same_losses[0]['final_advantage_ppm']),
                     xytext=(.15, .21), **note)
    for r in sorted(rows, key=lambda row: row["final_advantage_ppm"])[:3]:
        axes[0].annotate(f'{r["map"].split(".seed")[0]}/{r["seed"]}', (r["start_advantage_ppm"], r["final_advantage_ppm"]),
                         xytext=(8, 2), textcoords='offset points', fontsize=8)
    for ext in ('svg', 'pdf', 'png'):
        fig.savefig(output / f'cmk_start_vs_finish.{ext}', dpi=300)
    plt.close(fig)

    ordered = sorted(maps, key=lambda row: (row['stratum'], row['map']))
    assert len(ordered) == 20
    differences = [row['K_first_minus_M_first_ppm'] for row in ordered]
    equal_mean = mean(differences)
    fig, (points, contrasts) = plt.subplots(1, 2, sharey=True, figsize=(11, 7.1), layout='constrained', width_ratios=(1.08, .92))
    for idx, row in enumerate(ordered):
        lvalue, rvalue = row['M_first_ppm'], row['K_first_ppm']
        shade = colors[row['stratum']]
        diff = differences[idx]
        assert isclose(diff, rvalue - lvalue, abs_tol=1e-10)
        points.plot([lvalue, rvalue], [idx, idx], color=shade, lw=1.05, alpha=.51)
        points.scatter(lvalue, idx, facecolors='white', edgecolors=shade, marker='o', s=39, zorder=3)
        points.scatter(rvalue, idx, c=[shade], marker='D', s=29, zorder=4)
        contrasts.hlines(idx, min(0, diff), max(0, diff), color=shade, alpha=.36, lw=.85)
        contrasts.scatter(diff, idx, color=shade, s=29, zorder=3)
    points.set_yticks(range(len(ordered)), [f'{STRATA[row["stratum"]]} / {row["map"]}' for row in ordered])
    points.set_ylim(len(ordered) + .45, -.65)
    for axis in (points, contrasts):
        axis.axvline(0, color='0.35', lw=.75)
        axis.grid(axis='x', alpha=.26)
        for y in (4.5, 9.5, 14.5):
            axis.axhline(y, color='0.85', lw=.55)
    contrasts.axvline(equal_mean, color='#161616', lw=1.1, ls='--', label=f'Equal-map mean: {equal_mean:+.2f} ppm')
    contrasts.tick_params(axis='y', left=False)
    points.set_xlabel('K final reduction relative to M (ppm)')
    contrasts.set_xlabel('K first minus M first (ppm)')
    points.set_title('(a) Within-map effect by order', loc='left')
    contrasts.set_title('(b) Paired map differences', loc='left')
    points.legend(handles=[Line2D([], [], color='0.25', marker='o', fillstyle='none', linestyle='none', label='M first'),
                           Line2D([], [], color='0.25', marker='D', linestyle='none', label='K first')],
                  frameon=False, loc='lower left', ncol=2)
    contrasts.legend(frameon=False, loc='lower right')
    for ext in ('svg', 'pdf', 'png'):
        fig.savefig(output / f'cmk_order_sensitivity.{ext}', dpi=300)
    plt.close(fig)


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', type=Path, default=here.parent.parent,
                        help='Root of the corresponding-author review package with the frozen input CSVs.')
    parser.add_argument('--output', type=Path, default=here / 'results')
    parser.add_argument('--no-plot', action='store_true', help='Write tables and summaries with only the Python standard library.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = {name: keyed_csv(args.package_root / relative) for name, relative in INPUTS.items()}
    rows, skipped = crosscheck(raw)
    by_map, orders = order_stats(rows)
    strata_order = []
    strata_start = []
    for name, subset in sorted(grouped(rows, lambda row: row['stratum']).items()):
        _, details = order_stats(subset)
        strata_order.append({'stratum': name, 'maps': unique_len(subset, 'map'),
                             'K_first_n': details['K_first']['pairs'], 'M_first_n': details['M_first']['pairs'],
                             'K_first_ppm': details['K_first']['map_equal_mean_final_advantage_ppm'],
                             'M_first_ppm': details['M_first']['map_equal_mean_final_advantage_ppm'],
                             'K_first_minus_M_first_ppm': details['mean_difference_ppm'],
                             'maps_positive': details['maps_positive'], 'maps_negative': details['maps_negative']})
        strata_start.append({'stratum': name, 'K_shorter_start_n': sum(r['start_relation'] == 'shorter' for r in subset), **quality(subset)})
    dropped = [r for r in rows if abs(r['final_advantage_ppm']) >= FILTER_PPM]
    trimmed = [r for r in rows if abs(r['final_advantage_ppm']) < FILTER_PPM]
    _, trim_order = order_stats(trimmed)
    leave_one = [{'omitted_map': row['map'], 'order_contrast_ppm': mean(
        other['K_first_minus_M_first_ppm'] for other in by_map if other['map'] != row['map'])} for row in by_map]
    subsets = {group: quality(values) for group, values in grouped(rows, lambda row: row['start_relation']).items()}
    all_quality = quality(rows)
    source = {name: {'path': relative, 'sha256': hashlib.sha256((args.package_root/relative).read_bytes()).hexdigest()}
              for name, relative in INPUTS.items()}
    summary = {'scope': 'Exploratory secondary analyses. The registered all-valid-pair K/M comparison remains the primary estimate.',
               'scope_metrics': {'executed': 600, 'valid': 596, 'total_groups': 200, 'valid_MK_pairs': 198, 'maps': 20},
               'inputs': source, 'all_valid_quality': all_quality, 'start_relation_subsets': subsets, 'order_all': orders,
               'conditional_permutation_sensitivity': conditional_permutation(rows, orders['mean_difference_ppm']),
               'all_tails_abs_ge_1000_ppm': [{'map': r['map'], 'seed': r['seed'], 'order': r['order'],
                                               'start_ppm': r['start_advantage_ppm'], 'final_ppm': r['final_advantage_ppm']}
                                              for r in sorted(dropped, key=lambda row: row['final_advantage_ppm'])],
               'post_hoc_abs_lt_1000_ppm_only': trim_order, 'leave_one_map_order': leave_one,
               'exploratory_position_against_C': effects_against_c(raw), 'missing_MK_pairs': skipped,
               'same_start_non_ties': [r for r in rows if r['start_relation'] == 'same_sha256' and r['final_relation'] != 'tied'],
               'notes': [
                   'Group by original slot order. Plan checks verify five K-first and five M-first assignments on every map. Select only pairs with two valid results.',
                   'Order means aggregate seeds within each map and weight the 20 fixed maps equally. The sign-flip test assumes independent exchangeable map-level contrast signs under the exploratory null. P-values are unadjusted and hypothesis-generating.',
                   'Pair-weighted and map-equal means are both reported with explicit field prefixes. Subsets with fewer represented maps have different denominators.',
                   'Start advantage uses M initial length. Final advantage uses M final length. Phase gain uses each arm own initial length. On the common M-final denominator, initial difference plus incremental phase gain difference equals the final effect arithmetically.',
                   'Identical start hashes and seeds control two inputs. Wall time, background load, numerical scheduling and environmental state are not controlled in this comparison. Hardware telemetry needed to isolate thermal throttling was not logged.',
                   'The absolute 1000-ppm sensitivity was selected after inspecting the original outcomes. Tail pairs remain in the registered analysis. Endpoint lengths alone do not identify a local-basin mechanism.',
               ]}
    csv_out(args.output / 'start_end_pairs.csv', rows)
    csv_out(args.output / 'order_by_map.csv', by_map)
    csv_out(args.output / 'order_by_stratum.csv', strata_order)
    csv_out(args.output / 'start_end_by_stratum.csv', strata_start)
    csv_out(args.output / 'start_end_by_map.csv', [
        {'map': key, 'stratum': values[0]['stratum'], 'K_shorter_start_n': sum(r['start_relation'] == 'shorter' for r in values), **quality(values)}
        for key, values in sorted(grouped(rows, lambda r: r['map']).items())
    ])
    csv_out(args.output / 'order_leave_one_map.csv', leave_one)
    csv_out(args.output / 'tail_pairs.csv', sorted(dropped, key=lambda row: row['final_advantage_ppm']))
    csv_out(args.output / 'missing_MK_pairs.csv', skipped)
    (args.output / 'exploratory_summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    if not args.no_plot:
        make_figures(args.output, rows, by_map)
    print(f"198 pairs audited. {'Tables only' if args.no_plot else 'Tables and graphics'} written to {args.output}.")


if __name__ == '__main__':
    main()
