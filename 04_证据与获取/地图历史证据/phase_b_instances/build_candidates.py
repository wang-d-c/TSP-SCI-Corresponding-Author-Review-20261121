"""Create a pre-outcome four-stratum EUC_2D input candidate ledger."""

import argparse
import csv
from decimal import Decimal, localcontext, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT.parents[1]
DESIGN = OUTPUTS / "tsp_gpt_diagnosis_v2_20261119/design"
DIMACS = DESIGN / "dimacs_generated"
INPUTS = ROOT / "local_input_bytes_not_redistributable"
sys.path.insert(0, str(DESIGN))
from fetch_inputs import parse_instance, canonical_points_hash


WBASE = "https://www.math.uwaterloo.ca/tsp"
WREF = f"{WBASE}/world/summary.html"
VREF = f"{WBASE}/vlsi/summary.html"
CAT = f"{WBASE}/world/countries.html"
DBASE = "https://archive.dimacs.rutgers.edu/Challenges/TSP"
DREF = f"{DBASE}/bounds"
ARCHIVE_SHA = "5f041f0b9d68f2397309880919bbfde3d286e1b10b042cc07285f632cee6080a"

PANEL = {
    "01_VLSI_engineering": (
        ("dga9698", "xmc10150", "xvb13584", "xrb14233", "xia16928"),
        ("pjh17845", "frh19289", "ida8197"),
    ),
    "02_DIMACS_clustered": (
        ("C10k.0", "C10k.1", "C10k.2", "genC12k.seed100003", "genC15k.seed100004"),
        ("genC10k.seed100005", "genC17k.seed100006"),
    ),
    "03_DIMACS_uniform": (
        ("E10k.0", "E10k.1", "E10k.2", "genE12k.seed100006", "genE15k.seed100007"),
        ("genE10k.seed100003", "genE10k.seed100004", "genE10k.seed100005"),
    ),
    "04_Waterloo_geographic": (
        ("ja9847", "gr9882", "fi10639", "mo14185", "it16862"),
        ("kz9976", "ei8246", "ym7663", "eg7146", "tz6117"),
    ),
}
W_OPT = {"eg7146": 172386, "fi10639": 520527, "gr9882": 300899, "ei8246": 206171, "it16862": 557315,
         "ja9847": 491924, "kz9976": 1061881, "mo14185": 427377, "tz6117": 394718, "ym7663": 238314}
D_BOUND = {"E10k.0": "71362276.444048", "E10k.1": "71565485.443519", "E10k.2": "71351794.654167",
           "C10k.0": "32782155.221284", "C10k.1": "32958945.515201", "C10k.2": "32926889.150397"}
NEW_GENERATED = {
    "genC12k.seed100003": ("portcgen", 12000, 100003),
    "genC15k.seed100004": ("portcgen", 15000, 100004),
    "genC10k.seed100005": ("portcgen", 10000, 100005),
    "genC17k.seed100006": ("portcgen", 17000, 100006),
    "genE12k.seed100006": ("portgen", 12000, 100006),
    "genE15k.seed100007": ("portgen", 15000, 100007),
}
EXPOSED = {"fnc19402": "Maximum-size EAX engineering attempt Q19402; reserved only as exposed engineering case."}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["instance"]: r for r in csv.DictReader(f)}


def fetch(url):
    with urlopen(url, timeout=20) as r:
        data = r.read(5_000_000)
        if r.status != 200 or len(data) == 5_000_000:
            raise ValueError(f"unexpected transfer HTTP {r.status} {len(data)} bytes")
        return data


def get_bytes(name, layer, cache, generate, network):
    path = INPUTS / f"{name}.tsp"
    if path.is_file():
        data = path.read_bytes()
        if name in cache:
            assert sha(data) == cache[name][0], name
        return data, "checked_staged_file"
    if name in cache:
        expected, old = cache[name]
        data = old.read_bytes()
        assert sha(data) == expected, old
        return data, "reused_previous_original_bytes"
    if name in NEW_GENERATED and generate:
        exe, n, seed = NEW_GENERATED[name]
        binary = DIMACS / "private_build" / f"{exe}.exe"
        assert sha((DESIGN / "DIMACS_codes.zip").read_bytes()) == ARCHIVE_SHA
        official_sample = "C10k.0" if exe == "portcgen" else "E10k.0"
        reproduced = subprocess.check_output([str(binary), "10000", "10000"], timeout=20).replace(b"\r\n", b"\n")
        assert sha(reproduced) == cache[official_sample][0], exe
        return subprocess.check_output([str(binary), str(n), str(seed)], timeout=20).replace(b"\r\n", b"\n"), "project_generated_with_sample_verified_DIMACS_generator"
    if layer == "04_Waterloo_geographic" and network:
        return fetch(f"{WBASE}/world/{name}.tsp"), "official_download_current_run"
    raise FileNotFoundError("upstream download or verified generator execution needed")


