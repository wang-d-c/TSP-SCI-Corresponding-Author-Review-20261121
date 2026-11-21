"""Replay frozen EAX evidence and verify an isolated decimal callback candidate.

No launcher is imported or invoked. This writes only a new local audit receipt.
"""
from __future__ import annotations

import ast
from collections import Counter
from contextlib import contextmanager
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

from decimal_eax_candidate import (
    install_inner_callbacks, parse_coordinates, validate_eax_natural_result, validate_tour,
)


HERE = Path(__file__).resolve().parent
OUTPUTS = HERE.parents[1]
REVIEW = OUTPUTS / "tsp_review_execution_20261120"
MAIN = REVIEW / "phase_b_common_r3/formal"
NUMERIC = REVIEW / "phase_b_numeric"
CONTROL = REVIEW / "phase_b_control"
LINKED_WRAPPER = OUTPUTS / "lkh_v24_3_confirmation_20261116/formal_216/external_v3/EAX_WRAPPER_V2_R2_a06.py"
RECOVERY = OUTPUTS / "lkh_v24_local_20261116/recovery_r1"
PLAN = REVIEW / "phase_b_design/主实验800_候选账本.csv"
MODEL = NUMERIC / "final_panel_distance_model_binding.csv"
PANEL_INPUTS = REVIEW / "phase_b_instances/local_input_bytes_not_redistributable"
NATIVE_SHA = "db5e3f8d938aeb22d2d7d09a9218256b6e061b2c0149cf94e950bb407cff65a9"
OBSERVER_SHA = "57fe7ec2035eb0946d8f24a581ba354a20b5f7c43bb148f0dc13e977db9bd7cf"


def require(condition, label):
    if not condition:
        raise ValueError(label)


