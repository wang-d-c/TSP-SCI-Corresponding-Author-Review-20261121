"""Separately bound EAX adapter with exact-decimal candidate validation.

The 2026-11-20 85-second engineering observer is the source of this entry.
The native solver, stop chain, candidate accounting, and deadlines are unchanged.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

from decimal_eax_candidate import install_inner_callbacks
from review_eax_bindings import verify_dispatch

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE.parent.parent
ANCESTOR = OUTPUTS / 'tsp_gpt_diagnosis_v2_20261119/eax_formal_binding/frozen/adapter.py'
REQUEST_S = 85.0
PROOF_BEFORE_S = 86.0
DELIVERY_BEFORE_S = 88.0
CLEANUP_BEFORE_S = 90.0


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def proof_failure(proof):
    if not proof or proof.get('status') != 'passed':
        return 'stop_deadline_not_proven'
    if not proof.get('job_zero_observed_s', PROOF_BEFORE_S) < PROOF_BEFORE_S:
        return 'stop_deadline_not_proven'
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--method', choices=['EAX_r'], required=True)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--problem', type=Path, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--cpu', type=int, choices=[0], required=True)
    parser.add_argument('--outer-launch-monotonic-ns', type=int, required=True)
    parser.add_argument('--outer-launch-unix-ns', type=int, required=True)
    args = parser.parse_args()
    verify_dispatch(args)

    previous = load('review_eax_v2', ANCESTOR)
    base = previous.base
    install_inner_callbacks(base)
    base.STOP_REQUEST_S = REQUEST_S
    base.__file__ = str(Path(__file__).resolve())
    stop_adapter = previous.previous.adapter
    upstream_record = base.json_new

    class Run(previous.RueRepairRun):
        def accept_candidate(self, path, xy):
            # Each immutable source is evaluated once, while time remains.
            # A digest can reuse only a completed, independently checked cost.
            observed_key = str(path)
            if observed_key in self.seen_eax_immutable_paths or self.elapsed() >= PROOF_BEFORE_S:
                return
            try:
                raw = base.closed_snapshot(path)
            except (OSError, PermissionError):
                return
            observed = self.elapsed()
            if observed >= PROOF_BEFORE_S or not raw.rstrip().endswith(b'EOF'):
                return
            digest = base.digest(raw)
            seen = self.seen_eax_immutable_paths
            if digest in self.seen_digests:
                seen.add(observed_key)
                self.event('duplicate_candidate_source_observed', source=observed_key, sha256=digest,
                           observed_s=observed)
                return
            try:
                length = base.validate_tour(raw, xy)
            except (ValueError, UnicodeError, IndexError) as error:
                self.failures.append({'kind': 'candidate_invalid', 'source': observed_key, 'error': str(error)})
                seen.add(observed_key)
                return
            validated = self.elapsed()
            self.seen_digests.add(digest)
            seen.add(observed_key)
            if validated >= DELIVERY_BEFORE_S:
                self.failures.append({'kind': 'candidate_validation_after_deadline', 'source': observed_key})
                return
            if self.best is not None and length >= self.best['length']:
                self.event('candidate_validated_non_improving', source=observed_key, sha256=digest,
                           observed_s=observed, verified_s=validated, length=length)
                return

            self.snapshots += 1
            filename = f'{self.snapshots:06d}_{digest}.tour'
            snapshot = self.work / 'snapshots' / filename
            base.write_new(snapshot, raw)
            frozen = self.elapsed()
            if frozen >= PROOF_BEFORE_S:
                self.event('candidate_frozen_too_late', source=observed_key, sha256=digest,
                           observed_s=observed, frozen_s=frozen)
                return
            # Check that the immutable bytes now on disk are the exact bytes
            # scored above. Avoid repeating all distance calculations here.
            if base.digest(base.closed_snapshot(snapshot)) != digest:
                raise ValueError('candidate snapshot bytes changed')
            verified = self.elapsed()
            delivery = self.work / 'committed' / filename
            base.write_new(delivery, raw)
            delivered = self.elapsed()
            proof = {'source': observed_key, 'path': str(delivery), 'length': length, 'sha256': digest,
                     'observed_s': observed, 'scored_s': validated, 'frozen_s': frozen, 'verified_s': verified,
                     'delivered_s': delivered, 'eligible': delivered < DELIVERY_BEFORE_S,
                     'discovery_time': 'unknown; observed time only'}
            if proof['eligible']:
                self.best = proof
                self.event('candidate_committed', **proof)
            else:
                self.failures.append({'kind': 'candidate_delivery_after_deadline', 'source': observed_key})
                self.event('candidate_delivery_too_late', **proof)

    def strict_record(path, record):
        if Path(path).name == 'result.json' and record.get('method') == 'EAX_r':
            for child in record.get('children', []):
                if child.get('stop_requested'):
                    failure = proof_failure(stop_adapter._stop_proofs.get(child['pid']))
                    if failure is not None:
                        record.setdefault('failures', []).append({'kind': failure, 'pid': child['pid']})
                        record['status'] = 'failed'
            record['wrapper_version'] = 'review_EAX_decimal_85_R13a01'
        return upstream_record(path, record)

    base.json_new = strict_record
    return Run(args).run()


if __name__ == '__main__':
    raise SystemExit(main())
