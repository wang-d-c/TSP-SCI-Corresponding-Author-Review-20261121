"""Acquire and audit the one predeclared geography reserve without solver execution."""

from decimal import ROUND_CEILING
from gzip import decompress
from io import BytesIO
import json
import re
import tarfile
from urllib.request import urlopen

from build_candidates import INPUTS, ROOT, canonical_points_hash, parse_instance, sha
from check_exposure import PROJ, SOLVE_EVIDENCE_GLOBS, list_paths, normalize_locations


NAME = "usa13509"
SIZE = 13509
BASE = "https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/tsp"
SOURCES = [(f"{BASE}/{NAME}.tsp.gz", False), (f"{BASE}/ALL_tsp.tar.gz", True)]


def get_bytes(attempts):
    for url, archive in SOURCES:
        try:
            with urlopen(url, timeout=20) as response:
                raw = response.read(30_000_001)
                if response.status != 200 or len(raw) > 30_000_000:
                    raise ValueError(f"HTTP {response.status} or unexpected file size {len(raw)}")
            if archive:
                with tarfile.open(fileobj=BytesIO(raw)) as bundle:
                    choices = [item for item in bundle.getmembers() if item.name.rsplit("/",1)[-1] == f"{NAME}.tsp.gz" and item.isfile()]
                    if len(choices) != 1:
                        raise ValueError("archive does not have exactly one expected regular member")
                    member = bundle.extractfile(choices[0]).read()
            else:
                member = raw
            result = decompress(member)
            attempts.append({"url": url, "sha256_download": sha(raw), "sha256_compressed_member": sha(member), "status": "ok"})
            return result
        except (OSError, ValueError, tarfile.TarError, EOFError) as error:
            attempts.append({"url": url, "status": "failed", "reason": f"{type(error).__name__}: {error}"})
    return None


def exposure(raw, coordinates):
    path_regex = [option for glob in (*SOLVE_EVIDENCE_GLOBS, "*.par") for option in ("-g", glob)]
    indices = list_paths(["-li", "-0", "--hidden", "--no-ignore", *path_regex, "-e", r"\busa13509\b"])
    raw_hash, points_hash = sha(raw), sha(normalize_locations(coordinates))
    copied_paths, parse_errors = [], []
    for pointer in list_paths(["--files", "-0", "--hidden", "--no-ignore", "-g", "*.tsp"]):
        if pointer.startswith("outputs/tsp_review_execution_20261120/"):
            continue
        with (PROJ / pointer).open("rb") as f:
            prefix = f.read(4096)
            if not re.search(rb"(?im)^\s*DIMENSION\s*:\s*13509\s*$", prefix):
                continue
            candidate = prefix + f.read()
        try:
            _, points = parse_instance(candidate)
        except (ValueError, KeyError) as error:
            parse_errors.append({"file": pointer, "reason": str(error)})
            continue
        identical = sha(candidate) == raw_hash
        if identical or sha(normalize_locations(points)) == points_hash:
            copied_paths.append({"file": pointer, "identical_bytes": identical})
    return {"indices": indices, "raw_or_geometry_matches": copied_paths, "parse_errors": parse_errors}


def main():
    attempts = []
    data = get_bytes(attempts)
    receipt = {"instance": NAME, "rank": "last_technical_reserve", "official_reference_optimum": 19982859,
               "official_reference_url": "https://www.math.uwaterloo.ca/tsp/usa13509/usa13509.html", "downloads": attempts,
               "acquisition": "failed", "all_method_admission": "pending"}
    if data is not None:
        headers, points = parse_instance(data)
        assert len(points) == SIZE and headers["NAME"].lower() == NAME
        target = INPUTS / f"{NAME}.tsp"
        if target.exists():
            assert data == target.read_bytes()
        else:
            with target.open("xb") as f:
                f.write(data)
        xs, ys = zip(*points.values())
        max_edge = ((max(xs)-min(xs))**2 + (max(ys)-min(ys))**2).sqrt().to_integral_value(rounding=ROUND_CEILING)
        receipt.update(acquisition="verified", sha256_input_bytes=sha(data), sha256_point_table=canonical_points_hash(points),
                       metric=headers["EDGE_WEIGHT_TYPE"], cities=SIZE, min_x=str(min(xs)), max_x=str(max(xs)),
                       min_y=str(min(ys)), max_y=str(max(ys)), max_edge_bound=int(max_edge),
                       total_route_bound=int(max_edge)*SIZE, duplicated_locations=SIZE-len(set(points.values())),
                       fractional_locations=sum(x!=x.to_integral_value() or y!=y.to_integral_value() for x,y in points.values()),
                       exposure=exposure(data, points))
    (ROOT / "usa13509_acquisition_exposure.json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "exposure"}))


if __name__ == "__main__":
    main()
