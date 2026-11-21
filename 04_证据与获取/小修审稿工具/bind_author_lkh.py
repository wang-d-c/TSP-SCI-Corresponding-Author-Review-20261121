"""Prepare a static common-LKH binding for review. This module starts no processes."""

import argparse
import hashlib
import json
from pathlib import Path


AUTHOR_ARCHIVE_SHA256 = "632567cce753a89448920b330e39326f8aca2ca97b9c25342025122face1bd1d"
SHARED_ENGINE_SHA256 = "d239bf79873b085ae2d246812b0237af74f6d6b97c413490ea9ac9f8b295d665"
PAIR_NAMES = ("P1/P2", "P1/P3", "P2/P3")
COMMON = {
    "PROBLEM_FILE": "problem.tsp",
    "OUTPUT_TOUR_FILE": "tours/tour_$.tour",
    "CANDIDATE_SET_TYPE": "POPMUSIC",
    "POPMUSIC_MAX_NEIGHBORS": 5,
    "POPMUSIC_SAMPLE_SIZE": 10,
    "POPMUSIC_SOLUTIONS": 25,
    "POPMUSIC_TRIALS": 1,
    "POPMUSIC_INITIAL_TOUR": "NO",
    "MAX_CANDIDATES": 5,
    "SUBGRADIENT": "NO",
    "MOVE_TYPE": 5,
    "SUBSEQUENT_MOVE_TYPE": 5,
    "BACKTRACKING": "NO",
    "PATCHING_A": 1,
    "PATCHING_C": 0,
    "STOP_AT_OPTIMUM": "NO",
    "TRACE_LEVEL": 1,
    "GAIN_CRITERION": "YES",
    "PRECISION": 100,
    "SCALE": 1,
    "RECOMBINATION": "GPX2",
    "POPULATION_SIZE": 0,
    "MAX_TRIALS": 100000,
    "RUNS": 1,
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def parameter_sets(base_seed: int) -> dict:
    if not 1 <= base_seed <= 2**31 - 3001:
        raise ValueError("seed and registered offsets must fit the positive signed int range")
    roles = {"C_ref": dict(COMMON, SEED=base_seed)}
    roles.update({f"P{i + 1}": dict(COMMON, SEED=base_seed + 1000 * i) for i in range(3)})
    common_resume = dict(COMMON, SEED=base_seed + 3000,
                         INITIAL_TOUR_FILE="start.tour", INITIAL_TOUR_FRACTION=1)
    roles["M_new_resume"] = common_resume.copy()
    roles["K_new_resume"] = common_resume.copy()
    return roles


def serialize(parameters: dict) -> str:
    return "".join(f"{name} = {value}\n" for name, value in parameters.items()) + "EOF\n"


def bind(archive: Path, binary: Path, problem: Path, input_sha256: str,
         seed: int, output: Path) -> dict:
    roles = parameter_sets(seed)
    for item, required in ((archive, AUTHOR_ARCHIVE_SHA256), (binary, SHARED_ENGINE_SHA256),
                           (problem, input_sha256.lower())):
        if digest(item) != required:
            raise ValueError(f"input hash mismatch for {item.name}")
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for role, parameters in roles.items():
        path = output / f"{role}.par"
        path.write_bytes(serialize(parameters).encode("ascii"))
        files[role] = {"parameters": path.name, "parameters_sha256": digest(path),
                       "executable_sha256": SHARED_ENGINE_SHA256, "seed": parameters["SEED"]}
    receipt = {
        "status": "static_candidate_only", "solver_processes_started": 0,
        "archive_sha256": AUTHOR_ARCHIVE_SHA256, "engine_sha256": SHARED_ENGINE_SHA256,
        "problem_file": problem.name, "problem_sha256": input_sha256.lower(),
        "roles": files, "shared_physical_parent_pool": ["P1", "P2", "P3"],
        "start_binding": {"M_new_resume": "best certified parent",
                          "K_new_resume": "best certified parent or eligible GPX2 offspring"},
        "K_new_additional_pair_order": PAIR_NAMES,
        "formal_environment_must_omit": ["TSP_ABLATION_OMIT_INITIAL_EDGES"],
        "deadlines_s": {"request_stop": 85, "prove_stop_strictly_before": 86,
                        "certify_delivery_strictly_before": 88, "complete_cleanup_strictly_before": 90},
        "full_pool_charge_per_arm": True,
    }
    (output / "binding.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--problem", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    bind(**vars(parser.parse_args()))


if __name__ == "__main__":
    main()
