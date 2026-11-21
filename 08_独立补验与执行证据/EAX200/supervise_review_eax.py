"""Durable isolated R13 EAX supervisor. It does nothing without --start."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

import run_review_eax as core
from review_eax_bindings import ensure, load, read, sha, write_new


EVENTS = core.ROOT / 'controller_events.jsonl'
SOURCE = core.OLD_REVIEW / 'phase_b_common_r3'
REST_RECOVERY_SECONDS = 68
OBSERVED_WINDOW_SECONDS = 60


def event(kind, **detail):
    item = {'time_utc': core.now(), 'event': kind, **detail}
    with EVENTS.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(item, ensure_ascii=False, allow_nan=False), flush=True)


def resource_wait(contract, remaining, phase, label):
    last = None
    while True:
        current = core.disk_admission(Path(contract['run_root']), remaining)
        if current['eligible']:
            if last is not None:
                event('resource_wait_completed', phase=phase, label=label, current=current)
            return
        event('resource_wait', phase=phase, label=label, current=current)
        last = current
        time.sleep(30)


def proved_environment_interruption(contract, label):
    result_path = Path(contract['run_root']) / 'formal' / label / 'result.json'
    if not result_path.is_file():
        return None
    result = read(result_path)
    cleanup = result.get('cleanup') or {}
    guard = result.get('resource_guard') or {}
    error = guard.get('failure') or {}
    if (result.get('status') == 'monitor_invalid' and error.get('kind') == 'sustained_paging_pressure' and
            cleanup.get('status') == 'clean' and cleanup.get('remaining_owned_processes') == 0 and
            cleanup.get('ownership_known') is True and cleanup.get('unrelated_processes_touched') is False and
            result.get('sampler_exit_code') is not None):
        return {'outer_result_sha256': sha(result_path), 'cleanup': cleanup, 'observed_cause': error['kind']}
    return None


def write_paging_recovery(contract, label, environment, remaining):
    recovered = core.ROOT / 'ledger' / 'formal' / (label + '_recovery.json')
    if recovered.is_file():
        saved = read(recovered)
        ensure(saved['original_terminal_sha256'] == sha(core.terminal_path('formal', label)),
               'earlier environment recovery references changed original evidence')
        return saved

    # Use the already qualified R3 sampler and original paging readback.
    # This subprocess performs no native EAX or LKH search.
    sys.path.insert(0, str(SOURCE))
    runtime = load('cmk_eax_paging_recovery_original_runtime', SOURCE / 'owned_runtime.py')
    where = core.ROOT / 'resource_observations' / (label + '_' + datetime.now().strftime('%H%M%S_%f'))
    where.parent.mkdir(exist_ok=True)
    sampler = runtime.RECOVERY / 'system_sampler.py'
    resource_wait(contract, remaining, 'paging_recovery', label)
    runtime.preflight()
    event('paging_cooldown_begin', label=label, original=environment, evidence_directory=str(where))
    command = [sys.executable, '-B', '-X', 'utf8', str(sampler), '--directory', str(where),
               '--stop-file', str(where / 'stop'), '--max-seconds', str(REST_RECOVERY_SECONDS)]
    outcome = subprocess.run(command, stdin=subprocess.DEVNULL, timeout=85, creationflags=subprocess.CREATE_NO_WINDOW)
    ensure(outcome.returncode == 0, f'original sampler recovery observation failed at {where}')
    trace = runtime.validate_sampler_trace(where, [])
    observations = [json.loads(item) for item in (where / 'system_samples.jsonl').read_text(encoding='utf-8').splitlines()]
    clocks = [item['paging_record']['raw']['monotonic_start'] for item in observations
              if item['paging_record']['event'] == 'sample']
    ensure(clocks[-1] - clocks[0] >= OBSERVED_WINDOW_SECONDS and
           trace['minimum_available_bytes'] >= core.HARDWARE_BYTES,
           f'original paging warm-up did not verify 60 seconds of adequate resources at {where}')
    saved = {'evidence_path': str(where), 'original_terminal_sha256': sha(core.terminal_path('formal', label)),
             'time_utc': core.now(), 'terminal_attempt_never_retried': True, 'original_environment_failure': environment,
             'trace': trace, 'summary_sha256': sha(where / 'summary.json'), 'admission_readback': runtime.preflight()}
    write_new(recovered, saved)
    event('paging_cooldown_passed', label=label, evidence_file=str(recovered))
    return saved


def verify_existing_gate(contract):
    admission = read(core.ADMISSION)
    ensure(admission['admitted'] is True and admission['runtime_contract_sha256'] == sha(core.CONTRACT) and
           contract['planned_eax_rows'] == core.read_planned_rows() and
           all(sha(Path(path)) == digest for path, digest in admission['case_terminal_hashes'].items()),
           'earlier admission or frozen row identities differ')


def run_all():
    contract = read(core.CONTRACT)
    identity = psutil.Process()
    source = Path(__file__).resolve()
    with core.get_ancestry().serial_scope():
        event('controller_started', pid=identity.pid, process_creation_time=identity.create_time(),
              executable=sys.executable, controller_sha256=sha(source), frozen_contract_sha256=sha(core.CONTRACT),
              placed_outputs=contract['run_root'], exact_clock_boundaries=contract['cutoffs_s'])
        if not core.ADMISSION.is_file():
            for case in contract['qualification_cases']:
                label = case['label']
                resource_wait(contract, 1, 'qualification', label)
                terminal = core.run_attempt(contract, case, 'qualification', None)
                event('qualification_terminal', label=label, state=terminal['terminal_status'],
                      elapsed_proof=terminal.get('last_native_stop_proof_s'),
                      scored=False, started_native_count=terminal.get('native_child_processes'))
                ensure(terminal['end_to_end_passed'] is True and terminal['terminal_status'] == 'valid',
                       f'targeted engineering evidence did not pass for {label}')
            core.admit(contract)
            event('formal_admitted', qualification_gate_sha256=sha(core.ADMISSION))
        verify_existing_gate(contract)
        rows = contract['planned_eax_rows']
        for idx, row in enumerate(rows):
            label = f"e{int(row['slot']):04d}"
            terminal_path = core.terminal_path('formal', label)
            if not terminal_path.is_file():
                remaining = len(rows) - idx
                resource_wait(contract, remaining, 'formal', label)
                terminal = core.run_attempt(contract, row, 'formal', core.ADMISSION)
                event('formal_terminal', label=label, run_id=row['run_id'], state=terminal['terminal_status'],
                      score=terminal['score'], remaining_after_this=remaining - 1)
            else:
                terminal = read(terminal_path)
                ensure(terminal['source_row'] == row and terminal['admission_sha256'] == sha(core.ADMISSION),
                       f'prior result {label} identity changed')
            status = terminal['terminal_status']
            if status in ('valid', 'budget_no_delivery'):
                continue
            environment = proved_environment_interruption(contract, label) if status == 'monitor_invalid' else None
            if environment is not None:
                write_paging_recovery(contract, label, environment, len(rows) - idx - 1)
            else:
                # R26 requires any new numerical, publication or lifecycle
                # failure to pause the affected branch for actual diagnosis.
                raise RuntimeError(f'non-environment result requires review of {label}: {status}')
        event('controller_completed', **core.status())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', action='store_true', help='begin the single-lane timed qualification and formal EAX run')
    inputs = parser.parse_args()
    if not inputs.start:
        print(json.dumps(core.status(), ensure_ascii=False))
        return 0
    try:
        run_all()
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        event('controller_stopped', failure=str(exc), **core.status())
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
