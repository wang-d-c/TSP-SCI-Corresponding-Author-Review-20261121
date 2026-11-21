"""Freeze and resume only untouched R13 slots using the kernel-action audit."""
import argparse
import json
from pathlib import Path
import sys

import psutil

import run_review_eax as core
import supervise_review_eax as scheduler
from review_eax_bindings import ensure, load, read, sha, write_new
from stop_gate_r13_a02 import VERSION, ORIGINAL_INSPECT, audit_action_clock, clock_ok, owned_proof_verifier


HERE = Path(__file__).resolve().parent
CHANGE = HERE / 'r13_a02_continuation.json'
GATE = HERE / 'stop_gate_r13_a02.py'
FIRST_REJECTED_LABEL = 'e0316'
FIRST_REJECTED_SHA = '3cd77510f4bbb63aae45541be02fb2a0876b4ab01a3b30f803b8eb753ca153db'
EXPECTED_CORE_CONTRACT_SHA = 'f86a13532bce63b083728cc196e2746477f70d8fcf7eac4debbc0dbf5eff1e1f'
EXPECTED_ORIGINAL_ADMISSION_SHA = '8254d1ef9faad6b8bc44e8625699df6b329728bb29f356a704d4253de44367bc'


def records_match_path(run_root, label, terminal):
    path = run_root / label
    for file, expected in terminal['material_sha256'].items():
        ensure(sha(path / file) == expected, f'{label}: old raw output changed')
    return path


def bound_history(contract):
    scheduler.verify_existing_gate(contract)
    ensure(sha(core.CONTRACT) == EXPECTED_CORE_CONTRACT_SHA and sha(core.ADMISSION) == EXPECTED_ORIGINAL_ADMISSION_SHA,
           'the actual passed a01 contract or admission changed')
    old_terminal = core.terminal_path('formal', FIRST_REJECTED_LABEL)
    ensure(sha(old_terminal) == FIRST_REJECTED_SHA, 'the first rejected record is immutable')
    raw = read(old_terminal)
    ensure(raw['terminal_status'] == 'isolated_eax_evidence_failure' and raw['score'] is None,
           'first rejected record lost its original unscored status')
    return old_terminal


def prepare():
    contract = read(core.CONTRACT)
    old_terminal = bound_history(contract)
    raw_root = Path(contract['run_root']) / 'formal'
    checked = {}
    first_issue = None
    for entry in contract['planned_eax_rows']:
        label = f"e{int(entry['slot']):04d}"
        path = core.terminal_path('formal', label)
        if not path.is_file():
            break
        terminal = read(path)
        run = records_match_path(raw_root, label, terminal)
        outer = read(run / 'result.json')
        older = ORIGINAL_INSPECT(entry, 'formal', run, outer)
        newer = audit_action_clock(entry, 'formal', run, outer)
        ensure(older['terminal_status'] == terminal['terminal_status'] and older['score'] == terminal['score'],
               f'{label}: original decision does not reproduce')
        if label == FIRST_REJECTED_LABEL:
            ensure(newer['terminal_status'] == 'valid' and newer['complete_stop_proof'] and
                   newer['stop_request_s'] < core.CUTS[0] <= newer['kernel_termination_call_s'],
                   'the correction does not narrowly reproduce the observed false negative')
            attempt = read(run / 'w' / 'result.json')
            child, = [item for item in attempt['children'] if item['stop_requested']]
            proof = child['stop_proof']
            verifier = owned_proof_verifier()
            valid_args = (verifier, child['pid'], child['cleanup_observed_s'])
            changed_call = dict(proof, termination_call_s=84.99)
            changed_zero = dict(proof, job_zero_observed_s=86.00)
            changed_pid = dict(proof, root_pid=child['pid'] + 1)
            ensure(not any(clock_ok(attempt['stop'], value, *valid_args)
                           for value in (changed_call, changed_zero, changed_pid)),
                   'negative test must reject premature kernel action, late zero proof and foreign pid')
            backwards = dict(attempt['stop'], requested_s=newer['kernel_termination_call_s'] + 0.1)
            ensure(not clock_ok(backwards, proof, *valid_args),
                   'negative test must reject request after the action')
            first_issue = {
                'label': label, 'retained_status': terminal['terminal_status'], 'retained_score': None,
                'first_terminal_sha256': sha(path), 'raw_evidence_sha256': terminal['material_sha256'],
                'original_request_preparation_timestamp_s': newer['stop_request_s'],
                'native_kernel_termination_call_timestamp_s': newer['kernel_termination_call_s'],
                'native_zero_activity_proof_timestamp_s': newer['last_native_stop_proof_s'],
                'same_raw_audit_replay_hypothetical_decision': 'valid_if_replayed_under_new_gate_but_no_retroactive_score',
                'negative_scenarios_rejected': ['kernel_call_before_85', 'zero_activity_at_86', 'foreign_pid', 'request_after_action'],
                'candidate_publications': newer['published'], 'candidate_consumed': newer['consumed'],
            }
        else:
            ensure(newer['terminal_status'] == terminal['terminal_status'] and newer['score'] == terminal['score'],
                   f'{label}: the narrow repair would change one of the earlier scored outcomes')
        checked[label] = sha(path)
    ensure(len(checked) == 79 and len([1 for item in checked if item != FIRST_REJECTED_LABEL]) == 78 and
           first_issue is not None, 'a01 79-terminal boundary differs or is unresolved')
    write_new(CHANGE, {'policy': VERSION, 'checked_at_utc': core.now(),
                       'original_runtime_contract_sha256': sha(core.CONTRACT),
                       'original_actual_admission_sha256': sha(core.ADMISSION),
                       'frozen_new_files': {str(file.resolve()): sha(file) for file in (Path(__file__), GATE)},
                       'existing_79_result_hashes': checked, 'existing_failure': first_issue,
                       'following_unstarted': 121, 'native_logic_or_time_controls_changed': False,
                       'qualification_evidence_reused': '3/3 actual cases with exactly identical native and timing interfaces',
                       'old_failed_slot_rerun_permitted': False})
    print(json.dumps({'policy': VERSION, 'new_gate_sha256': sha(CHANGE), 'replayed_a01_terminal_count': len(checked),
                      'untouched_original_failure': str(old_terminal), 'unstarted': 121,
                      'negative_scenarios_rejected': first_issue['negative_scenarios_rejected']}, ensure_ascii=False))