def sha(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def structured(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def load_exact_verifier():
    spec = importlib.util.spec_from_file_location("frozen_exact_verifier", NUMERIC / "euc2d_verify.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def extracted_function(path, name):
    # Compare the exact legacy source without importing modules with execution hooks.
    source = path.read_text(encoding="utf-8-sig")
    function, = [function for function in ast.parse(source).body if isinstance(function, ast.FunctionDef)
                 and function.name == name]
    locals_by_name = {"Decimal": Decimal, "InvalidOperation": InvalidOperation,
                      "Path": Path, "re": re, "require": require}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), locals_by_name)
    return locals_by_name[name]


@contextmanager
def expected_failure():
    try:
        yield
    except ValueError:
        return
    raise AssertionError("unexpected acceptance of invalid evidence")


def test_decimal_boundary():
    instance = "TYPE: TSP\nDIMENSION: 3\nEDGE_WEIGHT_TYPE: EUC_2D\nNODE_COORD_SECTION\n1 0 0\n2 2.499999999999999999 0\n3 5 0\nEOF\n"
    route = b"TYPE: TOUR\nDIMENSION: 3\nCOMMENT: Length = 10\nTOUR_SECTION\n1\n2\n3\n-1\nEOF\n"
    coordinates = parse_coordinates(instance)
    require(validate_tour(route, coordinates) == 10, "exact half-distance case")
    with expected_failure():
        validate_tour(route.replace(b"Length = 10", b"Length = 11"), coordinates)
    with expected_failure():
        validate_tour(route.replace(b"2\n3", b"2\n2"), coordinates)
    with expected_failure():
        validate_tour(route.removesuffix(b"EOF\n"), coordinates)
    with expected_failure():
        validate_tour(route + b"1\n", coordinates)
    with expected_failure():
        parse_coordinates(instance.replace("2 2.499999999999999999", "3 2.499999999999999999"))
    with expected_failure():
        parse_coordinates(instance.replace("EUC_2D", "CEIL_2D"))
    with tempfile.TemporaryDirectory(prefix="eax_decimal_non_solving_") as temp:
        natural = Path(temp) / "bestsol"
        natural.write_text("3 10\n1 2 3\n", encoding="ascii")
        require(validate_eax_natural_result(natural, coordinates, 10) == 10, "natural-result exact boundary")
        with expected_failure():
            validate_eax_natural_result(natural, coordinates, 11)
        natural.write_text("3 10\n1 1 2\n", encoding="ascii")
        with expected_failure():
            validate_eax_natural_result(natural, coordinates, 10)
    from types import SimpleNamespace
    wrapper = SimpleNamespace(parse_coordinates=lambda: None, validate_tour=lambda: None,
                              validate_eax_natural_result=lambda: None)
    install_inner_callbacks(wrapper)
    require(wrapper.validate_tour(route, wrapper.parse_coordinates(instance)) == 10, "callback installation failed")


def review_engineering(exact):
    replayed = []
    for name in ("S1", "L1", "L2", "L3"):
        attempt = CONTROL / "q" / name
        review = structured(attempt / "qualification.json")
        for relative_file, digest in review["evidence_hashes"].items():
            require(sha(attempt / relative_file) == digest, f"{name}: evidence digest changed")
        binding = structured(attempt / "binding.json")
        require(binding["native_sha256"] == NATIVE_SHA and binding["wrapper_sha256"] == OBSERVER_SHA,
                f"{name}: wrong historical runtime")
        record = {k: review[k] for k in ("status", "outer_state", "stop_request_s", "complete_stop_proof",
                                         "candidate_ledger_complete", "published", "consumed", "selected_length",
                                         "commit_s", "cleanup_s")}
        if record["status"] == "passed_engineering_only":
            raw = structured(attempt / "independent_validation.json")
            route = Path(raw["route"])
            source = attempt / "w/input.tsp"
            expected = int(raw["length"])
            independent = exact.verify(exact.read_problem(source), route, expected=expected)
            verified = validate_tour(route.read_bytes(), parse_coordinates(source.read_text(encoding="utf-8-sig")))
            require(verified == expected and independent["tour_sha256"] == raw["route_sha256"],
                    f"{name}: route proof mismatch")
            proof, = review["stop_proof"]
            require(proof["status"] == "passed" and proof["job_zero_observed_s"] < 86, f"{name}: wrong stop proof")
            record["job_zero_observed_s"] = proof["job_zero_observed_s"]
            record["static_decimal_callback_route_replay"] = "passed"
        else:
            record["reason_from_current_raw_qualification"] = review["outer_error"]
        replayed.append({"case": name, **record})
    return replayed


def main():
    if len(sys.argv) != 2 or Path(sys.argv[1]).resolve().parent != HERE:
        raise SystemExit("provide a new audit JSON directly inside this workspace directory")
    destination = Path(sys.argv[1])
    test_decimal_boundary()
    exact = load_exact_verifier()
    state = structured(MAIN / "execution_scope.json")
    plan = rows(PLAN)
    require(sha(PLAN) == state["plan_hashes"]["main"], "planned main rows changed")
    picked = [row for row in plan if row["method"] == "EAX_ref"]
    require(len(plan) == 800 and len(picked) == 200, "EAX cohort count does not match plan")
    require([row["run_id"] for row in picked] == state["deferred_eax_ids"], "deferred run identity changed")
    require(all((row["budget_s"], row["request_at_s"], row["stop_proof_before_s"],
                 row["certify_before_s"], row["cleanup_before_s"]) == ("90", "85.0", "86", "88", "90")
                for row in picked), "candidate row cutoff differs from preregistration")
    require(all(not (MAIN / "main" / f"{int(row['slot']):04d}").exists() for row in picked),
            "existing result directory found for deferred slot")
    matrix = {row["instance"]: row for row in rows(MODEL)}
    keys = Counter(row["map"] for row in picked)
    require(len(keys) == len(matrix) == 20 and set(keys.values()) == {10}, "map-seed balance mismatch")
    old_inner = extracted_function(LINKED_WRAPPER, "parse_coordinates")
    old_outer = extracted_function(RECOVERY / "recovery_registry.py", "coordinates")
    proof_route_rows = {}
    for row in plan:
        slot = MAIN / "main" / f"{int(row['slot']):04d}" / "terminal.json"
        if row["method"] == "C_ref" and row["map"] not in proof_route_rows and slot.is_file():
            terminal = structured(slot)
            if terminal["status"] == "valid":
                proof_route_rows[row["map"]] = terminal["result"]
    cases = []
    for instance, row in matrix.items():
        source = PANEL_INPUTS / f"{instance}.tsp"
        require(sha(source) == row["instance_sha256"], f"{instance}: input digest mismatch")
        require(row["mismatches"] == row["narrowing_errors"] == '0' and
                int(row["pairs"]) == int(row["dimension"]) * (int(row["dimension"]) - 1) // 2,
                f"{instance}: missing native distance comparison")
        require(all(item["n"] == row["dimension"] and item["input_sha256"] == row["instance_sha256"]
                    for item in picked if item["map"] == instance), f"{instance}: plan input mismatch")
        content = source.read_text(encoding="utf-8-sig")
        coords = parse_coordinates(content)
        reference = exact.read_problem(source)
        require(coords.points == reference.points and coords.scale == reference.lattice and
                len(coords) == int(row["dimension"]), f"{instance}: exact coordinate mismatch")
        fractional = any(x % coords.scale or y % coords.scale for x, y in coords.points)
        rejection = {}
        for name, callback, value in (("legacy_inner", old_inner, content), ("legacy_outer", old_outer, source)):
            try:
                callback(value)
            except ValueError as error:
                rejection[name] = str(error)
        if fractional:
            require(len(rejection) == 2, f"{instance}: fractional blocker not reproduced")
        historical_route = proof_route_rows[instance]
        tour = Path(historical_route["route"])
        expected = int(historical_route["length"])
        counterproof = exact.verify(reference, tour, expected=expected)
        require(validate_tour(tour.read_bytes(), coords) == expected and
                counterproof["tour_sha256"] == historical_route["route_sha256"], f"{instance}: frozen route recounted differently")
        cases.append({"instance": instance, "dimension": len(coords), "input_sha256": row["instance_sha256"],
                      "fractional_coordinates": fractional, "legacy_inner_rejected": "legacy_inner" in rejection,
                      "legacy_outer_rejected": "legacy_outer" in rejection, "frozen_route_cost_replay": "matched",
                      "independent_model_pairs_in_prior_receipt": int(row["pairs"])})
    native = Path(structured(OUTPUTS / "lkh_v24_3_confirmation_20261116/formal_216/r4/eax/binary_binding.json")["path"])
    require(sha(native) == NATIVE_SHA, "frozen EAX PE changed")
    require(sha(CONTROL / "eax_observer_85.py") == OBSERVER_SHA, "85-s prototype changed")
    receipt = {"scope": "static_decimal_callback_replay_only", "solver_runs_started": 0,
               "formal_eax_slots_started": 0, "formal_eax_quality_results": 0,
               "main_plan_sha256": sha(PLAN), "first_deferred_original_run_id": picked[0]["run_id"],
               "deferred_slots": len(picked), "native_sha256_unchanged": sha(native),
               "isolated_callback_sha256": sha(HERE / "decimal_eax_candidate.py"),
               "old_wrapper_sha256": sha(LINKED_WRAPPER),
               "matched_existing_routes": len(cases), "engineered_proof_replays": review_engineering(exact),
               "frozen_input_checks": cases, "fractional_inputs": sum(row["fractional_coordinates"] for row in cases),
               "gate": "historical_engineering_integer_only; formal_adapter_and_task_sheet_required",
               "risk": "integration must replace all three legacy recount seams without weakening timed and publication proofs"}
    with destination.open('x', encoding='utf-8') as target:
        json.dump(receipt, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps({k: v for k, v in receipt.items() if not isinstance(v, (list, dict))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
