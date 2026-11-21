"""Exact-decimal validation callbacks for an isolated GA-EAX adapter candidate.

This file contains no native launcher and grants no experimental admission.
Its callbacks preserve native route claims, candidate completeness, and the
published nearest-integer EUC_2D distance model.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isqrt
from pathlib import Path
import re


FLAGS = re.ASCII
INTEGER = re.compile(r"[+-]?[0-9]+", FLAGS)
COORDINATE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]{1,4})?", FLAGS)
HEADER = re.compile(r"([A-Z][A-Z0-9_]*)\s*:\s*(.*?)\s*")
CLAIM = re.compile(r"\bLength\s*=\s*([+-]?[0-9]+)\b", FLAGS)


@dataclass(frozen=True)
class Coordinates:
    points: tuple[tuple[int, int], ...]
    scale: int

    def __len__(self):
        return len(self.points)

    def length(self, cities: list[int]) -> int:
        if len(cities) != len(self.points) or set(cities) != set(range(1, len(self.points) + 1)):
            raise ValueError("route must visit each numbered city exactly once")
        total = 0
        previous = cities[-1]
        for current in cities:
            ax, ay = self.points[previous - 1]
            bx, by = self.points[current - 1]
            dx, dy = ax - bx, ay - by
            q = dx * dx + dy * dy
            if self.scale == 1:
                integer = isqrt(q)
                total += integer + (q > integer * integer + integer)
            else:
                total += (isqrt(4 * q) + self.scale) // (2 * self.scale)
            previous = current
        return total


def integer(token: str) -> int:
    if len(token) > 30 or not INTEGER.fullmatch(token):
        raise ValueError(f"invalid integer: {token!r}")
    return int(token)


def exact_part(token: str) -> tuple[int, int]:
    if len(token) > 256 or not COORDINATE.fullmatch(token):
        raise ValueError(f"invalid coordinate: {token!r}")
    try:
        value = Decimal(token)
    except InvalidOperation as error:
        raise ValueError(f"invalid coordinate: {token!r}") from error
    sign, digits, exponent = value.as_tuple()
    if not value.is_finite() or not -512 <= exponent <= 512:
        raise ValueError(f"coordinate outside exact-verification range: {token!r}")
    coefficient = int(''.join(map(str, digits)))
    return (-coefficient if sign else coefficient), exponent


def sections(text: str, section: str, *, require_eof: bool) -> tuple[dict[str, str], list[list[str]], list[str]]:
    headings: dict[str, str] = {}
    data: list[list[str]] = []
    comments: list[str] = []
    started = ended = False
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ended:
            raise ValueError("content after EOF")
        if line == "EOF":
            ended = True
        elif started:
            data.append(line.split())
        elif line == section:
            started = True
        else:
            field = HEADER.fullmatch(line)
            if field is None:
                raise ValueError(f"invalid TSPLIB header: {line!r}")
            key, value = field.groups()
            if key == "COMMENT":
                comments.append(value)
            else:
                if key in headings:
                    raise ValueError(f"duplicate TSPLIB heading: {key}")
                headings[key] = value
    if not started or (require_eof and not ended):
        raise ValueError(f"missing {section} or EOF")
    return headings, data, comments


def parse_coordinates(text: str) -> Coordinates:
    headings, rows, _ = sections(text, "NODE_COORD_SECTION", require_eof=False)
    if headings.get("TYPE") != "TSP" or headings.get("EDGE_WEIGHT_TYPE") != "EUC_2D":
        raise ValueError("symmetric TSP EUC_2D required")
    if integer(headings.get("SCALE", "1")) != 1:
        raise ValueError("non-unit SCALE is outside the frozen distance model")
    dimension = integer(headings.get("DIMENSION", ""))
    if dimension < 3 or len(rows) != dimension:
        raise ValueError("instance dimension does not match the coordinate count")
    exact = []
    for number, record in enumerate(rows, start=1):
        if len(record) != 3 or integer(record[0]) != number:
            raise ValueError("native EAX requires sequential 1-based coordinate IDs")
        exact.append((exact_part(record[1]), exact_part(record[2])))
    min_exp = min(0, min(power for point in exact for _, power in point))
    points = tuple(tuple(coefficient * 10 ** (exp - min_exp) for coefficient, exp in point) for point in exact)
    return Coordinates(points, 10 ** -min_exp)


def validate_tour(raw: bytes, coordinates: Coordinates) -> int:
    header, records, comments = sections(raw.decode("ascii"), "TOUR_SECTION", require_eof=True)
    if header.get("TYPE") not in (None, "TOUR") or integer(header.get("DIMENSION", "")) != len(coordinates):
        raise ValueError("route type or dimension mismatch")
    numbers = [integer(token) for row in records for token in row]
    if not numbers or numbers[-1] != -1:
        raise ValueError("route must end with the -1 sentinel")
    total = coordinates.length(numbers[:-1])
    claims = [integer(token) for comment in comments for token in CLAIM.findall(comment)]
    if any(claim != total for claim in claims):
        raise ValueError("route claimed length disagrees with exact EUC_2D")
    return total


def validate_eax_natural_result(path: Path, coordinates: Coordinates, expected: int) -> int:
    rows = path.read_text(encoding="ascii").splitlines()
    if len(rows) != 2 or len(rows[0].split()) != 2:
        raise ValueError("EAX natural result requires an instance count, cost and one complete route")
    n, claimed = map(integer, rows[0].split())
    total = coordinates.length([integer(token) for token in rows[1].split()])
    if n != len(coordinates) or claimed != total or expected != total:
        raise ValueError("EAX natural result disagrees with independent cost or completion record")
    return total


def install_inner_callbacks(wrapper) -> None:
    for callback in (parse_coordinates, validate_tour, validate_eax_natural_result):
        if not callable(getattr(wrapper, callback.__name__, None)):
            raise TypeError(f"missing expected EAX callback {callback.__name__}")
    wrapper.parse_coordinates = parse_coordinates
    wrapper.validate_tour = validate_tour
    wrapper.validate_eax_natural_result = validate_eax_natural_result