def run():
    contract = read(core.CONTRACT)
    bound_history(contract)
    amendment = read(CHANGE)
    ensure(amendment['policy'] == VERSION and amendment['original_runtime_contract_sha256'] == sha(core.CONTRACT) and
           amendment['original_actual_admission_sha256'] == sha(core.ADMISSION), 'continuation gate mismatch')
    for label, digest in amendment['existing_79_result_hashes'].items():
        ensure(sha(core.terminal_path('formal', label)) == digest, 'previous terminal record changed before resume')
    archive = load('cmk_a02_static_guard', core.FROZEN / 'frozen_guard.py')
    frozen = {**amendment['frozen_new_files'], str(CHANGE): sha(CHANGE)}
    identity = psutil.Process()
    core.inspect_outputs = audit_action_clock
    with core.get_ancestry().serial_scope(), archive.protected_frozen_files(HERE / 'continuation_writer.lock', frozen):
        scheduler.event('controller_continuation_started', pid=identity.pid, process_creation_time=identity.create_time(),
                        executable=sys.executable, policy=VERSION, amendment_sha256=sha(CHANGE),
                        exact_clock_boundaries=contract['cutoffs_s'], existing_first_failure=FIRST_REJECTED_LABEL,
                        unstarted=core.status()['planned_eax'] - core.status()['started_eax'])
        rows = contract['planned_eax_rows']
        for idx, row in enumerate(rows):
            label = f"e{int(row['slot']):04d}"
            terminal_path = core.terminal_path('formal', label)
            if label == FIRST_REJECTED_LABEL:
                ensure(sha(terminal_path) == FIRST_REJECTED_SHA, 'the original failed slot must never be repeated')
                continue
            if terminal_path.is_file():
                terminal = read(terminal_path)
                ensure(terminal['source_row'] == row and terminal['admission_sha256'] == sha(core.ADMISSION),
                       'existing supplemental result identity has changed')
            else:
                remaining = len(rows) - idx
                scheduler.resource_wait(contract, remaining, 'formal_continuation', label)
                terminal = core.run_attempt(contract, row, 'formal', core.ADMISSION)
                scheduler.event('formal_terminal', label=label, run_id=row['run_id'], state=terminal['terminal_status'],
                                score=terminal['score'], remaining_after_this=remaining - 1, postrun_audit_policy=VERSION)
            status = terminal['terminal_status']
            if status in ('valid', 'budget_no_delivery'):
                continue
            environment = scheduler.proved_environment_interruption(contract, label) if status == 'monitor_invalid' else None
            if environment is None:
                raise RuntimeError(f'non-environment result requires review of {label}: {status}')
            scheduler.write_paging_recovery(contract, label, environment, len(rows) - idx - 1)
        scheduler.event('controller_completed', audit_policy=VERSION, **core.status())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--prepare', action='store_true')
    group.add_argument('--start', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare()
        return 0
    if not args.start:
        print(json.dumps(core.status(), ensure_ascii=False))
        return 0
    try:
        run()
    except (RuntimeError, ValueError, OSError, KeyError) as failure:
        scheduler.event('controller_stopped', audit_policy=VERSION, failure=str(failure), **core.status())
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
