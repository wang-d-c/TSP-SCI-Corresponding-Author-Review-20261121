"""Narrow post-run corrective audit for a separately versioned R13 continuation.

This does not control the native process, redefine the assigned 85-second
request, change timing thresholds, or restore the score of any prior attempt.
"""
from __future__ import annotations

from functools import lru_cache
import math

import run_review_eax as core
from review_eax_bindings import CUTS, ensure, load, read


VERSION = 'R13a02_kernel_action_audit'
ORIGINAL_INSPECT = core.inspect_outputs


@lru_cache(maxsize=1)
def owned_proof_verifier():
    return load('cmk_eax_a02_owned_proof', core.FROZEN / 'adapter.py').previous.adapter.valid_proof


def clock_ok(stop_record, proof, verify_proof, pid, cleanup_observed):
    try:
        requested = stop_record['requested_s']
        action = proof['termination_call_s']
        zero_activity = proof['job_zero_observed_s']
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in (requested, action, zero_activity)):
            return False
        if stop_record['action'] == 'terminate_owned_job':
            # Preparation can precede the actual owned kernel action.
            record_order = stop_record['child_pid'] == pid and 0.0 <= requested <= action
        elif stop_record['action'] == 'no_running_child':
            # A later watchdog idle observation can replace the request record.
            # It is not the termination request time. The child proof still
            # binds the actual action and zero population independently.
            record_order = stop_record['child_pid'] is None and zero_activity <= requested < CUTS[1]
        else:
            return False
        return (record_order and CUTS[0] <= action <= zero_activity < CUTS[1] and
                verify_proof(proof, pid, cleanup_observed))
    except (KeyError, TypeError, OverflowError):
        return False


def audit_action_clock(row, scope, attempt, result):
    legacy = ORIGINAL_INSPECT(row, scope, attempt, result)
    outer = result['status']
    if outer not in ('valid', 'budget_no_delivery'):
        return legacy
    raw = read(attempt / 'w' / 'result.json')
    stops = [child for child in raw.get('children', []) if child.get('stop_requested')]
    stop_record = raw.get('stop') or {}
    requested = stop_record.get('requested_s')
    if len(stops) != 1 or not clock_ok(stop_record, stops[0].get('stop_proof'), owned_proof_verifier(),
                                       stops[0].get('pid'), stops[0].get('cleanup_observed_s')):
        if legacy['end_to_end_passed']:
            return dict(legacy, terminal_status='isolated_eax_evidence_failure', score=None,
                        complete_stop_proof=False, end_to_end_passed=False,
                        explanation='native action or complete stop chronology failed the unchanged boundaries')
        return legacy

    if legacy['end_to_end_passed']:
        return dict(legacy, postrun_audit_policy=VERSION,
                    stop_record_role=stop_record['action'],
                    kernel_termination_call_s=stops[0]['stop_proof']['termination_call_s'])
    # Only the original lower-bound false negative is eligible for this path.
    # Everything else, including candidate-ledger and unchanged wrapper errors,
    # returns the prior decision without a new score.
    if (legacy.get('terminal_status') != 'isolated_eax_evidence_failure' or
            not legacy.get('complete_candidate_ledger') or legacy.get('complete_stop_proof') is not False or
            stop_record['action'] != 'terminate_owned_job' or not 0.0 <= requested < CUTS[0] or raw.get('failures')):
        return legacy
    ensure(0 <= result['owned_processes_cleanup_end_monotonic'] - raw['start_monotonic'] < CUTS[3],
           'strict owned cleanup exceeded original deadline')
    proof = None
    if outer == 'valid':
        proof = read(attempt / 'independent_validation.json')
        ensure(proof['independent_recount']['euc_2d_integer_length'] == proof['length'] == proof['second_recount']['length'] and
               proof['independent_recount']['route_sha256'] == proof['route_sha256'] == proof['second_recount']['route_sha256'],
               'the two exact outer recounts do not agree')
        ensure(0 <= proof['stop_s'] < CUTS[1] and 0 <= proof['commit_s'] < CUTS[2] and
               0 <= proof['all_processes_cleanup_charged_s'] < CUTS[3], 'previous strict evidence window invalid')
    else:
        ensure(raw['best'] is None and not raw['failures'], 'ordinary budget no-delivery evidence incomplete')
    legacy.update(terminal_status=outer, complete_stop_proof=True, end_to_end_passed=True,
                  stop_request_s=requested,
                  last_native_stop_proof_s=max(child['exited_s'] for child in raw['children']),
                  owned_cleanup_s=result['owned_processes_cleanup_end_monotonic'] - raw['start_monotonic'],
                  postrun_audit_policy=VERSION, stop_record_role=stop_record['action'],
                  kernel_termination_call_s=stops[0]['stop_proof']['termination_call_s'])
    if proof is not None:
        legacy['selected_candidate_length'] = proof['length']
        legacy['commit_s'] = proof['commit_s']
        if scope == 'formal':
            legacy.update(score=proof['length'], route_sha256=proof['route_sha256'])
    return legacy
