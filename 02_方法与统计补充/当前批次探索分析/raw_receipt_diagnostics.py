"""Audit dispatch order, starts, and disjoint charged intervals in the saved R3 receipts."""

import argparse
import csv
import hashlib
import json
import random
import re
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import datetime
from math import isclose
from pathlib import Path
from statistics import mean, median


EPOCH_PATHS = ["launch_a01.json", "disk_full_resume_a01/launch_a02.json", "paging_resume_r1/launch.json",
               "memory_resume_r1/launch.json", "memory_resume_r2/launch.json"]
DISK_FULL = "formal/recovery_slot0012_disk_full.json"
BUDGET_EXIT = 0xE0000001
IMPROVEMENT_PATTERN = re.compile(r"^\*\s*(\d+):\s*Cost\s*=\s*(\d+),\s*Time\s*=\s*([\d.]+)\s*sec\.", re.M)
PLAN = "04_证据与获取/原始证据/phase_b_design/主实验800_候选账本.csv"
DESIGN_RECEIPT = "04_证据与获取/原始证据/phase_b_design/design_receipt.json"
PANEL = "04_证据与获取/地图历史证据/phase_b_instances/preformal_panel_disposition.csv"


def json_read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def csv_read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_write(path, rows):
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc(timestamp):
    return datetime.fromisoformat(timestamp).timestamp() if timestamp else None


def time_diff(after, before):
    return after - before if after is not None and before is not None else None