def describe(layer, name, rank, proposed, cached, geom, dimacs, old_vlsi, generate, network):
    if layer.startswith("01"):
        url, origin, ref = f"{WBASE}/vlsi/{name}.tsp", f"{WBASE}/vlsi/", VREF
        kind = "Bonn VLSI routing / engineering point set"
        citation = "Official Waterloo catalogue; original bytes retrieved locally; redistribution grant not established."
        lower, tour, opt = (old_vlsi[name][x] for x in ("reference_lower_bound", "reference_best_known_tour", "reference_optimum"))
        precision = "Waterloo Optimal status" if opt else "Waterloo best reported tour and lower bound"
    elif layer.startswith("04"):
        url, origin, ref = f"{WBASE}/world/{name}.tsp", CAT, WREF
        kind = "National geographic feature locations, rounded planar Euclidean metric from archive"
        citation = "Original National TSP catalogue; no coordinate redistribution grant established; fetch upstream."
        lower = tour = opt = W_OPT[name]
        precision = "Waterloo summary marks Optimal (bound equals reported tour; individual location-page captions may be older)."
    else:
        url, origin, ref = f"{DBASE}/codes.zip", f"{DBASE}/download.html", DREF if name in D_BOUND else ""
        kind = "DIMACS clustered generator" if layer.startswith("02") else "DIMACS uniform planar generator"
        citation = "Official benchmark research download and generator; separate redistribution grant not established; regenerate using upstream."
        lower, tour, opt = D_BOUND.get(name, ""), "", ""
        precision = ("Held-Karp lower bound as displayed in the official text record. Optimal-length field is blank."
                     if lower else "No external reference registered for project-generated map.")
    seed = NEW_GENERATED[name][2] if name in NEW_GENERATED else dimacs.get(name, {}).get("generation_seed", "")
    nominal_size = NEW_GENERATED[name][1] if name in NEW_GENERATED else (
        int(geom[name]["size"]) if name in geom else int(dimacs[name]["size"]) if name in dimacs else int(name[2:]))
    row = {"stratum": layer, "candidate_role": "primary_provisional" if proposed else "reserve_ordered", "stratum_order": rank,
           "instance": name, "origin_and_structure": kind, "nominal_dimension": nominal_size, "source_url": url,
           "source_index_url": origin, "generation_seed": seed, "reference_url": ref, "reference_lower_bound": lower,
           "reference_reported_tour": tour, "reference_optimum": opt, "reference_nature": precision,
           "rights_boundary": citation, "search_exposure_status": "pending_exposure_audit", "all_methods_numerical_gate": "pending"}
    try:
        data, acquisition = get_bytes(name, layer, cached, generate, network)
        headers, points = parse_instance(data)
        assert len(points) == nominal_size, name
        locations = set(points.values())
        xs, ys = zip(*locations)
        with localcontext() as ctx:
            ctx.prec = 100
            rounded_max_bound = (((max(xs)-min(xs))**2+(max(ys)-min(ys))**2).sqrt()).to_integral_value(rounding=ROUND_CEILING)
        path = INPUTS / f"{name}.tsp"
        if not path.exists():
            with path.open("xb") as f:
                f.write(data)
        row.update(source_bytes_sha256=sha(data), point_table_sha256=canonical_points_hash(points), byte_count=len(data),
                   header_name=headers["NAME"], metric=headers["EDGE_WEIGHT_TYPE"], min_x=str(min(xs)), max_x=str(max(xs)),
                   min_y=str(min(ys)), max_y=str(max(ys)), duplicate_locations=len(points)-len(locations),
                   fractional_coordinate_cities=sum(x!=x.to_integral_value() or y!=y.to_integral_value() for x,y in points.values()),
                   negative_coordinate_cities=sum(x<0 or y<0 for x,y in points.values()),
                   max_edge_integer_upper_bound=int(rounded_max_bound), total_tour_integer_upper_bound=nominal_size*int(rounded_max_bound),
                   acquisition=acquisition, acquisition_error="")
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        row.update(acquisition="blocked", acquisition_error=f"{type(error).__name__}: {error}")
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--network", action="store_true", help="Fetch missing files from the one fixed official geographical catalogue.")
    p.add_argument("--generate", action="store_true", help="Generate the six fixed project-derived DIMACS inputs; no solve.")
    args = p.parse_args()
    INPUTS.mkdir(parents=True, exist_ok=True)
    geom = read_rows(DESIGN / "instance_manifest.csv")
    dimacs = read_rows(DIMACS / "candidate_manifest.csv")
    old_vlsi = read_rows(DESIGN / "selected_instances.csv")
    cache = {r["instance"]: (r["sha256"], DESIGN / "private_inputs" / f"{r['instance']}.tsp") for r in geom.values()}
    cache.update({r["instance"]: (r["sha256"], DIMACS / "private_inputs" / f"{r['instance']}.tsp") for r in dimacs.values()})
    rows = [describe(layer, name, i, proposed, cache, geom, dimacs, old_vlsi, args.generate, args.network)
            for layer, (primary, reserved) in PANEL.items() for proposed, names in ((True,primary),(False,reserved))
            for i, name in enumerate(names,1)]
    assert len({r["instance"] for r in rows}) == len(rows) and not set(EXPOSED).intersection(r["instance"] for r in rows)
    prior_manifest = ROOT / "candidate_instances.csv"
    if prior_manifest.exists():
        prior = read_rows(prior_manifest)
        for row in rows:
            prev = prior.get(row["instance"], {})
            if row["acquisition"] == "checked_staged_file" and row.get("source_bytes_sha256") == prev.get("source_bytes_sha256"):
                row["acquisition"] = prev["acquisition"]
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT / "candidate_instances.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    primary = [r for r in rows if r["candidate_role"] == "primary_provisional"]
    receipt = {"planned_methods_started": 0, "primary_targets": len(primary), "available_primary_bytes": sum("source_bytes_sha256" in r for r in primary),
               "available_reserve_bytes": sum("source_bytes_sha256" in r for r in rows if r not in primary),
               "unavailable": {r["instance"]: r["acquisition_error"] for r in rows if r["acquisition_error"]}, "explicit_exclusions": EXPOSED,
               "numeric_checks_not_admission": "Raw files, hashes, parser, ranges and structure only; all-method admission remains separate.",
               "DIMACS_generator_archive_sha256": ARCHIVE_SHA,
               "generator_exe_sha256": {name: sha((DIMACS / "private_build" / f"{name}.exe").read_bytes()) for name in ("portgen","portcgen")}}
    (ROOT / "instance_acquisition_receipt.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
