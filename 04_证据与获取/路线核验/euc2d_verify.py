"""Read-only, exact EUC_2D reference for terminating-decimal TSPLIB inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path


INTEGER = re.compile(r"[+-]?[0-9]+", re.ASCII)
DECIMAL = re.compile(
    r"(?P<sign>[+-]?)(?P<field>[0-9]+(?:\.[0-9]*)?|\.[0-9]+)"
    r"(?:[eE](?P<exponent>[+-]?[0-9]{1,4}))?",
    re.ASCII,
)
HEADER = re.compile(r"([A-Z][A-Z0-9_]*)\s*:\s*(.*?)\s*")
INT32_MAX = (1 << 31) - 1
INT64_MAX = (1 << 63) - 1


def signed_integer(text: str) -> int:
    if len(text) > 30 or not INTEGER.fullmatch(text):
        raise ValueError(f"invalid integer: {text!r}")
    return int(text)


def decimal_parts(token: str) -> tuple[int, int]:
    """Return an exact signed coefficient and a radix-10 exponent."""
    match = DECIMAL.fullmatch(token) if len(token) <= 256 else None
    if not match:
        raise ValueError(f"invalid finite decimal coordinate: {token!r}")
    whole, _, fractional = match["field"].partition(".")
    exponent = int(match["exponent"] or 0) - len(fractional)
    if not -512 <= exponent <= 512:
        raise ValueError(f"coordinate decimal exponent exceeds verifier range: {token!r}")
    coefficient = int(whole + fractional)
    if match["sign"] == "-":
        coefficient = -coefficient
    return coefficient, exponent


def read_sections(path: Path, section: str) -> tuple[dict[str, str], list[str], str]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    lines = raw.decode("utf-8-sig").splitlines()
    header = {}
    records = []
    seen_section = False
    seen_end = False
    for number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if seen_end:
            raise ValueError(f"{path}:{number}: data after EOF")
        if line == "EOF":
            seen_end = True
            continue
        if seen_section:
            records.append(line)
            continue
        if line == section:
            seen_section = True
            continue
        match = HEADER.fullmatch(line)
        if not match:
            raise ValueError(f"{path}:{number}: invalid header or unexpected section")
        key, value = match.groups()
        if key == "COMMENT":
            continue
        if key in header:
            raise ValueError(f"{path}:{number}: duplicate {key}")
        header[key] = value
    if not seen_section:
        raise ValueError(f"{path}: missing {section}")
    return header, records, digest


def dimension_of(header: dict[str, str]) -> int:
    dimension = signed_integer(header.get("DIMENSION", ""))
    if dimension < 3:
        raise ValueError("dimension must be at least three")
    return dimension


def rounded_euclidean(dx: int, dy: int, lattice: int) -> int:
    # floor(sqrt(dx²+dy²)/lattice + 1/2). Flooring the numerator's
    # square root preserves the quotient floor for integer denominator.
    return (math.isqrt(4 * (dx * dx + dy * dy)) + lattice) // (2 * lattice)


@dataclass(frozen=True)
class Problem:
    digest: str
    points: tuple[tuple[int, int], ...]
    tokens: tuple[tuple[str, str], ...]
    input_ids: tuple[int, ...]
    lattice: int

    @property
    def n(self) -> int:
        return len(self.points)

    def distance(self, a: int, b: int) -> int:
        ax, ay = self.points[a - 1]
        bx, by = self.points[b - 1]
        return rounded_euclidean(ax - bx, ay - by, self.lattice)


def read_problem(path: Path) -> Problem:
    header, records, digest = read_sections(path, "NODE_COORD_SECTION")
    if header.get("TYPE") != "TSP" or header.get("EDGE_WEIGHT_TYPE") != "EUC_2D":
        raise ValueError("only symmetric TYPE TSP with EDGE_WEIGHT_TYPE EUC_2D is supported")
    if "SCALE" in header and signed_integer(header["SCALE"]) != 1:
        raise ValueError("non-unit SCALE is outside standard EUC_2D")
    n = dimension_of(header)
    if len(records) != n:
        raise ValueError(f"expected {n} coordinate rows, got {len(records)}")
    token_map = {}
    decimal_map = {}
    for line in records:
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(f"invalid coordinate row: {line!r}")
        node = signed_integer(fields[0])
        if not 1 <= node <= n or node in token_map:
            raise ValueError(f"out-of-range or repeated city number: {node}")
        token_map[node] = (fields[1], fields[2])
        decimal_map[node] = (decimal_parts(fields[1]), decimal_parts(fields[2]))
    exponent = min(0, min(part[1] for point in decimal_map.values() for part in point))
    points = []
    for node in range(1, n + 1):
        x, y = decimal_map[node]
        points.append((x[0] * 10 ** (x[1] - exponent), y[0] * 10 ** (y[1] - exponent)))
    return Problem(
        digest,
        tuple(points),
        tuple(token_map[node] for node in range(1, n + 1)),
        tuple(token_map),
        10 ** -exponent,
    )


def read_tour(path: Path, n: int) -> tuple[tuple[int, ...], str]:
    header, records, digest = read_sections(path, "TOUR_SECTION")
    if header.get("TYPE") not in ("TOUR", None):
        raise ValueError("route TYPE must be TOUR when present")
    if dimension_of(header) != n:
        raise ValueError("route DIMENSION does not match the instance")
    city_ids = tuple(signed_integer(word) for line in records for word in line.split())
    if len(city_ids) != n + 1 or city_ids[-1] != -1:
        raise ValueError("route must contain exactly DIMENSION city IDs followed by -1")
    nodes = city_ids[:-1]
    if set(nodes) != set(range(1, n + 1)):
        raise ValueError("route must contain each city exactly once")
    return nodes, digest


def verify(problem: Problem, tour: Path, expected: int | None = None) -> dict:
    nodes, digest = read_tour(tour, problem.n)
    length = sum(problem.distance(a, b) for a, b in zip(nodes, (*nodes[1:], nodes[0])))
    if expected is not None and length != expected:
        raise ValueError(f"route length {length} differs from expected length {expected}")
    return {
        "status": "valid_hamiltonian_cycle",
        "dimension": problem.n,
        "length": length,
        "metric": "EUC_2D decimal-exact nearest integer, ties upward",
        "instance_sha256": problem.digest,
        "tour_sha256": digest,
    }


def lattice_text(value: int, lattice: int) -> str:
    digits = len(str(lattice)) - 1
    if not digits:
        return str(value)
    whole, fractional = divmod(abs(value), lattice)
    sign = "-" if value < 0 else ""
    return f"{sign}{whole}.{fractional:0{digits}d}".rstrip("0").rstrip(".")


def numeric_preflight(problem: Problem, precision: int, sample: int) -> dict:
    if precision < 1 or sample < 0:
        raise ValueError("LKH precision must be positive and sample count nonnegative")
    coordinates = tuple((float(x), float(y)) for x, y in problem.tokens)
    finite = all(math.isfinite(value) for point in coordinates for value in point)
    range_indices = [
        min(range(problem.n), key=lambda i: problem.points[i][axis]) for axis in (0, 1)
    ] + [
        max(range(problem.n), key=lambda i: problem.points[i][axis]) for axis in (0, 1)
    ]
    mins = tuple(problem.points[range_indices[axis]][axis] for axis in (0, 1))
    maxs = tuple(problem.points[range_indices[axis + 2]][axis] for axis in (0, 1))
    edge_upper = rounded_euclidean(maxs[0] - mins[0], maxs[1] - mins[1], problem.lattice)
    rng = random.Random(20261120)
    pairs = {(min(a, b), max(a, b)) for a in range_indices for b in range_indices if a != b}
    sample_target = min(problem.n * (problem.n - 1) // 2, sample + len(pairs))
    if sample_target == problem.n * (problem.n - 1) // 2:
        pairs.update((a, b) for a in range(problem.n) for b in range(a + 1, problem.n))
    else:
        while len(pairs) < sample_target:
            a, b = rng.sample(range(problem.n), 2)
            pairs.add((min(a, b), max(a, b)))
    disagreements = []
    mismatch_count = 0
    if finite:
        for a, b in sorted(pairs):
            ax, ay = coordinates[a]
            bx, by = coordinates[b]
            dx, dy = ax - bx, ay - by
            native = math.sqrt(dx * dx + dy * dy) + 0.5
            model_length = int(native) if math.isfinite(native) and native < INT32_MAX + 1 else None
            exact = problem.distance(a + 1, b + 1)
            if model_length != exact:
                mismatch_count += 1
                if len(disagreements) < 12:
                    disagreements.append([a + 1, b + 1, exact, model_length])
    integral = all(value % problem.lattice == 0 for point in problem.points for value in point)
    sequential = problem.input_ids == tuple(range(1, problem.n + 1))
    return {
        "status": "static_screen_only",
        "dimension": problem.n,
        "instance_sha256": problem.digest,
        "coordinate_min": [lattice_text(value, problem.lattice) for value in mins],
        "coordinate_max": [lattice_text(value, problem.lattice) for value in maxs],
        "binary64_all_finite": finite,
        "binary64_duplicate_pairs_count": len(coordinates) - len(set(coordinates)) if finite else None,
        "coordinate_rows_sequential": sequential,
        "signed_int32_edge_bound_pass": edge_upper <= INT32_MAX,
        "lkh_precision": precision,
        "signed_int32_scaled_edge_bound_pass": edge_upper * precision <= INT32_MAX,
        "rounded_bbox_edge_upper": edge_upper,
        "tour_length_upper": problem.n * edge_upper,
        "eax_double_counted_tour_int64_bound_pass": 2 * problem.n * edge_upper <= INT64_MAX,
        "eax_neighbor_sentinel_bound_pass": edge_upper <= 100_000_000,
        "eax_dense_distance_matrix_min_bytes": 4 * problem.n**2,
        "eax_two_dense_int32_matrices_min_bytes": 8 * problem.n**2,
        "legacy_p5_gpx_coordinate_gate_pass": integral
        and min(mins) >= 0
        and max(maxs) <= 1_000_000 * problem.lattice,
        "binary64_modeled_edge_checks": len(pairs) if finite else 0,
        "binary64_mismatch_count": mismatch_count if finite else None,
        "binary64_mismatch_examples": disagreements,
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("instance", type=Path)
    cli.add_argument("tour", nargs="?", type=Path)
    cli.add_argument("--expect", type=int)
    cli.add_argument("--screen", action="store_true")
    cli.add_argument("--sample", type=int, default=5000)
    cli.add_argument("--lkh-precision", type=int, default=100)
    args = cli.parse_args()
    if (args.tour is None) == (not args.screen):
        cli.error("provide either a tour to verify or --screen")
    if args.expect is not None and args.tour is None:
        cli.error("--expect requires a tour")
    try:
        problem = read_problem(args.instance)
        result = (
            numeric_preflight(problem, args.lkh_precision, args.sample)
            if args.screen
            else verify(problem, args.tour, args.expect)
        )
    except (UnicodeError, OSError, ValueError) as exc:
        cli.exit(2, f"{exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