def metrics(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": mean(values), "median": median(values), "min": min(values), "max": max(values)}


def replay_main_plan(package, actual):
    """Independently replay shuffle calls in source freeze_candidate_design.py."""
    receipt = json_read(package / DESIGN_RECEIPT)
    assert digest(package / PANEL) == receipt["input_ledger_sha256"]
    assert receipt["order_seed"] == 20261120
    maps = sorted([row for row in csv_read(package / PANEL) if row["candidate_role"] == "primary_provisional"],
                  key=lambda row: (row['stratum'], int(row['stratum_order'])))
    rng = random.Random(receipt["order_seed"])
    rng.shuffle(maps)
    groups = []
    for row in maps:
        assigned = [False] * 5 + [True] * 5
        rng.shuffle(assigned)
        for seed, k_first in zip(receipt["selected_main_seed_labels"], assigned, strict=True):
            pair = ('K_new', 'M_new') if k_first else ('M_new', 'K_new')
            blocks = [('C_ref',), pair, ('EAX_ref',)]
            rng.shuffle(blocks)
            groups.append((row['instance'], seed, k_first, [m for b in blocks for m in b]))
    rng.shuffle(groups)
    plan = csv_read(package / PLAN)
    recreated = [(m, str(seed), method, str(i)) for m,seed,_,methods in groups for i,method in enumerate(methods,1)]
    assert len(recreated) == 800
    assert [(r['map'],r['pool_seed'],r['method'],r['within_group']) for r in plan] == recreated
    assert [(r['map'],r['seed'],r['method'],r['slot']) for r in actual] == [
        (r['map'],r['pool_seed'],r['method'],r['slot']) for r in plan if r['method'] != 'EAX_ref']
    return receipt, groups


def canonical_tour(data, dimension):
    section, cities = False, []
    for line in data.decode("utf-8-sig").splitlines():
        if not section:
            section = line.strip() == "TOUR_SECTION"
            continue
        if line.strip() in ("-1", "EOF"):
            break
        cities.extend(int(word) for word in line.split())
    assert section and len(cities) == dimension and set(cities) == set(range(1, dimension + 1))
    start = cities.index(1)
    forward = cities[start:] + cities[:start]
    return min(forward, [1] + list(reversed(forward[1:])))


def receipt_for_arm(r3, raw, dispatch, epoch):
    loc = r3 / "formal/main" / f"{int(raw['slot']):04d}"
    terminal_path = loc / "terminal.json"
    if not terminal_path.exists() and raw['failure_cause'] == 'disk_full':
        terminal_path = r3 / DISK_FULL
    terminal = json_read(terminal_path)
    assert digest(terminal_path) == raw["terminal_sha256"], raw["run_id"]
    assert terminal["dispatch_sha256"] == digest(loc / "dispatch.json"), raw["run_id"]
    assert dispatch["row"]["run_id"] == terminal["row"]["run_id"] == raw["run_id"]
    assert terminal["status"] == raw["status"]
    result = terminal["result"]
    monitor = result.get("monitor", {})
    admission = monitor.get("admission", {})
    native = result.get("native", {})
    job = native.get("job", {}).get("final_job", {})
    parent_seen = next((p["parent_pid"] for p in native.get("job", {}).get("processes", [])
                        if p["pid"] == native["root_pid"]), None)
    if raw["status"] == "valid":
        assert parent_seen == epoch["pid"], raw["run_id"]
        assert result["length"] == int(raw["checked_length"]) and result["route_sha256"] == raw["route_sha256"]
        assert native["status"] == "passed" and monitor["status"] == "passed"
        assert native["returncode"] in (0, BUDGET_EXIT)
        assert native["terminated_for_budget"] == (native["returncode"] == BUDGET_EXIT)
    stage = {
        "slot": int(raw["slot"]), "run_id": raw["run_id"], "method": raw["method"],
        "map": raw["map"], "seed": int(raw["seed"]), "status": raw["status"],
        "epoch": epoch["name"], "controller_pid": epoch["pid"], "root_parent_pid_verified": parent_seen,
        "dispatch_time": dispatch["time"], "terminal_time": terminal.get("time"),
        "dispatch_to_terminal_wall_s": time_diff(utc(terminal.get("time")), utc(dispatch["time"])),
        "common_paid_s": result.get("common_paid_s"), "controller_finished_monotonic": result.get("completion_observed_monotonic"),
        "entered_arm_monotonic": result["charged_origin_monotonic"] + result["common_paid_s"]
        if raw["status"] == "valid" else None,
        "available_physical_at_admission_bytes": admission.get("available_physical_bytes"),
        "minimum_available_physical_bytes": monitor.get("minimum_available_bytes"),
        "peak_system_commit_bytes": monitor.get("peak_system_commit_bytes"), "ac_power": admission.get("ac_power"),
        "solver_cpu": admission.get("solver_cpu"), "sampler_cpu": admission.get("sampler_cpu"),
        "paging_samples": monitor.get("paging_samples"), "monitor_status": monitor.get("status"),
        "job_cpu_s": job.get("job_cpu_s"), "job_peak_commit_bytes": job.get("peak_job_memory_used_bytes"),
        "job_active_at_stop": job.get("job_active_processes"),
        "native_budget_terminated": native.get("terminated_for_budget"), "native_returncode": native.get("returncode"),
    }
    return stage, result


def disjoint_cost(stage, result):
    native = result["native"]
    marks = [0.0, stage["common_paid_s"], native["native_launch_s"],
             native["lifetime_proof"]["job_zero_observed_s"], native["cleanup_s"], result["delivered_s"], result["full_charge_s"]]
    assert marks == sorted(marks), stage["run_id"]
    child_spans, child_launch_to_zero, child_zero_to_verified = [], [], []
    for call in result.get("gpx_calls", []):
        child_native = call["native"]
        child_span = [child_native["native_launch_s"], child_native["lifetime_proof"]["job_zero_observed_s"], call["verified_s"]]
        assert child_span == sorted(child_span)
        assert marks[1] <= child_span[0] <= child_span[-1] <= marks[2]
        if child_spans:
            assert child_spans[-1][1] <= child_span[0], stage["run_id"]
        child_spans.append((child_span[0], child_span[-1]))
        child_launch_to_zero.append(child_span[1] - child_span[0])
        child_zero_to_verified.append(child_span[2] - child_span[1])
    if stage["method"] == "K_new":
        assert len(child_spans) == 3, stage["run_id"]
    values = {
        "pool_fee_charged_s": marks[1],
        "before_native_launch_residual_s": marks[2] - marks[1] - sum(b-a for a,b in child_spans),
        "GPX_launch_to_job_zero_s": sum(child_launch_to_zero),
        "GPX_job_zero_to_child_verification_s": sum(child_zero_to_verified),
        "LKH_launch_to_observed_job_zero_s": marks[3] - marks[2],
        "LKH_job_zero_to_native_cleanup_s": marks[4] - marks[3],
        "LKH_native_cleanup_to_scored_delivery_s": marks[5] - marks[4],
        "LKH_delivery_to_charged_completion_s": marks[6] - marks[5],
    }
    assert min(values.values()) >= 0
    assert isclose(sum(values.values()), marks[6], abs_tol=1e-10), stage["run_id"]
    assert marks[3] < 86 and marks[5] < 88 and marks[6] < 90
    return {"slot": stage["slot"], "run_id": stage["run_id"], "map": stage["map"], "seed": stage["seed"], "method": stage["method"],
            **values, "full_charge_s": marks[6], "native_launch_on_charged_clock_s": marks[2],
            "native_job_zero_on_charged_clock_s": marks[3], "native_cleanup_on_charged_clock_s": marks[4],
            "scored_delivery_on_charged_clock_s": marks[5]}


def check_starts(r3, pair, runs):
    proof = {"map": pair["map"], "seed": int(pair["seed"]), "order": pair["order"], "final_relation": pair["final_relation"]}
    paths = []
    for arm in ("M", "K"):
        stage, result = runs[int(pair[arm+"_slot"])]
        base = r3 / "formal/main" / f"{stage['slot']:04d}" / "result/resume"
        start_path = base / "start.tour"
        witness = base / "first_trial.tour"
        delivered = base / "delivered.tour"
        paths.append(start_path)
        start_bytes = start_path.read_bytes()
        start_hash = hashlib.sha256(start_bytes).hexdigest()
        assert start_hash == result["initial"]["selected_sha256"] == pair[arm+"_start_sha256"]
        witness_bytes = witness.read_bytes()
        witness_hash = hashlib.sha256(witness_bytes).hexdigest()
        assert witness_hash == result["initial"]["first_tour_sha256"]
        dimension = result["numeric_bounds"]["dimension"]
        assert canonical_tour(start_bytes, dimension) == canonical_tour(witness_bytes, dimension)
        assert digest(delivered) == result["route_sha256"]
        params = base / "run.par"
        assert digest(params) == result["parameter_sha256"]
        source = result.get("source", {})
        stage_receipt = base / "owned/stage_receipt.json"
        assert digest(stage_receipt) == result["completion_evidence"]["native_receipt_sha256"]
        stdout = base / "owned/stdout.log"
        progress = [(int(trial), int(length), float(at)) for trial,length,at in IMPROVEMENT_PATTERN.findall(stdout.read_text("utf-8"))]
        proof.update({arm+"_"+k:v for k,v in {
            "slot": stage["slot"], "start_sha256": start_hash, "first_trial_sha256": witness_hash,
            "start_length": result["initial"]["selected_length"], "end_length": result["length"],
            "final_tour_sha256": result["route_sha256"], "parameter_sha256": digest(params),
            "engine_sha256": result["engine_sha256"], "parent_pool_sha256": result["pool_sha256"],
            "seed": int(result["effective_parameters"]["values"]["SEED"]),
            "actual_initial_cycle_verified": True, "paid_pool_s": stage["common_paid_s"],
            "dispatch_time": stage["dispatch_time"], "epoch": stage["epoch"],
            "launch_s": result["native"]["native_launch_s"], "stop_request_s": result["native"]["stop_request_s"],
            "stop_proof_s": result["native"]["stop_proof_s"], "delivery_s": result["delivered_s"],
            "final_route_first_observed_s": source.get("first_observed_s"), "final_route_file_verified_s": source.get("verified_s"),
            "completion_s": result["full_charge_s"],
            "normal_budget_termination": stage["native_budget_terminated"], "job_exit": stage["native_returncode"],
            "last_logged_improvement_trial": progress[-1][0] if progress else None,
            "last_logged_improvement_cost": progress[-1][1] if progress else None,
            "last_logged_improvement_printed_time_s": progress[-1][2] if progress else None,
            "logged_improvements": len(progress), "stdout_sha256": digest(stdout)
        }.items()})
    assert paths[0].read_bytes() == paths[1].read_bytes()
    assert proof["M_parameter_sha256"] == proof["K_parameter_sha256"]
    assert proof["M_engine_sha256"] == proof["K_engine_sha256"]
    assert proof["M_parent_pool_sha256"] == proof["K_parent_pool_sha256"]
    assert proof["M_seed"] == proof["K_seed"] == int(pair["continuation_seed"])
    proof["start_bytes_equal"] = True
    proof["K_minus_M_launch_s"] = proof["K_launch_s"] - proof["M_launch_s"]
    proof["K_minus_M_length_units"] = proof["K_end_length"] - proof["M_end_length"]
    return proof


def pair_timing(pair, run_map, spans):
    m, k, c = (run_map[int(pair[key+"_slot"])][0] for key in ("M", "K", "C"))
    cost_m, cost_k = spans[m["slot"]], spans[k["slot"]]
    first, second = sorted((m,k), key=lambda stage: utc(stage["dispatch_time"]))
    return {"map": pair["map"], "seed": int(pair["seed"]), "order": pair["order"],
            "stratum": pair["stratum"], "C_before_MK": pair["C_before_MK"],
            "first_slot": first["slot"], "second_slot": second["slot"], "C_slot": c["slot"], "C_status": c["status"],
            "first_epoch": first["epoch"], "second_epoch": second["epoch"],
            "first_MK_predecessor_method": first["preceding_method"], "first_MK_predecessor_slot": first["preceding_slot"],
            "second_MK_predecessor_method": second["preceding_method"], "second_MK_predecessor_slot": second["preceding_slot"],
            "first_dispatch_timestamp": first["dispatch_time"], "second_dispatch_timestamp": second["dispatch_time"],
            "first_dispatch_to_second_dispatch_wall_s": time_diff(utc(second["dispatch_time"]), utc(first["dispatch_time"])),
            "first_terminal_to_second_dispatch_wall_s": time_diff(utc(second["dispatch_time"]), utc(first["terminal_time"])),
            "first_end_to_second_entered_within_epoch_s": time_diff(second['entered_arm_monotonic'], first['controller_finished_monotonic'])
            if first['epoch'] == second['epoch'] else None,
            "first_after_preceding_terminal_wall_s": first["after_preceding_terminal_wall_s"],
            "C_after_its_preceding_terminal_wall_s": c["after_preceding_terminal_wall_s"],
            "M_launch_charged_s": cost_m["native_launch_on_charged_clock_s"],
            "K_launch_charged_s": cost_k["native_launch_on_charged_clock_s"],
            "K_minus_M_launch_charged_s": cost_k["native_launch_on_charged_clock_s"] - cost_m["native_launch_on_charged_clock_s"],
            "M_native_wall_s": cost_m["LKH_launch_to_observed_job_zero_s"],
            "K_native_wall_s": cost_k["LKH_launch_to_observed_job_zero_s"],
            "M_native_job_cpu_s": m["job_cpu_s"], "K_native_job_cpu_s": k["job_cpu_s"],
            "M_minimum_available_physical_bytes": m["minimum_available_physical_bytes"],
            "K_minimum_available_physical_bytes": k["minimum_available_physical_bytes"],
            "K_final_reduction_ppm": float(pair["final_advantage_ppm"])}


def main():
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--r3", type=Path, required=True, help="path to protected original R3 directory")
    p.add_argument("--package-root", type=Path, required=True, help="published R3 review package")
    p.add_argument("--analysis-pairs", type=Path, default=here/"results/start_end_pairs.csv")
    p.add_argument("--output", type=Path, default=here/"evidence_results")
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = csv_read(args.package_root/"03_数据与复算/data/core_600_runs.csv")
    design_receipt, replayed = replay_main_plan(args.package_root, raw)
    pairs = csv_read(args.analysis_pairs)
    epochs = []
    for n, path in enumerate(EPOCH_PATHS, 1):
        reference = args.r3/path
        receipt = json_read(reference)
        epochs.append({"name": f"epoch_{n}", "pid": receipt["pid"], "launch_time": receipt.get("created", receipt.get("creation")),
                       "path_relative_to_R3": path, "sha256": digest(reference)})
    ordered_epochs = [utc(e["launch_time"]) for e in epochs]
    assert ordered_epochs == sorted(ordered_epochs)
    stages, spans, run_map = [], {}, {}
    for row in raw:
        slot = int(row["slot"])
        dispatch = json_read(args.r3/"formal/main"/f"{slot:04d}"/"dispatch.json")
        epoch_id = bisect_right(ordered_epochs, utc(dispatch["time"])) - 1
        stage, result = receipt_for_arm(args.r3, row, dispatch, epochs[epoch_id])
        stages.append(stage)
        run_map[slot] = (stage, result)
        if stage["status"] == "valid":
            spans[slot] = disjoint_cost(stage, result)
    stages.sort(key=lambda r: (utc(r["dispatch_time"]), r["slot"]))
    assert [r["slot"] for r in stages] == sorted(r["slot"] for r in stages)
    preceding = None
    for stage in stages:
        stage.update(preceding_slot=preceding["slot"] if preceding else None,
                     preceding_method=preceding["method"] if preceding else None,
                     preceding_run_id=preceding["run_id"] if preceding else None,
                     preceding_epoch=preceding["epoch"] if preceding else None,
                     preceding_status=preceding["status"] if preceding else None,
                     after_preceding_terminal_wall_s=time_diff(utc(stage["dispatch_time"]), utc(preceding["terminal_time"])) if preceding else None)
        preceding = stage
    paired = [pair_timing(r, run_map, spans) for r in pairs]
    paired_labels = {(r['map'],r['seed']):r['order'] for r in paired}
    seed_balance = []
    for seed in design_receipt['selected_main_seed_labels']:
        row = {'seed':seed}
        for order, first in (('K_first', True), ('M_first', False)):
            row[order+'_planned'] = sum(n == seed and k == first for _,n,k,_ in replayed)
            row[order+'_eligible'] = sum(s == seed and g == order for (_,s),g in paired_labels.items())
        seed_balance.append(row)
    identical_starts = [check_starts(args.r3, r, run_map) for r in pairs if r["start_relation"] == 'same_sha256']
    assert len(paired) == 198 and len(identical_starts) == 17 and len(spans) == 596
    budget_by_method = {}
    for method in ("C_ref", "M_new", "K_new"):
        selected = [v for v in spans.values() if v["method"] == method]
        budget_by_method[method] = {key:metrics([v[key] for v in selected]) for key in selected[0] if key.endswith('_s')}
    selected_groups = defaultdict(list)
    for item in paired:
        selected_groups[item["order"]].append(item)
    timing_by_order = {key: {f: metrics([r[f] for r in selected]) for f in selected[0]
                             if f.endswith('_s') or f.endswith('_bytes')} for key,selected in selected_groups.items()}
    for key, selected in selected_groups.items():
        timing_by_order[key].update({"pair_count":len(selected), "first_MK_predecessor_method": Counter(r["first_MK_predecessor_method"] for r in selected),
                                     "first_MK_by_epoch": Counter(r["first_epoch"] for r in selected),
                                     "cross_epoch_pairs": sum(r["first_epoch"] != r["second_epoch"] for r in selected)})
    for epoch in epochs:
        selection = [r for r in stages if r["epoch"] == epoch["name"]]
        epoch.update({"first_dispatch": selection[0]["dispatch_time"], "last_dispatch": selection[-1]["dispatch_time"],
                      "trial_count": len(selection), "native_parent_pid_matches": sum(r['root_parent_pid_verified'] == epoch['pid'] for r in selection)})
    summary = {
        "registered_slots": len(stages), "valid_cost_decompositions": len(spans), "verified_same_start_pairs": len(identical_starts),
        "order_recreation": {"seed": design_receipt['order_seed'], "identical_full_plan_slots": 800,
                              "identical_executed_non_EAX_slots": 600, "plan_source_sha256": digest(args.package_root/PLAN),
                              "per_map_planned_K_first": 5, "per_map_planned_M_first": 5, "by_seed": seed_balance},
        "epochs": epochs, "missing_terminal_time_slots": [r['slot'] for r in stages if r['terminal_time'] is None],
        "monitor_statuses": dict(Counter(str(r["monitor_status"]) for r in stages)),
        "native_return_codes_valid_runs": dict(Counter(r["native_returncode"] for r in stages if r["status"] == "valid")),
        "ac_power_valid_runs": dict(Counter(str(r["ac_power"]) for r in stages if r["status"] == "valid")),
        "timing_by_order_pair_weighted": timing_by_order, "charged_parts_by_method": budget_by_method,
        "two_same_start_non_ties": [r for r in identical_starts if r["K_minus_M_length_units"]],
        "limits": ["Dispatch and terminal timestamps are wall-clock observations at one-second resolution. Controller epochs derive from stored launch receipts and native root parent PID where available.",
                   "The most recent dispatched formal trial is not necessarily the previous physical workload. Parent-pool construction, controller recoveries, admission delays and other host processes can intervene.",
                   "The milliseconds-scale within-controller gap derives from monotonic completion and entered-arm anchors, only compared within the same controller epoch. Charged timestamps use individual arm origins and are distinct from wall timestamps.",
                   "Charge components sum exactly by construction. All observed spans include operational overhead. The pre-launch residual is unclassified. Overlapped monitor CPU/time and routine parsing are not additionally allocated.",
                   "Monitor receipts record available physical memory, system commit, sampled paging, AC admission and CPU affinity. They do not establish clock frequency, temperature, PL1/PL2 or total completed LKH trials.",
                   "A native last logged improvement index is only a reported marker. Competing physical explanations remain untested."]}
    csv_write(args.output/"dispatch_and_cost_context_600.csv", stages)
    csv_write(args.output/"valid_cost_disjoint_spans_596.csv", list(spans.values()))
    csv_write(args.output/"MK_timing_and_epoch_pairs_198.csv", paired)
    csv_write(args.output/"same_start_bytes_verified_17.csv", identical_starts)
    csv_write(args.output/"order_assignment_balance_by_seed.csv", seed_balance)
    (args.output/"raw_receipt_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(f"{len(stages)} dispatches, {len(spans)} valid timing decompositions and {len(identical_starts)} paired start identities verified.")


if __name__ == '__main__':
    main()
