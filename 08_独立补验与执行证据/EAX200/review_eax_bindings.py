"""New review EAX dispatch receipts and exact outer verification callbacks."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from math import isqrt
import os
from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT.parents[1]
OLD_REVIEW = OUTPUTS / 'tsp_review_execution_20261120'
NATIVE_SHA = 'db5e3f8d938aeb22d2d7d09a9218256b6e061b2c0149cf94e950bb407cff65a9'
CUTS = [85.0, 86.0, 88.0, 90.0]


def sha(path: Path) -> str:
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write_new(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def ensure(test: bool, message: str) -> None:
    if not test:
        raise ValueError(message)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def bound_dispatch_path(scope: str, attempt: str) -> Path:
    if scope not in ('qualification', 'formal') or not attempt.isascii() or not attempt.isalnum():
        raise ValueError('invalid separate review dispatch identity')
    return ROOT / 'ledger' / scope / (attempt + '_dispatch.json')


def verify_dispatch(args) -> None:
    work = args.output.resolve()
    scope = work.parent.parent.name
    contract_path = ROOT / 'runtime_contract.json'
    contract = read(contract_path)
    ensure(len(work.parents) > 2 and work.parents[2] == Path(contract['run_root']).resolve() and work.name == 'w',
           'EAX must be dispatched into the separately bound review run root')
    path = bound_dispatch_path(scope, work.parent.name)
    item = read(path)
    ensure(item['scope'] == scope and item['run_id'] == args.run_id and item['seed'] == args.seed and
           item['cpu'] == args.cpu == 0 and item['method'] == args.method == 'EAX_r' and
           item['cutoffs_s'] == CUTS and Path(item['work']).resolve() == work and
           Path(item['problem']).resolve() == args.problem.resolve() and
           Path(item['native']).resolve() == args.exe.resolve() and
           item['native_sha256'] == NATIVE_SHA and item['wrapper_sha256'] == sha(ROOT / 'eax_decimal_observer.py'),
           'EAX arguments differ from the recorded dispatch')
    ensure(item['input_sha256'] == sha(args.problem), 'map differs from the dispatch hash')
    ensure(item['runtime_contract_sha256'] == sha(contract_path) and contract['cutoffs_s'] == CUTS,
           'dispatch differs from the frozen review runtime contract')
    if scope == 'formal':
        gate_path = ROOT / 'formal_admission.json'
        gate = read(gate_path)
        ensure(item['admission_sha256'] == sha(gate_path) and gate['admitted'] is True and
               gate['runtime_contract_sha256'] == item['runtime_contract_sha256'] and
               item['source_row'] in contract['planned_eax_rows'], 'formal EAX admission or row is invalid')
    else:
        ensure(item['source_row'] in contract['qualification_cases'] and item['admission_sha256'] is None,
               'engineering input differs from the registered qualification case')


def install_outer_callbacks(runner) -> None:
    exact = load('review_eax_exact_outer', OLD_REVIEW / 'phase_b_numeric' / 'euc2d_verify.py')

    def recount_coordinates(path):
        problem = exact.read_problem(Path(path))
        return tuple(zip(problem.input_ids, problem.tokens))

    def primary(problem_path, tour_path):
        info = exact.verify(exact.read_problem(Path(problem_path)), Path(tour_path))
        return {'complete_cycle': True, 'city_count': info['dimension'],
                'euc_2d_integer_length': info['length'], 'route_sha256': info['tour_sha256'],
                'problem_sha256': info['instance_sha256'], 'global_optimality_proven': False}

    def secondary(problem_path, tour_path):
        problem = exact.read_problem(Path(problem_path))
        route, route_hash = exact.read_tour(Path(tour_path), problem.n)
        scale = problem.lattice
        length = 0
        previous = route[-1]
        for current in route:
            x1, y1 = problem.points[previous - 1]
            x2, y2 = problem.points[current - 1]
            squared = (x1 - x2) ** 2 + (y1 - y2) ** 2
            integer = isqrt(squared) // scale
            length += integer + (4 * squared >= ((2 * integer + 1) * scale) ** 2)
            previous = current
        return {'city_count': len(route), 'length': length, 'closed_cycle': True, 'route_sha256': route_hash,
                'map_sha256': problem.digest, 'rounding': 'exact squared comparison at integer plus one half',
                'optimality_proof': False}

    runner.batch.import_recount = lambda: SimpleNamespace(coordinates=recount_coordinates, verify=primary)
    runner.registry.recount = secondary
