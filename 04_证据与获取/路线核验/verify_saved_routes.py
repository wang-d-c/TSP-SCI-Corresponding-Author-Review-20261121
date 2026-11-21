"""Independently verify saved R3 EUC_2D routes supplied by a reviewer."""
import argparse
import csv
import json
from pathlib import Path

from euc2d_verify import read_problem, verify


ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maps", type=Path, required=True)
    parser.add_argument("--tours", type=Path, required=True)
    parser.add_argument("--run-id", action="append", help="select one or more known run IDs")
    parser.add_argument("--report", type=Path, help="write a new JSON receipt")
    args = parser.parse_args()
    with (ROOT / "route_manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        ledger = list(csv.DictReader(stream))
    all_ids = {row["run_id"] for row in ledger}
    if len(ledger) != 596 or len(all_ids) != 596:
        parser.error("the frozen route manifest must contain 596 unique runs")
    if args.run_id:
        chosen = set(args.run_id)
        if missing := chosen - all_ids:
            parser.error(f"unknown run ID: {', '.join(sorted(missing))}")
        ledger = [row for row in ledger if row["run_id"] in chosen]
    problems = {}
    passed = []
    failed = []
    for row in ledger:
        run_id = row["run_id"]
        if row["map_file"] != Path(row["map_file"]).name or row["tour_file"] != run_id + ".tour":
            parser.error(f"unsafe manifest filename for {run_id}")
        try:
            map_file = row["map_file"]
            if map_file not in problems:
                problems[map_file] = read_problem(args.maps / map_file)
            problem = problems[map_file]
            if problem.digest != row["map_sha256"]:
                raise ValueError("frozen map SHA256 mismatch")
            proof = verify(problem, args.tours / row["tour_file"], int(row["length"]))
            if proof["tour_sha256"] != row["tour_sha256"]:
                raise ValueError("frozen route SHA256 mismatch")
            passed.append({"run_id": run_id, **proof})
        except (OSError, UnicodeError, ValueError) as error:
            failed.append({"run_id": run_id, "error": str(error)})
    result = {
        "scope": "saved tour identity, validity and length",
        "requested": len(ledger),
        "passed": len(passed),
        "failed": len(failed),
        "results": passed,
        "errors": failed,
    }
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"{len(passed)}/{len(ledger)} verified")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(int(bool(failed)))


if __name__ == "__main__":
    main()
