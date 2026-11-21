"""Audit project exposure without reading route lengths or ranking candidates."""

import csv
import json
import re
import subprocess

from build_candidates import INPUTS, OUTPUTS, ROOT, canonical_points_hash, parse_instance, sha


PROJ = OUTPUTS.parent
STUDY_CANDIDATES = (
    "outputs/tsp_gpt_diagnosis_v2_20261119/design/",
    "outputs/tsp_corresponding_author_review_20261119/previous_desktop_archive/"
    "TSP_SCI_论文与完整实验资料_20261118_新版/09_GPT诊断v2交付/本地新批次输入/",
)
SOLVE_EVIDENCE_GLOBS = (
    "progress*.jsonl", "*attempt*.csv", "*run*.csv", "qualification.json", "result.json"
)


def normalize_locations(points):
    coordinates = tuple(points.values())
    min_x = min(x for x, _ in coordinates)
    min_y = min(y for _, y in coordinates)
    return ("\n".join(f"{x.normalize()} {y.normalize()}" for x, y in sorted(
        (x - min_x, y - min_y) for x, y in coordinates
    )) + "\n").encode("ascii")


def list_paths(args):
    proc = subprocess.run(["rg", *args, "outputs"], capture_output=True, cwd=PROJ, check=False)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.decode("utf-8", errors="replace"))
    return [path.decode("utf-8").replace("\\", "/") for path in proc.stdout.split(b"\0") if path]


def main():
    with (ROOT / "candidate_instances.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    candidates = {}
    for row in rows:
        name = row["instance"]
        raw = (INPUTS / f"{name}.tsp").read_bytes()
        _, points = parse_instance(raw)
        assert sha(raw) == row["source_bytes_sha256"]
        candidates[name] = (sha(raw), canonical_points_hash(points), sha(normalize_locations(points)), len(points))
    matching_dimensions = {values[3] for values in candidates.values()}

    pattern = "(?i)(?:^|[^a-z0-9])(?:" + "|".join(re.escape(name) for name in (*candidates, "fnc19402")) + ")(?:$|[^a-z0-9])"
    index_files = list_paths(["-l", "-0", "--hidden", "--no-ignore", *[
        option for glob in SOLVE_EVIDENCE_GLOBS for option in ("-g", glob)
    ], "-e", pattern])
    name_matches = {}
    lookup_names = (*candidates, "fnc19402")
    for pointer in sorted(set(index_files)):
        content = (PROJ / pointer).read_text(encoding="utf-8-sig", errors="replace")
        names = [name for name in lookup_names if re.search(
            f"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])", content, re.IGNORECASE
        )]
        name_matches[pointer] = names

    matches = {name: [] for name in candidates}
    dimensions_checked = 0
    header_missing = []
    unreadable = []
    parse_errors = []
    file_count = 0
    checked_paths = set()
    cache = {}
    for pointer in list_paths(["--files", "-0", "--hidden", "--no-ignore", "-g", "*.tsp"]):
        if pointer in checked_paths or pointer.startswith("outputs/tsp_review_execution_20261120/"):
            continue
        checked_paths.add(pointer)
        file_count += 1
        path = PROJ / pointer
        try:
            with path.open("rb") as f:
                prefix = f.read(4096)
                header_match = re.search(rb"(?im)^\s*DIMENSION\s*:\s*(\d+)\s*$", prefix)
                if header_match is None:
                    header_missing.append(pointer)
                    continue
                if int(header_match.group(1)) not in matching_dimensions:
                    continue
                dimensions_checked += 1
                raw = prefix + f.read()
        except OSError as error:
            unreadable.append({"file": pointer, "error": str(error)})
            continue
        digest = sha(raw)
        try:
            if digest not in cache:
                _, points = parse_instance(raw)
                cache[digest] = canonical_points_hash(points), sha(normalize_locations(points))
            coords, normalized = cache[digest]
        except (ValueError, KeyError) as error:
            parse_errors.append({"file": pointer, "error": str(error)})
            continue
        for name, (ref_bytes, ref_coords, ref_normalized, _) in candidates.items():
            kind = ("byte_identical" if digest == ref_bytes else "same_city_numeric_values" if coords == ref_coords
                    else "same_geometric_points_after_translation_and_relabeling" if normalized == ref_normalized else None)
            if kind:
                matches[name].append({"file": pointer, "match": kind,
                                      "candidate_staging": pointer.startswith(STUDY_CANDIDATES)})

    verified_columns = list(rows[0]) + ["staged_match_count", "other_match_count", "execution_names_match_count"]
    for row in rows:
        name = row["instance"]
        staged = sum(x["candidate_staging"] for x in matches[name])
        other = len(matches[name]) - staged
        mentions = sum(name in y for y in name_matches.values())
        row.update(staged_match_count=staged, other_match_count=other, execution_names_match_count=mentions)
        row["search_exposure_status"] = ("potential_exposure_requires_review" if other or mentions else
                                         "no_solve_exposure_match_in_audited_loose_files")
    with (ROOT / "candidate_manifest_verified.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=verified_columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    result = {
        "scope": "Loose project outputs only. The two enumerated old unrun-design data caches are prequalification staging. Candidate-phase files, archived ZIP contents, and remote disks excluded. Normalized points allow translation and city permutation, not rotation/reflection or scale. No performance values used.",
        "staging_prefixes_verified_against_prior_zero_formal_record": STUDY_CANDIDATES,
        "scanned_instance_files": file_count,
        "matching_dimension_files": dimensions_checked,
        "unique_successfully_parsed_instance_byte_hashes": len(cache),
        "header_missing_count": len(header_missing),
        "header_missing_paths": header_missing,
        "unreadable": unreadable,
        "matching_dimension_parse_errors": parse_errors,
        "candidate_file_matches": {k: sorted(v, key=lambda x: x["file"]) for k, v in matches.items()},
        "execution_index_name_matches": name_matches,
        "explicit_engineering_exclusion": "fnc19402, engineering run Q19402"
    }
    (ROOT / "exposure_audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    p = [r for r in rows if r["candidate_role"] == "primary_provisional"]
    print(json.dumps({"scanned_tsp": file_count, "matching_n": dimensions_checked, "unique_compared": len(cache),
                      "unreadable": len(unreadable), "parse_errors": len(parse_errors), "header_missing": len(header_missing),
                      "index_matches": name_matches, "primary_needing_review": [r["instance"] for r in p if
                      r["search_exposure_status"] == "potential_exposure_requires_review"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
