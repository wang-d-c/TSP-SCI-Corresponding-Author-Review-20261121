"""Check statistical and visual regression runs against the frozen package."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_png(generated, expected):
    with Image.open(generated) as new, Image.open(expected) as old:
        return (
            (new.size, new.mode) == (old.size, old.mode)
            and new.tobytes() == old.tobytes() and new.info == old.info
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Frozen package reproduction outputs")
    parser.add_argument("test", type=Path, help="Isolated fixture and CLI output directory")
    args = parser.parse_args()
    test = args.test.resolve()
    no_plot, full = test / "no_plot", test / "full"
    reference = args.reference.resolve()

    statistical_files = sorted(p.name for p in reference.glob("*.csv"))
    if len(statistical_files) != 8:
        raise AssertionError("Expected the eight frozen output CSVs")
    for name in statistical_files:
        if not sha256(reference / name) == sha256(full / name) == sha256(no_plot / name):
            raise AssertionError(f"CSV changed: {name}")
    result_name = "statistical_reproduction.json"
    if sha256(full / result_name) != sha256(reference / result_name):
        raise AssertionError("The default result JSON changed")
    result = json.loads((no_plot / result_name).read_text(encoding="utf-8"))
    expected = json.loads((reference / result_name).read_text(encoding="utf-8"))
    frozen_environment = expected.pop("environment")
    statistical_environment = result.pop("environment")
    if statistical_environment["matplotlib"] is not None or result != expected:
        raise AssertionError("The statistics-only CLI changed frozen results")
    if {p.name for p in no_plot.iterdir()} != set(statistical_files + [result_name]):
        raise AssertionError("Statistics-only CLI produced unexpected outputs")

    rendered = sorted(reference.glob("*.pdf")) + sorted(reference.glob("*.png"))
    if len(rendered) != 6:
        raise AssertionError("Expected six frozen figures")
    figure_receipts = {}
    for frozen in rendered:
        generated = full / frozen.name
        same_bytes = sha256(generated) == sha256(frozen)
        same_content = same_bytes if frozen.suffix == ".pdf" else check_png(generated, frozen)
        if not same_content:
            raise AssertionError(f"Figure changed: {frozen.name}")
        figure_receipts[frozen.name] = {
            "same_content": same_content, "same_bytes": same_bytes,
        }

    # In the isolated interpreter, there cannot be a hidden Matplotlib dependency.
    isolated = subprocess.run(
        [sys.executable, "-I", "-S", "-c",
         "import importlib.util; assert importlib.util.find_spec('matplotlib') is None"],
        check=False, capture_output=True,
    )
    if isolated.returncode:
        raise AssertionError("Matplotlib was visible in the statistics-only interpreter")

    # A copied and deliberately changed fixture must fail before creating new outputs.
    bad = test / "tampered_fixture"
    shutil.copytree(test / "fixture", bad)
    source = bad / "data" / "core_600_runs.csv"
    with source.open("ab") as stream:
        stream.write(b"\n")
    out = test / "tampered_result"
    failed = subprocess.run(
        [sys.executable, "-I", "-S", str(bad / "reproduce.py"), "--no-plot", "--output", str(out)],
        check=False, capture_output=True, text=True,
    )
    if failed.returncode == 0 or "does not match its bundled SHA256" not in failed.stderr or out.exists():
        raise AssertionError("The statistics-only CLI accepted corrupted input")

    details = {
        "frozen_reference_check": result["frozen_reference_check"],
        "attempted_slots": result["attempted_slots"], "valid_outputs": result["valid_outputs"],
        "complete_triplet_groups": result["complete_triplet_groups"],
        "isolated_interpreter_switches": ["-I", "-S"], "isolated_matplotlib_available": False,
        "default_environment": frozen_environment, "no_plot_environment": statistical_environment,
        "byte_equal_frozen_csvs": statistical_files, "byte_equal_default_statistical_json": True,
        "equal_no_plot_statistical_fields": True, "no_plot_figure_count": 0,
        "full_figures": figure_receipts,
        "input_sha256_guard_regression": {"exit_code": failed.returncode, "no_output_directory": True},
        "effects": {
            name: {field: item[field] for field in ("pairs", "mean_ppm", "sign_flip_p")}
            for name, item in result["effects"].items()
        },
    }
    (test.parent / "reproduction_regression.json").write_text(
        json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print("Frozen statistics, plotting mode, optional dependency and input-integrity guard verified.")


if __name__ == "__main__":
    main()
