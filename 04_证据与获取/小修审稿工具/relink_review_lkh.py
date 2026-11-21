"""Relink three existing audited LKH source substitutions using a new stock build."""

import argparse
import json
from pathlib import Path
import subprocess
import time

from bind_author_lkh import AUTHOR_ARCHIVE_SHA256, SHARED_ENGINE_SHA256, digest


PATCHES = {
    "Ascent": ("Ascent_cost64_candidate.c", "cda62c286fcc6cd43dc74ed37f233d3809822034ffdfba5764fb31cc58c7a7dd"),
    "AddTourCandidates": ("AddTourCandidates_ablation.c", "0f093e9b690b706007d6eb60f044f224e1f82a8a8051c7850804d8eae6f4083a"),
    "FindTour": ("FindTour_ablation.c", "97af1de112eb88ef3dfc59ff50db586ca0637dac9de94fbb9e62ebec6a5acb30"),
}


def relink(stock: Path, source_ascent: Path, source_ablation: Path, output: Path) -> int:
    receipt_path = stock / "build_status.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["state"] != "built_not_run_not_validated" or receipt["archive_sha256"] != AUTHOR_ARCHIVE_SHA256:
        raise ValueError("the stock build does not match the archived source")
    if digest(Path(receipt["compiler"])) != receipt["compiler_sha256"]:
        raise ValueError("stock compiler changed")
    sources = {name: (source_ascent if name == "Ascent" else source_ablation) / filename
               for name, (filename, _) in PATCHES.items()}
    if any(digest(source) != PATCHES[name][1] for name, source in sources.items()):
        raise ValueError("an audited replacement file changed")
    by_log = {record["log"]: record["argv"] for record in receipt["commands"]}
    output.mkdir(parents=True, exist_ok=False)
    binary = output / "LKH-review-common.exe"
    state = {"state": "started", "stock_receipt_sha256": digest(receipt_path),
             "patched_sources": {name: PATCHES[name][1] for name in sources},
             "solver_executions": 0, "commands": []}
    begin = time.monotonic()

    def run_stage(name: str, args: list[str]) -> None:
        with (output / f"{name}.log").open("xb") as log:
            process = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT,
                                     check=False, timeout=60)
        state["commands"].append({"argv": args, "return_code": process.returncode})
        process.check_returncode()

    try:
        for name, source in sources.items():
            args = by_log[f"logs/{name}.log"].copy()
            args[args.index("-c") + 1] = str(source)
            args[args.index("-o") + 1] = str(output / f"{name}.o")
            run_stage(name, args)
        link = by_log["logs/link.log"].copy()
        link[link.index("-o") + 1] = str(binary)
        link = [str(output / Path(arg).name) if arg.endswith(".o") and Path(arg).stem in sources else arg
                for arg in link]
        run_stage("link", link)
        objdump = Path(receipt["compiler"]).with_name("objdump.exe")
        run_stage("pe_imports", [str(objdump), "-p", str(binary)])
        binary_sha256 = digest(binary)
        state.update(state="built_not_run", binary=binary.name, binary_sha256=binary_sha256,
                     identical_to_historically_built_ablation_pe=binary_sha256 == SHARED_ENGINE_SHA256)
        return 0
    except (OSError, subprocess.SubprocessError) as exc:
        state.update(state="build_failed", error=str(exc))
        return 1
    finally:
        state["elapsed_s"] = time.monotonic() - begin
        (output / "relink_receipt.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({field: state.get(field) for field in ("state", "binary_sha256",
                                                               "solver_executions", "elapsed_s")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for parameter in ("stock", "source-ascent", "source-ablation", "output"):
        parser.add_argument(f"--{parameter}", type=Path, required=True)
    options = {key: path.resolve() for key, path in vars(parser.parse_args()).items()}
    raise SystemExit(relink(**options))
