"""Isolated EAX qualification and supplemental 200-slot controller.

The default command only reports the current state. Original C/M/K scores and
all older engineering artifacts stay read-only. A full-run phase requires a
new immutable admission derived from real qualification and an explicit run.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import struct
import sys

import psutil

from review_eax_bindings import (
    ROOT, OUTPUTS, OLD_REVIEW, NATIVE_SHA, CUTS, bound_dispatch_path, ensure,
    install_outer_callbacks, load, read, sha, write_new,
)


SOURCE_BINDING = OUTPUTS / 'tsp_gpt_diagnosis_v2_20261119' / 'eax_formal_binding'
RECOVERY = OUTPUTS / 'lkh_v24_local_20261116' / 'recovery_r1'
FROZEN = SOURCE_BINDING / 'frozen'
OBSERVER = ROOT / 'eax_decimal_observer.py'
CONTRACT = ROOT / 'runtime_contract.json'
ADMISSION = ROOT / 'formal_admission.json'
STATE = OLD_REVIEW / 'phase_b_common_r3' / 'formal'
PLAN = OLD_REVIEW / 'phase_b_design' / '主实验800_候选账本.csv'
PANEL_INPUTS = OLD_REVIEW / 'phase_b_instances' / 'local_input_bytes_not_redistributable'
MODEL = OLD_REVIEW / 'phase_b_numeric' / 'final_panel_distance_model_binding.csv'
HARDWARE_BYTES = 12 * 1024**3
STORAGE = STATE / 'storage_resume_policy.json'
HISTORICAL_LARGE = OLD_REVIEW / 'phase_b_control' / 'q'
REQUIRED_CUTS = ('85.0', '86', '88', '90')
FORMAL_RESEARCH_TASKS = frozenset(('largest', 'fractional', 'high_frequency'))
FROZEN_POLICY = 'review_EAX_decimal_85_R13a01'


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def get_ancestry():
    # This authenticates the installed Python and native PE that actually ran
    # the old benchmark. Mixing a bundled but different Python is rejected.
    return load('cmk_eax_ancestral_binding', SOURCE_BINDING / 'adapter_binding.py')


def read_planned_rows():
    prior = read(STATE / 'execution_scope.json')
    ensure(sha(PLAN) == prior['plan_hashes']['main'], 'the original main schedule changed')
    entries = [item for item in csv_rows(PLAN) if item['method'] == 'EAX_ref']
    ensure(len(entries) == 200 and [item['run_id'] for item in entries] == prior['deferred_eax_ids'],
           'the 200 original deferred EAX identities changed')
    ensure(all((item['request_at_s'], item['stop_proof_before_s'], item['certify_before_s'], item['cleanup_before_s'])
               == REQUIRED_CUTS and item['budget_s'] == '90' for item in entries),
           'deadline mismatch in scheduled deferred EAX rows')
    return entries


def source_map(row: dict, scope: str) -> Path:
    if scope == 'formal':
        return (PANEL_INPUTS / (row['map'] + '.tsp')).resolve(strict=True)
    candidate = (OUTPUTS / row['problem_relative_to_outputs']).resolve(strict=True)
    ensure(candidate.is_relative_to(OUTPUTS), 'qualification input must be existing project evidence')
    return candidate


def check_casebook(path: Path) -> list[dict]:
    cases = read(path)['qualification_cases']
    ensure(len(cases) == 3 and {row['coverage'] for row in cases} == FORMAL_RESEARCH_TASKS,
           'exactly one declared largest, fractional and high-frequency qualification required')
    planned = read_planned_rows()
    planned_inputs = {(row['input_sha256'], int(row['pool_seed'])) for row in planned}
    maximum_dimension = max(int(row['n']) for row in planned)
    for case in cases:
        ensure(case['label'].isascii() and case['label'].isalnum() and len(case['label']) <= 16,
               'qualification attempt label is invalid')
        ensure(isinstance(case['seed'], int) and 0 < case['seed'] <= 2147483647 and
               (case['input_sha256'], case['seed']) not in planned_inputs,
               'qualification instance-and-seed pair must be separate from the 200 test rows')
        ensure(sha(source_map(case, 'qualification')) == case['input_sha256'], 'qualification map bytes differ')
        if case['coverage'] == 'largest':
            ensure(case['dimension'] >= maximum_dimension, 'declared largest qualification is too small')
    ensure(len({case['label'] for case in cases}) == 3, 'duplicate qualification label')
    return cases


def pe_format(path: Path) -> str:
    with path.open('rb') as stream:
        dos = stream.read(64)
        ensure(dos[:2] == b'MZ', 'native solver is not a PE')
        stream.seek(struct.unpack_from('<I', dos, 60)[0])
        header = stream.read(26)
    ensure(header[:4] == b'PE\0\0' and struct.unpack_from('<H', header, 4)[0] == 0x8664 and
           struct.unpack_from('<H', header, 24)[0] == 0x20B, 'native solver is not x86_64 PE32+')
    return 'PE32+ x86_64'


def archived_maximum_bytes() -> int:
    return max(sum(path.stat().st_size for path in (HISTORICAL_LARGE / case).rglob('*') if path.is_file())
               for case in ('L2', 'L3'))


def bind(case_file: Path, task_sheet: Path, run_root: Path) -> dict:
    ensure(task_sheet.is_file() and task_sheet.stat().st_size > 0, 'an actual execution task sheet is required')
    ensure('R13' in task_sheet.read_text(encoding='utf-8-sig'), 'task sheet does not contain the R13 item')
    cases = check_casebook(case_file)
    run_root = run_root.resolve()
    ensure(run_root.parent.is_dir() and (not run_root.exists() or (run_root.is_dir() and not any(run_root.iterdir()))),
           'supplemental artifact root must be new or empty')
    ancestry = get_ancestry()
    native, bound = ancestry.established_runtime()
    native = native.resolve(strict=True)
    entries = read_planned_rows()
    core = OLD_REVIEW / 'phase_b_numeric' / 'euc2d_verify.py'
    immutable = [PLAN, MODEL, STORAGE, STATE / 'execution_scope.json', STATE / 'main_admission.json', case_file,
                 task_sheet, Path(__file__), OBSERVER, ROOT / 'review_eax_bindings.py', core,
                 ROOT / 'decimal_eax_candidate.py', ROOT / 'static_receipt.json']
    immutable += [source_map(case, 'qualification') for case in cases]
    immutable += sorted({source_map(row, 'formal') for row in entries})
    bound.update({str(path.resolve(strict=True)): sha(path) for path in immutable})
    model_rows = {row['instance']: row for row in csv_rows(MODEL)}
    for row in entries:
        old = model_rows[row['map']]
        ensure(old['mismatches'] == old['narrowing_errors'] == '0' and old['dimension'] == row['n'] and
               bound[str(source_map(row, 'formal'))] == old['instance_sha256'] == row['input_sha256'],
               'existing exact-distance receipt differs from frozen scheduled map')
    staging = read(ROOT / 'static_receipt.json')
    ensure(staging['native_sha256_unchanged'] == sha(native) == NATIVE_SHA,
           'GA-EAX native build differs from static review')
    ensure(staging['deferred_slots'] == 200 and staging['formal_eax_slots_started'] == 0,
           'prior partial EAX scores cannot be included')
    exact = load('cmk_eax_binding_exact', core)
    for case in cases:
        problem = exact.read_problem(source_map(case, 'qualification'))
        ensure(problem.n == case['dimension'], 'qualification input dimension mismatch')
        if case['coverage'] == 'fractional':
            ensure(any(x % problem.lattice or y % problem.lattice for x, y in problem.points),
                   'fractional-coordinate qualification must use a truly fractional input')
    contract = {'version': FROZEN_POLICY, 'time_utc': now(), 'scope': 'isolated_R13_EAX_only',
                'task_sheet_sha256': sha(task_sheet), 'native': str(native), 'native_sha256': sha(native),
                'native_format': pe_format(native), 'solver_cpu': 0, 'sampler_cpu': 1,
                'per_process_commit_cap_bytes': 4 * 1024**3, 'admission_available_bytes': HARDWARE_BYTES,
                'run_root': str(run_root), 'disk_reserve_bytes': read(STORAGE)['reserve_bytes'],
                'historical_large_slot_bytes': archived_maximum_bytes(),
                'cutoffs_s': CUTS, 'native_options': ['1', 'DATA', '100', '30'],
                'restart_seed_step': 100000, 'planned_main_sha256': sha(PLAN),
                'first_original_run_id': entries[0]['run_id'], 'qualification_cases': cases,
                'planned_eax_rows': entries, 'runtime_hashes': bound}
    write_new(CONTRACT, contract)
    return {'contract_sha256': sha(CONTRACT), 'frozen_files': len(bound), 'planned': len(entries),
            'qualification': len(cases), 'native_sha256': sha(native)}


def disk_admission(run_root: Path | None = None, remaining: int = 1) -> dict:
    available = psutil.virtual_memory().available
    run_root = run_root or ROOT / 'runs'
    free_disk = shutil.disk_usage(run_root.parent).free
    reserve = read(STORAGE)['reserve_bytes']
    minimum_disk = reserve + remaining * archived_maximum_bytes()
    runner = load('cmk_eax_power_probe', RECOVERY / 'run_recovery_postcheck.py')
    ac_power = runner.power_ok()
    values = {'checked_at_utc': now(), 'available_bytes': available, 'available_min_bytes': HARDWARE_BYTES,
              'disk_free_bytes': free_disk, 'disk_min_bytes': minimum_disk, 'disk_remaining_slots': remaining,
              'disk_root': str(run_root), 'ac_power': ac_power}
    values['eligible'] = available >= HARDWARE_BYTES and free_disk >= minimum_disk and ac_power
    return values


def inspect_outputs(row: dict, scope: str, attempt: Path, result: dict) -> dict:
    raw = attempt / 'w' / 'result.json'
    method = result['status']
    checks = {'score': None, 'complete_candidate_ledger': False, 'end_to_end_passed': False}
    if not raw.is_file():
        return dict(checks, terminal_status=method, explanation='inner result absent')
    inner = read(raw)
    records = inner.get('eax_discovery_reconciliation', [])
    children = inner.get('children', [])
    checks.update(published=sum(r['published_count'] for r in records), consumed=sum(r['consumed_count'] for r in records),
                  native_child_processes=len(children), native_best=inner.get('best'),
                  inner_status=inner['status'], inner_failures=inner.get('failures'))
    if method not in ('valid', 'budget_no_delivery'):
        return dict(checks, terminal_status=method, explanation='existing guarded runner rejected')
    stop_module = load('cmk_eax_stop_proof_helpers', FROZEN / 'adapter.py').previous.adapter
    stops = [child for child in children if child.get('stop_requested')]
    complete = bool(records) and all(r['status'] == 'complete' and r['published_count'] == r['consumed_count'] and
                 not r.get('missing_sequences') and not r.get('published_not_consumed') and not r.get('unexpected')
                 for r in records)
    observed = (inner.get('stop') or {}).get('requested_s')
    stop_ok = (len(stops) == 1 and isinstance(observed, (int, float)) and CUTS[0] <= observed < CUTS[1] and
               all(stop_module.valid_proof(child['stop_proof'], child['pid'], child['cleanup_observed_s']) and
                   child['stop_proof']['job_zero_observed_s'] < CUTS[1] for child in stops))
    soft_bounds = ('run_id', 'number_of_cities', 'stop_request_s', 'search_deadline_s',
                   'commit_strictly_before_s', 'cleanup_deadline_s')
    want = (row['run_id'], int(row['n'] if scope == 'formal' else row['dimension']), *CUTS)
    ensure(tuple(inner.get(key) for key in soft_bounds) == want and inner['map_sha256'] == row['input_sha256'] and
           inner['binary_sha256'] == NATIVE_SHA and inner['wrapper_sha256'] == sha(OBSERVER) and
           sha(attempt / 'w' / 'input.tsp') == row['input_sha256'], 'result and dispatch do not agree')
    if not complete or not stop_ok:
        return dict(checks, terminal_status='isolated_eax_evidence_failure',
                    complete_candidate_ledger=complete, complete_stop_proof=stop_ok)
    proof = None
    if method == 'valid':
        proof = read(attempt / 'independent_validation.json')
        ensure(proof['independent_recount']['euc_2d_integer_length'] == proof['length'] == proof['second_recount']['length'] and
               proof['independent_recount']['route_sha256'] == proof['route_sha256'] == proof['second_recount']['route_sha256'],
               'the two exact outer recounts do not agree')
        ensure(0 <= proof['stop_s'] < CUTS[1] and 0 <= proof['commit_s'] < CUTS[2] and
               0 <= proof['all_processes_cleanup_charged_s'] < CUTS[3], 'strict evidence window invalid')
    else:
        ensure(inner['best'] is None and not inner['failures'] and
               result['owned_processes_cleanup_end_monotonic'] - inner['start_monotonic'] < CUTS[3],
               'ordinary budget no-delivery cleanup/evidence incomplete')
    checks.update(terminal_status=method, complete_candidate_ledger=True, complete_stop_proof=True,
                  end_to_end_passed=True, stop_request_s=observed,
                  last_native_stop_proof_s=max(child['exited_s'] for child in children),
                  owned_cleanup_s=result['owned_processes_cleanup_end_monotonic'] - inner['start_monotonic'])
    if scope == 'formal' and proof is not None:
        checks.update(score=proof['length'], route_sha256=proof['route_sha256'])
    if proof is not None:
        checks['selected_candidate_length'] = proof['length']
        checks['commit_s'] = proof['commit_s']
    return checks


def terminal_path(scope: str, label: str) -> Path:
    return ROOT / 'ledger' / scope / (label + '_terminal.json')


def run_attempt(contract: dict, input_row: dict, scope: str, phase_admission: Path | None) -> dict:
    if scope == 'formal':
        label = f"e{int(input_row['slot']):04d}"
    else:
        label = input_row['label']
    terminal = terminal_path(scope, label)
    if terminal.exists():
        return read(terminal)
    dispatch = bound_dispatch_path(scope, label)
    attempt = Path(contract['run_root']) / scope / label
    ensure(not dispatch.exists() and not attempt.exists(),
           'an unfinished dispatch is unresolved; do not rerun an unknown owned process')
    formal_directory = ROOT / 'ledger' / 'formal'
    remaining = len(contract['planned_eax_rows']) - len(list(formal_directory.glob('*_terminal.json')))
    hardware = disk_admission(Path(contract['run_root']), remaining if scope == 'formal' else 1)
    if not hardware['eligible']:
        hardware_logs = ROOT / 'hardware_blockers'
        hardware_logs.mkdir(exist_ok=True)
        write_new(hardware_logs / f'{scope}_{label}_{datetime.now().strftime("%Y%m%d%H%M%S%f")}.json', hardware)
        raise RuntimeError(f'pre-dispatch eligibility blocked: {hardware}')
    ancestry = get_ancestry()
    native = Path(contract['native'])
    wrapper = load('cmk_review_recovery_runner', RECOVERY / 'run_recovery_postcheck.py')
    wrapper.EXTERNAL = OBSERVER
    wrapper.batch.EAX = native
    install_outer_callbacks(wrapper)
    load('cmk_eax_error_classifier', FROZEN / 'outer_errors.py').install(wrapper)
    row = ({**input_row, 'pool_seed': str(input_row['seed']), 'map': source_map(input_row, scope).stem,
            'run_id': f"CMK_R13_QUAL_{label}"} if scope == 'qualification' else input_row)
    problem = source_map(input_row, scope)
    guard = load('cmk_eax_guard', FROZEN / 'frozen_guard.py')
    expected = {**contract['runtime_hashes'], str(CONTRACT): sha(CONTRACT)}
    if phase_admission is not None:
        expected[str(phase_admission)] = sha(phase_admission)
    outer_row = {'sequence': row.get('slot', '1'), 'run_id': row['run_id'], 'map_id': row['map'],
                 'seed': str(row['pool_seed']), 'method': 'EAX_r', 'attempt': 'a01'}
    attempt.parent.mkdir(parents=True, exist_ok=True)
    dispatch.parent.mkdir(parents=True, exist_ok=True)
    # Guard before writing a dispatch, so a changed artifact never consumes a
    # frozen result slot and can never cause a score to be written.
    with guard.protected_frozen_files(ROOT / 'writer.lock', expected):
        detail = {'scope': scope, 'source_row': input_row, 'method': 'EAX_r', 'cpu': 0,
                  'cutoffs_s': CUTS, 'run_id': row['run_id'], 'seed': int(row['pool_seed']),
                  'problem': str(problem), 'work': str(attempt / 'w'), 'input_sha256': row['input_sha256'],
                  'native': str(native), 'native_sha256': sha(native), 'wrapper_sha256': sha(OBSERVER),
                  'runtime_contract_sha256': sha(CONTRACT), 'admission_sha256': expected.get(str(phase_admission)),
                  'started_utc': now(), 'controller_pre_dispatch': hardware}
        write_new(dispatch, detail)
        with ancestry.eax_control_affinity():
            outcome = wrapper.run_one(outer_row, problem, attempt, formal=False)
        try:
            proof = inspect_outputs(row, scope, attempt, outcome)
        except (ValueError, TypeError, KeyError, OSError) as failure:
            proof = {'terminal_status': 'isolated_eax_evidence_failure', 'explanation': repr(failure), 'score': None,
                     'end_to_end_passed': False}
    terminal_record = {**detail, **proof, 'time_utc': now(), 'outer_status': outcome.get('status'),
                       'outer_error': outcome.get('error'), 'counts_as_formal': scope == 'formal',
                       'material_sha256': {path: sha(attempt / path) for path in (
                           'result.json', 'job_final.json', 'independent_validation.json', 'w/result.json')
                         if (attempt / path).is_file()}}
    write_new(terminal, terminal_record)
    return terminal_record


def admit(contract: dict):
    evidence = {}
    for case in contract['qualification_cases']:
        path = terminal_path('qualification', case['label'])
        result = read(path)
        ensure(result['source_row'] == case and result['scope'] == 'qualification' and
               result['runtime_contract_sha256'] == sha(CONTRACT) and result['end_to_end_passed'] is True and
               result['terminal_status'] == 'valid' and result['score'] is None,
               f"frozen engineering case not passed: {case['label']}")
        evidence[str(path)] = sha(path)
    receipt = {'admitted': True, 'admitted_at_utc': now(), 'runtime_contract_sha256': sha(CONTRACT),
               'case_terminal_hashes': evidence, 'native_sha256': contract['native_sha256'],
               'preregistered_original_rows': len(contract['planned_eax_rows'])}
    write_new(ADMISSION, receipt)
    return receipt


def formal(contract: dict, count: int | None):
    admitted = read(ADMISSION)
    ensure(admitted['admitted'] is True and admitted['runtime_contract_sha256'] == sha(CONTRACT) and
           contract['planned_eax_rows'] == read_planned_rows() and
           all(sha(Path(path)) == digest for path, digest in admitted['case_terminal_hashes'].items()),
           'frozen admission or original schedule no longer match')
    consecutive = 0
    last_signature = None
    newly_started = 0
    for row in contract['planned_eax_rows']:
        terminal = terminal_path('formal', f"e{int(row['slot']):04d}")
        was_done = terminal.is_file()
        if not was_done and count is not None and newly_started >= count:
            break
        record = run_attempt(contract, row, 'formal', ADMISSION)
        newly_started += not was_done
        failure = record['terminal_status']
        if failure == 'monitor_invalid':
            raise RuntimeError('resource protection rejected formal run; hold this scope')
        if failure in ('valid', 'budget_no_delivery'):
            consecutive = 0
            last_signature = None
            continue
        signature = (failure, record.get('explanation'), record.get('outer_error'))
        consecutive = consecutive + 1 if signature == last_signature else 1
        last_signature = signature
        if consecutive >= 2:
            raise RuntimeError(f'repeated EAX-specific failure; hold remaining EAX rows: {signature}')
    return status()


def status():
    rows = read_planned_rows()
    result_dir = ROOT / 'ledger' / 'formal'
    formal_status = Counter(read(p)['terminal_status'] for p in result_dir.glob('*_terminal.json'))
    return {'protocol': FROZEN_POLICY, 'planned_eax': len(rows),
            'timed_qualification_attempts': len(list((ROOT / 'ledger' / 'qualification').glob('*_dispatch.json'))),
            'started_eax': len(list(result_dir.glob('*_dispatch.json'))), 'terminal_eax': dict(formal_status),
            'untouched_core_slots': 600, 'formal_admitted': ADMISSION.is_file(), 'runtime_bound': CONTRACT.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command')
    bind_parser = sub.add_parser('bind')
    bind_parser.add_argument('--casebook', required=True, type=Path)
    bind_parser.add_argument('--task-sheet', required=True, type=Path)
    bind_parser.add_argument('--run-root', default=ROOT / 'runs', type=Path)
    qualifier = sub.add_parser('qualify')
    qualifier.add_argument('label')
    sub.add_parser('admit')
    formally = sub.add_parser('formal')
    formally.add_argument('--initial-count', type=int)
    sub.add_parser('status')
    hardware = sub.add_parser('hardware')
    hardware.add_argument('--run-root', default=ROOT / 'runs', type=Path)
    hardware.add_argument('--remaining', type=int, default=1)
    problem = parser.parse_args()
    if problem.command in (None, 'status'):
        result = status()
    elif problem.command == 'hardware':
        result = disk_admission(problem.run_root, problem.remaining)
    elif problem.command == 'bind':
        result = bind(problem.casebook, problem.task_sheet, problem.run_root)
    else:
        contract = read(CONTRACT)
        ancestry = get_ancestry()
        with ancestry.serial_scope():
            if problem.command == 'qualify':
                selected, = [case for case in contract['qualification_cases'] if case['label'] == problem.label]
                result = run_attempt(contract, selected, 'qualification', None)
            elif problem.command == 'admit':
                result = admit(contract)
            else:
                result = formal(contract, problem.initial_count)
    print(result, flush=True)


if __name__ == '__main__':
    main()
